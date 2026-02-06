"""
Agent Loop

实现完整的 agentic loop 执行周期：
intake → context assembly → model inference → tool execution → streaming replies → persistence

借鉴 OpenClaw/Moltbot 的设计，支持：
- 每 session 串行化执行
- 队列模式（collect、steer、followup）
- 流式输出 (事件驱动)
- 工具调用 (ReAct 模式)
- 会话压缩
- 生命周期钩子
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, TYPE_CHECKING
from uuid import uuid4

from orb.system.services.logger import LoggerMixin
from orb.agent.runtime.stream_handler import (
    StreamHandler,
    StreamEvent,
    StreamEventType,
    create_stream_handler,
)

if TYPE_CHECKING:
    from orb.agent.infrastructure.session_store import (
        SessionStore,
        Session,
        SessionMessage,
    )
    from orb.agent.infrastructure.workspace import WorkspaceManager
    from orb.agent.runtime.context_builder import ContextBuilder, AgentContext
    from orb.agent.runtime.tool_executor import ToolExecutor, ToolCall, ToolResult


class LoopPhase(Enum):
    """Loop 执行阶段"""
    IDLE = "idle"
    INTAKE = "intake"              # 接收输入
    CONTEXT_ASSEMBLY = "context"   # 上下文组装
    INFERENCE = "inference"        # 模型推理
    TOOL_EXECUTION = "tool"        # 工具执行
    STREAMING = "streaming"        # 流式输出
    PERSISTENCE = "persistence"    # 持久化
    COMPLETED = "completed"        # 完成
    ERROR = "error"                # 错误


class LoopState(Enum):
    """Loop 状态"""
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


class QueueMode(Enum):
    """队列模式"""
    COLLECT = "collect"    # 收集消息直到当前 turn 完成
    STEER = "steer"        # 在工具调用后注入新消息
    FOLLOWUP = "followup"  # 保持消息在队列中等待下一个 turn


@dataclass
class LoopConfig:
    """Loop 配置"""
    max_iterations: int = 50           # 最大迭代次数
    timeout_seconds: float = 600.0     # 超时时间
    queue_mode: QueueMode = QueueMode.COLLECT
    enable_streaming: bool = True
    enable_tool_calls: bool = True
    max_tool_calls_per_turn: int = 20
    compaction_threshold: int = 100    # 消息数量阈值触发压缩
    retry_on_error: bool = True
    max_retries: int = 3


@dataclass
class RunContext:
    """运行上下文"""
    run_id: str = field(default_factory=lambda: str(uuid4()))
    session_id: str = ""
    agent_id: str = ""
    user_input: str = ""
    model: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # 运行时状态
    phase: LoopPhase = LoopPhase.IDLE
    iteration: int = 0
    tool_calls_count: int = 0
    tokens_used: int = 0
    
    # 上下文
    context: Optional[AgentContext] = None
    pending_tool_calls: List[ToolCall] = field(default_factory=list)
    tool_results: List[ToolResult] = field(default_factory=list)
    
    # 输出
    assistant_response: str = ""
    streaming_chunks: List[str] = field(default_factory=list)


@dataclass
class RunResult:
    """运行结果"""
    run_id: str
    session_id: str
    status: str  # "success", "error", "timeout", "cancelled"
    response: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    started_at: str = ""
    ended_at: str = field(default_factory=lambda: datetime.now().isoformat())
    tokens_used: int = 0
    iterations: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


# 类型定义
InferenceFunc = Callable[["AgentContext"], AsyncIterator[str]]
LifecycleHook = Callable[["RunContext"], None]
AsyncLifecycleHook = Callable[["RunContext"], Any]  # 可返回 coroutine


class AgentLoop(LoggerMixin):
    """
    Agent Loop
    
    实现完整的 agentic loop 执行周期。
    支持事件驱动架构，通过 StreamHandler 发射生命周期、工具和助手事件。
    """
    
    def __init__(
        self,
        config: LoopConfig,
        context_builder: ContextBuilder,
        tool_executor: ToolExecutor,
        session_store: SessionStore,
        inference_func: Optional[InferenceFunc] = None,
        stream_handler: Optional[StreamHandler] = None,
    ):
        """
        初始化 Agent Loop
        
        Args:
            config: Loop 配置
            context_builder: 上下文构建器
            tool_executor: 工具执行器
            session_store: 会话存储
            inference_func: 推理函数
            stream_handler: 流处理器（用于事件发射）
        """
        self._config = config
        self._context_builder = context_builder
        self._tool_executor = tool_executor
        self._session_store = session_store
        self._inference_func = inference_func
        
        # 流处理器（事件驱动核心）
        self._stream_handler = stream_handler or create_stream_handler()
        
        self._state = LoopState.CREATED
        self._current_run: Optional[RunContext] = None
        self._abort_signal = asyncio.Event()
        
        # 生命周期钩子 (同步回调)
        self._hooks: Dict[str, List[LifecycleHook]] = {
            "before_run": [],
            "after_intake": [],
            "before_inference": [],
            "after_inference": [],
            "before_tool_call": [],
            "after_tool_call": [],
            "before_persistence": [],
            "after_run": [],
            "on_error": [],
        }
        
        # 异步钩子 (async 回调)
        self._async_hooks: Dict[str, List[AsyncLifecycleHook]] = {
            "before_run": [],
            "after_intake": [],
            "before_inference": [],
            "after_inference": [],
            "before_tool_call": [],
            "after_tool_call": [],
            "before_persistence": [],
            "after_run": [],
            "on_error": [],
        }
        
        # 队列和锁
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._lock = asyncio.Lock()
        
        # 运行历史
        self._run_history: List[RunResult] = []
        self._max_history = 100
        
    @property
    def state(self) -> LoopState:
        """Loop 状态"""
        return self._state
        
    @property
    def current_run(self) -> Optional[RunContext]:
        """当前运行上下文"""
        return self._current_run
        
    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        return self._state == LoopState.RUNNING
        
    @property
    def stream_handler(self) -> StreamHandler:
        """流处理器"""
        return self._stream_handler
        
    @property
    def run_history(self) -> List[RunResult]:
        """运行历史"""
        return self._run_history.copy()
        
    def set_inference_func(self, func: InferenceFunc) -> None:
        """设置推理函数"""
        self._inference_func = func
        
    def set_stream_handler(self, handler: StreamHandler) -> None:
        """设置流处理器"""
        self._stream_handler = handler
        
    def register_hook(
        self,
        hook_name: str,
        callback: LifecycleHook,
        is_async: bool = False,
    ) -> None:
        """
        注册生命周期钩子
        
        Args:
            hook_name: 钩子名称
            callback: 回调函数
            is_async: 是否为异步回调
        """
        if is_async:
            if hook_name in self._async_hooks:
                self._async_hooks[hook_name].append(callback)
        else:
            if hook_name in self._hooks:
                self._hooks[hook_name].append(callback)
                
    def unregister_hook(
        self,
        hook_name: str,
        callback: LifecycleHook,
        is_async: bool = False,
    ) -> bool:
        """
        注销生命周期钩子
        
        Args:
            hook_name: 钩子名称
            callback: 回调函数
            is_async: 是否为异步回调
            
        Returns:
            是否成功移除
        """
        hooks = self._async_hooks if is_async else self._hooks
        if hook_name in hooks and callback in hooks[hook_name]:
            hooks[hook_name].remove(callback)
            return True
        return False
            
    async def _emit_hook(self, hook_name: str, context: RunContext) -> None:
        """触发钩子（同步和异步）"""
        # 同步钩子
        for callback in self._hooks.get(hook_name, []):
            try:
                callback(context)
            except Exception as e:
                self.logger.warning(f"Hook {hook_name} 执行失败: {e}")
                
        # 异步钩子
        for callback in self._async_hooks.get(hook_name, []):
            try:
                result = callback(context)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                self.logger.warning(f"Async Hook {hook_name} 执行失败: {e}")
                
    async def run(
        self,
        session_id: str,
        user_input: str,
        agent_id: str = "",
        model: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RunResult:
        """
        执行完整的 Agent Loop
        
        Args:
            session_id: 会话 ID
            user_input: 用户输入
            agent_id: Agent ID
            model: 模型
            parameters: 参数
            metadata: 元数据
            
        Returns:
            运行结果
        """
        # 创建运行上下文
        run_context = RunContext(
            session_id=session_id,
            agent_id=agent_id,
            user_input=user_input,
            model=model,
            parameters=parameters or {},
            metadata=metadata or {},
        )
        
        async with self._lock:
            self._current_run = run_context
            self._state = LoopState.RUNNING
            self._abort_signal.clear()
            
        # 设置流处理器上下文
        self._stream_handler.set_run_context(run_context.run_id, session_id)
        self._stream_handler.reset()
        
        # 发射生命周期开始事件
        await self._stream_handler.emit_lifecycle_start(
            phase="start",
            metadata={"agent_id": agent_id, "model": model},
        )
            
        # 触发 before_run 钩子
        await self._emit_hook("before_run", run_context)
        
        try:
            # 执行 loop
            result = await self._execute_loop(run_context)
            
            # 触发 after_run 钩子
            await self._emit_hook("after_run", run_context)
            
            # 发射生命周期结束事件
            await self._stream_handler.emit_lifecycle_end(
                status=result.status,
                summary=result.response[:200] if result.response else None,
                metadata={
                    "tokens_used": result.tokens_used,
                    "iterations": result.iterations,
                },
            )
            
            # 记录到历史
            self._add_to_history(result)
            
            return result
            
        except asyncio.TimeoutError:
            result = RunResult(
                run_id=run_context.run_id,
                session_id=session_id,
                status="timeout",
                error="执行超时",
                started_at=run_context.started_at,
                iterations=run_context.iteration,
            )
            await self._stream_handler.emit_lifecycle_error("执行超时")
            self._add_to_history(result)
            return result
            
        except asyncio.CancelledError:
            result = RunResult(
                run_id=run_context.run_id,
                session_id=session_id,
                status="cancelled",
                started_at=run_context.started_at,
                iterations=run_context.iteration,
            )
            await self._stream_handler.emit_lifecycle_error("执行被取消")
            self._add_to_history(result)
            return result
            
        except Exception as e:
            self.logger.error(f"Agent Loop 执行失败: {e}")
            await self._emit_hook("on_error", run_context)
            
            # 发射错误事件
            await self._stream_handler.emit_lifecycle_error(str(e))
            
            result = RunResult(
                run_id=run_context.run_id,
                session_id=session_id,
                status="error",
                error=str(e),
                started_at=run_context.started_at,
                iterations=run_context.iteration,
            )
            self._add_to_history(result)
            return result
            
        finally:
            async with self._lock:
                self._current_run = None
                self._state = LoopState.CREATED
                
    def _add_to_history(self, result: RunResult) -> None:
        """添加到运行历史"""
        self._run_history.append(result)
        if len(self._run_history) > self._max_history:
            self._run_history.pop(0)
                
    async def _execute_loop(self, context: RunContext) -> RunResult:
        """
        执行 Loop 主循环
        
        Args:
            context: 运行上下文
            
        Returns:
            运行结果
        """
        # 设置超时
        timeout = self._config.timeout_seconds
        
        async with asyncio.timeout(timeout):
            while context.iteration < self._config.max_iterations:
                # 检查中止信号
                if self._abort_signal.is_set():
                    return RunResult(
                        run_id=context.run_id,
                        session_id=context.session_id,
                        status="cancelled",
                        started_at=context.started_at,
                        iterations=context.iteration,
                    )
                    
                context.iteration += 1
                self.logger.debug(f"Loop iteration {context.iteration}/{self._config.max_iterations}")
                
                # Phase 1: Intake
                context.phase = LoopPhase.INTAKE
                await self._phase_intake(context)
                await self._emit_hook("after_intake", context)
                
                # Phase 2: Context Assembly
                context.phase = LoopPhase.CONTEXT_ASSEMBLY
                await self._phase_context_assembly(context)
                
                # Phase 3: Inference
                context.phase = LoopPhase.INFERENCE
                await self._emit_hook("before_inference", context)
                await self._phase_inference(context)
                await self._emit_hook("after_inference", context)
                
                # 发射助手响应结束事件
                if context.assistant_response:
                    await self._stream_handler.emit_assistant_end(
                        context.assistant_response,
                        metadata={"iteration": context.iteration},
                    )
                
                # 检查是否有工具调用
                if context.pending_tool_calls and self._config.enable_tool_calls:
                    # Phase 4: Tool Execution
                    context.phase = LoopPhase.TOOL_EXECUTION
                    await self._phase_tool_execution(context)
                    
                    # 检查队列模式是否需要中断
                    if self._config.queue_mode == QueueMode.STEER:
                        if not self._message_queue.empty():
                            # 注入新消息，跳过剩余工具调用
                            context.pending_tool_calls.clear()
                else:
                    # 没有工具调用，完成
                    break
                    
            # Phase 5: Persistence
            context.phase = LoopPhase.PERSISTENCE
            await self._emit_hook("before_persistence", context)
            await self._phase_persistence(context)
            
            context.phase = LoopPhase.COMPLETED
            
            return RunResult(
                run_id=context.run_id,
                session_id=context.session_id,
                status="success",
                response=context.assistant_response,
                tool_calls=[
                    {"name": tr.tool_name, "result": tr.result}
                    for tr in context.tool_results
                ],
                started_at=context.started_at,
                tokens_used=context.tokens_used,
                iterations=context.iteration,
            )
            
    async def _phase_intake(self, context: RunContext) -> None:
        """
        Intake 阶段：接收和预处理输入
        
        Args:
            context: 运行上下文
        """
        # 第一次迭代使用原始输入
        if context.iteration == 1:
            return
            
        # 后续迭代检查队列中的新消息
        if self._config.queue_mode == QueueMode.STEER:
            try:
                new_input = self._message_queue.get_nowait()
                context.user_input = new_input
            except asyncio.QueueEmpty:
                pass
                
    async def _phase_context_assembly(self, context: RunContext) -> None:
        """
        Context Assembly 阶段：构建上下文
        
        Args:
            context: 运行上下文
        """
        # 获取会话
        session = await self._session_store.get_session(context.session_id)
        
        # 使用 ContextBuilder 构建上下文
        agent_context = await self._context_builder.build(
            session=session,
            user_input=context.user_input,
            tool_results=context.tool_results if context.iteration > 1 else None,
            parameters=context.parameters,
        )
        
        context.context = agent_context
        
    async def _phase_inference(self, context: RunContext) -> None:
        """
        Inference 阶段：模型推理
        
        支持流式输出，通过 StreamHandler 发射事件。
        
        Args:
            context: 运行上下文
        """
        if not self._inference_func:
            raise RuntimeError("推理函数未设置")
            
        if not context.context:
            raise RuntimeError("上下文未构建")
            
        # 执行推理（流式）
        response_chunks = []
        tool_calls = []
        
        async for chunk in self._inference_func(context.context):
            # 处理响应块
            if isinstance(chunk, str):
                response_chunks.append(chunk)
                context.streaming_chunks.append(chunk)
                
                # 发射流式事件
                if self._config.enable_streaming:
                    await self._stream_handler.emit_assistant_delta(
                        chunk,
                        metadata={"iteration": context.iteration},
                    )
                    
            elif isinstance(chunk, dict):
                # 工具调用
                if chunk.get("type") == "tool_call":
                    tool_calls.append(chunk)
                # Token 统计
                elif chunk.get("type") == "usage":
                    context.tokens_used += chunk.get("tokens", 0)
                # 其他类型的流式数据
                elif chunk.get("type") == "delta":
                    delta_content = chunk.get("content", "")
                    if delta_content:
                        response_chunks.append(delta_content)
                        context.streaming_chunks.append(delta_content)
                        if self._config.enable_streaming:
                            await self._stream_handler.emit_assistant_delta(
                                delta_content,
                                metadata={"iteration": context.iteration},
                            )
                    
        # 合并响应
        context.assistant_response = "".join(response_chunks)
        
        # 解析工具调用
        context.pending_tool_calls = [
            self._tool_executor.parse_tool_call(tc)
            for tc in tool_calls
        ]
        
    async def _phase_tool_execution(self, context: RunContext) -> None:
        """
        Tool Execution 阶段：执行工具调用
        
        通过 StreamHandler 发射工具事件。
        
        Args:
            context: 运行上下文
        """
        for tool_call in context.pending_tool_calls:
            if context.tool_calls_count >= self._config.max_tool_calls_per_turn:
                self.logger.warning("达到单轮工具调用上限")
                break
                
            # 触发 before_tool_call 钩子
            await self._emit_hook("before_tool_call", context)
            
            # 发射工具开始事件
            await self._stream_handler.emit_tool_start(
                tool_name=tool_call.tool_name,
                call_id=tool_call.call_id,
                arguments=tool_call.arguments,
                metadata={"iteration": context.iteration},
            )
            
            # 执行工具
            result = await self._tool_executor.execute(tool_call)
            context.tool_results.append(result)
            context.tool_calls_count += 1
            
            # 发射工具结束事件
            await self._stream_handler.emit_tool_end(
                tool_name=tool_call.tool_name,
                call_id=tool_call.call_id,
                result=result.result if result.status.value == "success" else result.error,
                status=result.status.value,
                metadata={
                    "duration_ms": result.duration_ms,
                    "iteration": context.iteration,
                },
            )
            
            # 触发 after_tool_call 钩子
            await self._emit_hook("after_tool_call", context)
            
            # 检查 steer 模式下是否有新消息
            if self._config.queue_mode == QueueMode.STEER:
                if not self._message_queue.empty():
                    # 标记剩余工具调用为跳过
                    self.logger.info("检测到新消息，中断工具执行")
                    break
                    
        # 清空待处理工具调用
        context.pending_tool_calls.clear()
        
    async def _phase_persistence(self, context: RunContext) -> None:
        """
        Persistence 阶段：持久化结果
        
        Args:
            context: 运行上下文
        """
        from orb.agent.infrastructure.session_store import (
            SessionMessage,
            MessageRole,
        )
        
        # 保存用户消息
        user_message = SessionMessage(
            role=MessageRole.USER,
            content=context.user_input,
            metadata={"run_id": context.run_id},
        )
        await self._session_store.append_message(context.session_id, user_message)
        
        # 保存工具调用结果
        for result in context.tool_results:
            tool_message = SessionMessage(
                role=MessageRole.TOOL,
                content=str(result.result),
                tool_call_id=result.call_id,
                tool_name=result.tool_name,
                tool_result=result.to_dict(),
            )
            await self._session_store.append_message(context.session_id, tool_message)
            
        # 保存助手响应
        assistant_message = SessionMessage(
            role=MessageRole.ASSISTANT,
            content=context.assistant_response,
            metadata={
                "run_id": context.run_id,
                "tokens_used": context.tokens_used,
                "iterations": context.iteration,
            },
        )
        await self._session_store.append_message(context.session_id, assistant_message)
        
        # 更新 token 计数
        await self._session_store.update_token_count(
            context.session_id,
            context.tokens_used,
        )
        
        # 检查是否需要压缩
        session = await self._session_store.get_session(context.session_id)
        if session and len(session.messages) > self._config.compaction_threshold:
            self.logger.info(f"会话消息数超过阈值，考虑压缩: {context.session_id}")
            # 压缩逻辑可以在这里触发
            
    def abort(self) -> None:
        """中止当前运行"""
        self._abort_signal.set()
        
    async def enqueue_message(self, message: str) -> None:
        """
        将消息加入队列
        
        Args:
            message: 消息内容
        """
        await self._message_queue.put(message)
        
    def clear_queue(self) -> None:
        """清空消息队列"""
        while not self._message_queue.empty():
            try:
                self._message_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
                
    async def wait_for_completion(self, timeout: Optional[float] = None) -> bool:
        """
        等待当前运行完成
        
        Args:
            timeout: 超时时间
            
        Returns:
            是否成功完成
        """
        start = asyncio.get_event_loop().time()
        
        while self.is_running:
            if timeout:
                elapsed = asyncio.get_event_loop().time() - start
                if elapsed >= timeout:
                    return False
            await asyncio.sleep(0.1)
            
        return True
        
    def subscribe_events(self, callback: Callable[[StreamEvent], Any]) -> None:
        """
        订阅所有流事件
        
        Args:
            callback: 事件回调函数
        """
        self._stream_handler.subscribe(callback)
        
    def unsubscribe_events(self, callback: Callable[[StreamEvent], Any]) -> None:
        """
        取消订阅流事件
        
        Args:
            callback: 事件回调函数
        """
        self._stream_handler.unsubscribe(callback)
        
    async def events(self) -> AsyncIterator[StreamEvent]:
        """
        异步迭代流事件
        
        Yields:
            流事件
        """
        async for event in self._stream_handler.events():
            yield event
            
    def get_run_by_id(self, run_id: str) -> Optional[RunResult]:
        """
        通过 ID 获取运行结果
        
        Args:
            run_id: 运行 ID
            
        Returns:
            运行结果
        """
        for result in self._run_history:
            if result.run_id == run_id:
                return result
        return None
        
    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息
        
        Returns:
            统计信息
        """
        total_runs = len(self._run_history)
        success_runs = sum(1 for r in self._run_history if r.status == "success")
        error_runs = sum(1 for r in self._run_history if r.status == "error")
        total_tokens = sum(r.tokens_used for r in self._run_history)
        total_iterations = sum(r.iterations for r in self._run_history)
        
        return {
            "state": self._state.value,
            "total_runs": total_runs,
            "success_runs": success_runs,
            "error_runs": error_runs,
            "success_rate": success_runs / total_runs if total_runs > 0 else 0,
            "total_tokens": total_tokens,
            "total_iterations": total_iterations,
            "avg_iterations": total_iterations / total_runs if total_runs > 0 else 0,
            "current_run": self._current_run.run_id if self._current_run else None,
        }


# ============== 便捷函数 ==============

def create_agent_loop(
    context_builder: "ContextBuilder",
    tool_executor: "ToolExecutor",
    session_store: "SessionStore",
    inference_func: Optional[InferenceFunc] = None,
    config: Optional[LoopConfig] = None,
    stream_handler: Optional[StreamHandler] = None,
) -> AgentLoop:
    """
    创建 Agent Loop
    
    Args:
        context_builder: 上下文构建器
        tool_executor: 工具执行器
        session_store: 会话存储
        inference_func: 推理函数
        config: 配置
        stream_handler: 流处理器
        
    Returns:
        AgentLoop 实例
    """
    return AgentLoop(
        config=config or LoopConfig(),
        context_builder=context_builder,
        tool_executor=tool_executor,
        session_store=session_store,
        inference_func=inference_func,
        stream_handler=stream_handler,
    )


async def run_single_turn(
    loop: AgentLoop,
    session_id: str,
    user_input: str,
    **kwargs,
) -> str:
    """
    执行单轮对话
    
    Args:
        loop: Agent Loop
        session_id: 会话 ID
        user_input: 用户输入
        **kwargs: 其他参数
        
    Returns:
        助手响应
    """
    result = await loop.run(
        session_id=session_id,
        user_input=user_input,
        **kwargs,
    )
    
    if result.status == "success":
        return result.response
    elif result.error:
        return f"Error: {result.error}"
    else:
        return f"Status: {result.status}"
