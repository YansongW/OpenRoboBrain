"""
OpenRoboBrain 核心入口

提供系统的统一入口和生命周期管理。
支持用户自然语言输入，异步返回对话(chat)和ROS2控制消息。

两种处理模式:
- LLM 模式: AgentLoop -> LLM 推理 -> Memory 检索 -> Compaction（需要 API Key）
- 规则模式: BehaviorExecutor -> 规则匹配（无需 API Key，开发调试用）
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from uuid import uuid4

from orb.system.services.config_center import ConfigCenter
from orb.system.services.logger import get_logger

if TYPE_CHECKING:
    from orb.agent.super.super_agent import SuperAgent
    from orb.agent.runtime.agent_loop import AgentLoop
    from orb.agent.runtime.llm_inference import LLMInferenceAdapter
    from orb.agent.runtime.context_builder import ContextBuilder
    from orb.agent.runtime.tool_executor import ToolExecutor
    from orb.agent.infrastructure.session_store import SessionStore
    from orb.agent.infrastructure.session_compactor import SessionCompactor
    from orb.system.brain_pipeline.message_bus import MessageBus
    from orb.system.brain_pipeline.brain_cerebellum_bridge import (
        BrainCerebellumBridge,
        BrainCommand,
    )
    from orb.system.llm.base import BaseLLM
    from orb.behavior.executor import BehaviorExecutor
    from orb.behavior.base import BehaviorResult
    from orb.data.memory.memory_stream import MemoryStream
    from orb.data.memory.memory_ranker import MemoryRanker

logger = get_logger(__name__)


@dataclass
class ProcessResult:
    """
    处理结果
    
    包含对话响应和ROS2命令，实现双输出。
    """
    trace_id: str                              # 请求追踪ID
    chat_response: str                         # 对话输出
    ros2_commands: List["BrainCommand"] = field(default_factory=list)  # ROS2命令列表
    behavior_name: str = ""                    # 执行的行为名称
    behavior_result: Optional["BehaviorResult"] = None  # 行为执行结果
    success: bool = True                       # 是否成功
    error: Optional[str] = None                # 错误信息
    execution_time_ms: float = 0.0             # 执行时间(毫秒)
    mode: str = ""                             # 处理模式: "llm" 或 "rule"
    metadata: Dict[str, Any] = field(default_factory=dict)  # 元数据
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "trace_id": self.trace_id,
            "chat_response": self.chat_response,
            "ros2_commands": [cmd.to_dict() if hasattr(cmd, 'to_dict') else str(cmd) for cmd in self.ros2_commands],
            "behavior_name": self.behavior_name,
            "success": self.success,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "mode": self.mode,
            "metadata": self.metadata,
        }


class OpenRoboBrain:
    """
    OpenRoboBrain 系统主类
    
    负责整个系统的初始化、启动和关闭。
    提供统一的process()入口，接收自然语言输入，返回对话和ROS2命令。
    
    两种模式:
    - LLM 模式: 完整 AgentLoop 管线 (需要配置 LLM API Key)
    - 规则模式: BehaviorExecutor 规则匹配 (无需 API Key)
    """
    
    def __init__(
        self,
        config_path: Optional[str] = None,
        mock_ros2: bool = True,
    ):
        """
        初始化 OpenRoboBrain 系统
        
        Args:
            config_path: 配置文件路径，默认使用 configs/system.yaml
            mock_ros2: 是否使用模拟ROS2（默认True，开发调试用）
        """
        self.config_path = config_path or "configs/system.yaml"
        self.mock_ros2 = mock_ros2
        self.config: Optional[ConfigCenter] = None
        
        # 系统层
        self._message_bus: Optional["MessageBus"] = None
        self._bridge: Optional["BrainCerebellumBridge"] = None
        
        # Agent 层
        self._super_agent: Optional["SuperAgent"] = None
        self._llm: Optional["BaseLLM"] = None
        self._agent_loop: Optional["AgentLoop"] = None
        self._inference_adapter: Optional["LLMInferenceAdapter"] = None
        self._context_builder: Optional["ContextBuilder"] = None
        self._tool_executor: Optional["ToolExecutor"] = None
        self._session_store: Optional["SessionStore"] = None
        self._session_compactor: Optional["SessionCompactor"] = None
        
        # 行为层
        self._behavior_executor: Optional["BehaviorExecutor"] = None
        
        # 记忆系统
        self._memory_stream: Optional["MemoryStream"] = None
        self._memory_ranker: Optional["MemoryRanker"] = None
        
        # 广播器
        self._broadcaster = None
        
        # 状态
        self._running = False
        self._llm_available = False
        self._main_session_id: Optional[str] = None
        
    async def initialize(self) -> None:
        """初始化系统所有组件"""
        logger.info("正在初始化 OpenRoboBrain 系统...")
        
        # 1. 加载配置
        self.config = ConfigCenter(self.config_path)
        await self.config.load()
        logger.info("配置加载完成")
        
        # 2. 初始化系统层 - 大脑管道
        from orb.system.brain_pipeline.message_bus import MessageBus
        self._message_bus = MessageBus(self.config)
        await self._message_bus.initialize()
        logger.info("大脑管道初始化完成")
        
        # 3. 初始化Agent层 - Super Agent
        from orb.agent.super.super_agent import SuperAgent
        self._super_agent = SuperAgent(self._message_bus, self.config)
        await self._super_agent.initialize()
        logger.info("Super Agent 初始化完成")
        
        # 4. 初始化行为层 - BehaviorExecutor (规则模式 fallback)
        from orb.behavior.executor import BehaviorExecutor
        from orb.behavior.registry import get_registry
        self._behavior_executor = BehaviorExecutor(registry=get_registry())
        logger.info("行为执行器初始化完成")
        
        # 5. 初始化桥接层 - Brain-Cerebellum Bridge
        from orb.system.brain_pipeline.brain_cerebellum_bridge import (
            BrainCerebellumBridge,
        )
        self._bridge = BrainCerebellumBridge(mock_mode=self.mock_ros2)
        await self._bridge.initialize()
        mode_str = "模拟模式" if self.mock_ros2 else "真实模式"
        logger.info(f"大脑-小脑桥接器初始化完成 ({mode_str})")
        
        # 6. 尝试初始化 LLM 管线 (如果 API Key 可用)
        await self._try_init_llm_pipeline()
        
        # 7. 初始化记忆系统
        self._init_memory_system()
        
        # 8. 启动命令广播器 (WebSocket, 供 ROS2 监控和 MuJoCo 仿真订阅)
        try:
            from orb.system.brain_pipeline.command_broadcaster import get_broadcaster
            self._broadcaster = get_broadcaster()
            await self._broadcaster.start()
        except Exception as e:
            logger.debug(f"命令广播器启动跳过: {e}")
        
        # 9. 注册 Memory 工具到 ToolExecutor (如果 LLM 管线可用)
        if self._tool_executor and self._memory_stream:
            from orb.system.tools.builtin.memory import register_memory_tools
            register_memory_tools(
                self._tool_executor,
                memory_stream=self._memory_stream,
                memory_ranker=self._memory_ranker,
            )
            logger.info("Memory 工具已注册到 ToolExecutor")
        
        logger.info("OpenRoboBrain 系统初始化完成")
        
    async def _try_init_llm_pipeline(self) -> None:
        """
        尝试初始化 LLM 管线
        
        如果 LLM API Key 可用，创建完整的 AgentLoop 管线。
        如果不可用，系统降级到规则模式。
        """
        try:
            llm = self._create_llm_from_env()
            if llm is None:
                logger.info("未检测到 LLM API Key，使用规则模式")
                return
            
            self._llm = llm
            logger.info(f"LLM 初始化成功: {llm.model}")
            
            # 创建 SessionStore (内存模式)
            from orb.agent.infrastructure.session_store import SessionStore
            from pathlib import Path
            import tempfile
            sessions_dir = Path(tempfile.gettempdir()) / "orb_sessions"
            self._session_store = SessionStore(
                sessions_dir=sessions_dir,
                agent_id="main",
            )
            
            # 创建主会话
            session = await self._session_store.create_session(
                session_key="agent:main:main",
            )
            self._main_session_id = session.session_id
            
            # 创建 ToolExecutor 并注册 Memory 工具
            from orb.agent.runtime.tool_executor import ToolExecutor
            self._tool_executor = ToolExecutor()
            
            # Memory 工具将在 _init_memory_system() 后注册
            
            # 创建 ContextBuilder
            from orb.agent.runtime.context_builder import ContextBuilder, ContextConfig
            self._context_builder = ContextBuilder(
                config=ContextConfig(
                    base_system_prompt=self._get_system_prompt(),
                    inject_bootstrap=False,  # MVP 阶段不注入 bootstrap 文件
                ),
            )
            
            # 创建 LLMInferenceAdapter
            from orb.agent.runtime.llm_inference import LLMInferenceAdapter
            self._inference_adapter = LLMInferenceAdapter(
                llm=self._llm,
                use_streaming=True,
            )
            
            # 创建 AgentLoop
            from orb.agent.runtime.agent_loop import AgentLoop, LoopConfig
            self._agent_loop = AgentLoop(
                config=LoopConfig(
                    max_iterations=10,
                    timeout_seconds=120.0,
                    enable_streaming=True,
                    enable_tool_calls=True,
                ),
                context_builder=self._context_builder,
                tool_executor=self._tool_executor,
                session_store=self._session_store,
                inference_func=self._inference_adapter.inference_func,
            )
            
            # 创建 SessionCompactor
            from orb.agent.infrastructure.session_compactor import (
                SessionCompactor,
                CompactionConfig,
            )
            self._session_compactor = SessionCompactor(
                config=CompactionConfig(
                    context_window=getattr(llm, 'capabilities', None) 
                        and llm.capabilities.max_context_length or 128000,
                ),
                llm=self._llm,
            )
            
            self._llm_available = True
            logger.info("LLM 管线初始化完成 (AgentLoop + Inference + Compaction)")
            
        except Exception as e:
            logger.warning(f"LLM 管线初始化失败，使用规则模式: {e}")
            self._llm_available = False
    
    def _create_llm_from_env(self) -> Optional["BaseLLM"]:
        """
        从环境变量创建 LLM 实例
        
        优先级: Ollama (本地) -> OPENAI_API_KEY -> DEEPSEEK_API_KEY -> ...
        """
        from orb.system.llm.factory import LLMFactory
        from orb.system.llm.config import ProviderConfig, OPENAI_COMPATIBLE_ENDPOINTS
        
        # 1. 优先检查 Ollama (本地模型，无需 API Key)
        ollama_model = os.environ.get("OLLAMA_MODEL")
        ollama_base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        
        if ollama_model:
            # 显式指定了 Ollama 模型
            try:
                llm = LLMFactory.create(
                    "ollama",
                    model=ollama_model,
                    base_url=ollama_base_url,
                )
                logger.info(f"使用 Ollama 本地模型: {ollama_model} ({ollama_base_url})")
                return llm
            except Exception as e:
                logger.warning(f"Ollama 创建失败: {e}")
        else:
            # 自动探测本地 Ollama 服务
            try:
                import urllib.request
                req = urllib.request.Request(f"{ollama_base_url}/api/tags", method="GET")
                with urllib.request.urlopen(req, timeout=2) as resp:
                    if resp.status == 200:
                        import json as _json
                        data = _json.loads(resp.read())
                        models = data.get("models", [])
                        if models:
                            # 优先选择 qwen 系列, 其次任意可用模型
                            model_names = [m.get("name", "") for m in models]
                            chosen = None
                            for preferred in ["qwen2.5:3b", "qwen3:8b", "qwen2.5:7b", "llama3.1:8b"]:
                                if preferred in model_names:
                                    chosen = preferred
                                    break
                            if not chosen:
                                chosen = model_names[0]
                            
                            llm = LLMFactory.create(
                                "ollama",
                                model=chosen,
                                base_url=ollama_base_url,
                            )
                            logger.info(f"自动检测到 Ollama 本地模型: {chosen}")
                            return llm
            except Exception:
                pass  # Ollama 不可用，继续检查云端 API
        
        # 2. 检查云端 API Key
        providers = [
            ("openai", "OPENAI_API_KEY", None, "gpt-4o"),
            ("deepseek", "DEEPSEEK_API_KEY", OPENAI_COMPATIBLE_ENDPOINTS.get("deepseek"), "deepseek-chat"),
            ("kimi", "KIMI_API_KEY", OPENAI_COMPATIBLE_ENDPOINTS.get("kimi"), "moonshot-v1-128k"),
            ("glm", "GLM_API_KEY", OPENAI_COMPATIBLE_ENDPOINTS.get("glm"), "glm-4-flash"),
            ("qwen", "QWEN_API_KEY", OPENAI_COMPATIBLE_ENDPOINTS.get("qwen"), "qwen-turbo"),
        ]
        
        for provider_name, env_var, base_url, default_model in providers:
            api_key = os.environ.get(env_var)
            if api_key and not api_key.startswith("sk-xxx"):
                try:
                    config = ProviderConfig(
                        api_key=api_key,
                        model=default_model,
                        base_url=base_url,
                    )
                    llm = LLMFactory.create(provider_name, config)
                    logger.info(f"使用 LLM Provider: {provider_name} (model: {default_model})")
                    return llm
                except Exception as e:
                    logger.debug(f"创建 {provider_name} LLM 失败: {e}")
                    continue
        
        return None
    
    def _init_memory_system(self) -> None:
        """初始化记忆系统"""
        from orb.data.memory.memory_stream import MemoryStream
        from orb.data.memory.memory_ranker import MemoryRanker
        
        self._memory_stream = MemoryStream(agent_id="main")
        self._memory_ranker = MemoryRanker()
        
        logger.info("记忆系统初始化完成 (MemoryStream + MemoryRanker)")
    
    def _get_system_prompt(self) -> str:
        """获取系统提示词"""
        return """你是 OpenRoboBrain，一个具身智能服务机器人的大脑系统。

你的能力:
- 理解用户的自然语言指令
- 将指令转化为具体的机器人动作（导航、抓取、放置等）
- 进行友好的对话

请以 JSON 格式回复，包含:
{
    "chat_response": "给用户的自然语言回复",
    "ros2_commands": [
        {"command_type": "命令类型", "parameters": {"参数": "值"}}
    ]
}

如果不需要机器人动作，ros2_commands 为空数组 []。
可用的命令类型: navigate, grasp, place, pour, stop, patrol, clean"""
        
    async def start(self) -> None:
        """启动系统"""
        if self._running:
            logger.warning("系统已在运行中")
            return
            
        logger.info("正在启动 OpenRoboBrain 系统...")
        self._running = True
        
        # 启动 Super Agent
        if self._super_agent:
            await self._super_agent.start()
            
        logger.info(
            f"OpenRoboBrain 系统启动完成 "
            f"(模式: {'LLM' if self._llm_available else '规则'})"
        )
        
    async def stop(self) -> None:
        """停止系统"""
        if not self._running:
            return
            
        logger.info("正在停止 OpenRoboBrain 系统...")
        self._running = False
        
        # 保存记忆
        if self._memory_stream and self._memory_stream.size > 0:
            try:
                save_path = Path("data/memory_backup.json")
                self._memory_stream.save_to_json(save_path)
                logger.info(f"记忆已保存: {self._memory_stream.size} 条")
            except Exception as e:
                logger.warning(f"保存记忆失败: {e}")
        
        # 停止广播器
        if self._broadcaster:
            await self._broadcaster.stop()
        
        # 停止桥接器
        if self._bridge:
            await self._bridge.shutdown()
            
        # 停止 Super Agent
        if self._super_agent:
            await self._super_agent.stop()
            
        # 关闭大脑管道
        if self._message_bus:
            await self._message_bus.shutdown()
            
        logger.info("OpenRoboBrain 系统已停止")
    
    async def process(
        self,
        user_input: str,
        parameters: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
    ) -> ProcessResult:
        """
        处理用户输入
        
        接收自然语言输入，异步返回对话(chat)和ROS2控制消息。
        
        有 LLM 时走完整 AgentLoop 管线，
        无 LLM 时走 BehaviorExecutor 规则模式。
        
        Args:
            user_input: 用户自然语言输入
            parameters: 额外参数
            trace_id: 追踪ID（可选，自动生成）
            
        Returns:
            ProcessResult: 包含chat_response和ros2_commands
        """
        trace_id = trace_id or f"trace-{uuid4().hex[:8]}"
        start_time = datetime.now()
        
        logger.info(f"[{trace_id}] 收到用户输入: {user_input[:100]}...")
        
        result = ProcessResult(
            trace_id=trace_id,
            chat_response="",
            ros2_commands=[],
        )
        
        try:
            if not self._running:
                raise RuntimeError("OpenRoboBrain系统未启动")
            
            # 根据 LLM 可用性选择处理路径
            if self._llm_available and self._agent_loop:
                result = await self._process_with_llm(user_input, parameters, trace_id)
            else:
                result = await self._process_with_rules(user_input, parameters, trace_id)
                
        except Exception as e:
            logger.error(f"[{trace_id}] 处理失败: {e}")
            result.success = False
            result.error = str(e)
            result.chat_response = f"处理请求时发生错误: {e}"
            
        finally:
            end_time = datetime.now()
            result.execution_time_ms = (end_time - start_time).total_seconds() * 1000
            logger.info(
                f"[{trace_id}] 处理完成 (模式={result.mode}, "
                f"耗时={result.execution_time_ms:.2f}ms)"
            )
        
        return result
    
    async def _process_with_llm(
        self,
        user_input: str,
        parameters: Optional[Dict[str, Any]],
        trace_id: str,
    ) -> ProcessResult:
        """
        LLM 模式处理: AgentLoop -> LLM -> Memory -> Compaction
        """
        result = ProcessResult(
            trace_id=trace_id,
            chat_response="",
            ros2_commands=[],
            mode="llm",
        )
        
        # 1. 记忆检索 - 用 MemoryRanker 找到相关记忆
        memory_context = ""
        if self._memory_stream and self._memory_ranker and self._memory_stream.size > 0:
            ranked = self._memory_ranker.rank(
                query=user_input,
                candidates=self._memory_stream.get_all(),
                recently_activated=self._memory_stream.recently_activated,
                top_k=5,
            )
            if ranked:
                memory_lines = [
                    f"- {r.memory.description} (相关度: {r.final_score:.2f})"
                    for r in ranked
                ]
                memory_context = "\n相关记忆:\n" + "\n".join(memory_lines)
                logger.info(f"[{trace_id}] 检索到 {len(ranked)} 条相关记忆")
        
        # 2. 注入记忆到系统提示词
        if memory_context and self._context_builder:
            from orb.agent.runtime.context_builder import ContextConfig
            self._context_builder._config.base_system_prompt = (
                self._get_system_prompt() + memory_context
            )
        
        # 3. 通过 AgentLoop 执行
        run_result = await self._agent_loop.run(
            session_id=self._main_session_id or "default",
            user_input=user_input,
            agent_id="main",
            metadata={"trace_id": trace_id, "parameters": parameters or {}},
        )
        
        # 4. 解析 AgentLoop 结果
        if run_result.status == "success":
            response_text = run_result.response
            
            # 尝试解析 JSON 格式响应
            parsed = self._parse_llm_response(response_text)
            result.chat_response = parsed.get("chat_response", response_text)
            
            # 提取 ROS2 命令
            ros2_cmds = parsed.get("ros2_commands", [])
            if ros2_cmds:
                await self._send_ros2_commands(ros2_cmds, trace_id, result)
            
            result.success = True
            result.metadata["tokens_used"] = run_result.tokens_used
            result.metadata["iterations"] = run_result.iterations
        else:
            result.success = False
            result.error = run_result.error
            result.chat_response = f"处理失败: {run_result.error}"
        
        # 5. 存储新记忆
        if self._memory_stream and result.success:
            from orb.data.memory.memory_stream import MemoryType
            self._memory_stream.create_and_add(
                description=f"用户: {user_input[:100]}",
                memory_type=MemoryType.OBSERVATION,
                importance=5.0,
                session_id=self._main_session_id or "",
                metadata={"trace_id": trace_id},
            )
            if result.chat_response:
                self._memory_stream.create_and_add(
                    description=f"助手: {result.chat_response[:100]}",
                    memory_type=MemoryType.OBSERVATION,
                    importance=4.0,
                    session_id=self._main_session_id or "",
                    metadata={"trace_id": trace_id},
                )
        
        # 6. 检查是否需要 compaction
        if self._session_compactor and self._session_store and self._main_session_id:
            session = await self._session_store.get_session(self._main_session_id)
            if session and self._session_compactor.should_compact(session.messages):
                logger.info(f"[{trace_id}] 触发会话压缩...")
                compact_result = await self._session_compactor.compact(session.messages)
                if compact_result.success:
                    logger.info(
                        f"[{trace_id}] 压缩完成: "
                        f"{compact_result.original_tokens} -> {compact_result.compacted_tokens} tokens"
                    )
        
        return result
    
    async def _process_with_rules(
        self,
        user_input: str,
        parameters: Optional[Dict[str, Any]],
        trace_id: str,
    ) -> ProcessResult:
        """
        规则模式处理: BehaviorExecutor -> 规则匹配 (无需 LLM)
        """
        result = ProcessResult(
            trace_id=trace_id,
            chat_response="",
            ros2_commands=[],
            mode="rule",
        )
        
        if self._behavior_executor:
            from orb.behavior.base import BehaviorStatus
            
            logger.info(f"[{trace_id}] 执行行为匹配 (规则模式)...")
            behavior_result = await self._behavior_executor.auto_execute(
                user_input=user_input,
                parameters=parameters,
                trace_id=trace_id,
            )
            
            result.behavior_name = behavior_result.behavior_name
            result.behavior_result = behavior_result
            
            if behavior_result.status == BehaviorStatus.COMPLETED:
                behavior_data = behavior_result.result or {}
                result.chat_response = behavior_data.get(
                    "chat_response",
                    f"已完成{behavior_result.behavior_name}任务"
                )
                
                ros2_cmds = behavior_data.get("ros2_commands", [])
                if ros2_cmds:
                    await self._send_ros2_commands(ros2_cmds, trace_id, result)
                
                result.success = True
            else:
                result.success = False
                result.error = behavior_result.error or "行为执行失败"
                result.chat_response = f"抱歉，执行失败: {result.error}"
        else:
            result.chat_response = "系统正在初始化中，请稍后再试"
            result.success = False
            result.error = "行为执行器未初始化"
        
        # 规则模式也存储记忆
        if self._memory_stream and result.success:
            from orb.data.memory.memory_stream import MemoryType
            self._memory_stream.create_and_add(
                description=f"用户: {user_input[:100]}",
                memory_type=MemoryType.OBSERVATION,
                importance=5.0,
                metadata={"trace_id": trace_id, "mode": "rule"},
            )
        
        return result
    
    async def _send_ros2_commands(
        self,
        ros2_cmds: List[Dict[str, Any]],
        trace_id: str,
        result: ProcessResult,
    ) -> None:
        """发送 ROS2 命令到 Bridge 并广播到 WebSocket"""
        from orb.system.brain_pipeline.brain_cerebellum_bridge import BrainCommand
        
        for cmd_data in ros2_cmds:
            if isinstance(cmd_data, dict):
                cmd = BrainCommand(
                    command_type=cmd_data.get("command_type", ""),
                    parameters=cmd_data.get("parameters", {}),
                    source_agent="OpenRoboBrain",
                )
                result.ros2_commands.append(cmd)
                
                # 发送到 Bridge
                if self._bridge:
                    logger.info(f"[{trace_id}] 发送ROS2命令: {cmd.command_type}")
                    await self._bridge.send_command(cmd)
                
                # 广播到 WebSocket (供 ROS2 监控和 MuJoCo 仿真)
                if self._broadcaster and self._broadcaster.is_running:
                    await self._broadcaster.broadcast_command(cmd.to_dict())
    
    def _parse_llm_response(self, response_text: str) -> Dict[str, Any]:
        """解析 LLM 响应 (可能是 JSON 或纯文本)"""
        import re
        
        # 尝试直接 JSON 解析
        try:
            data = json.loads(response_text)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, TypeError):
            pass
        
        # 尝试从代码块提取 JSON
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', response_text)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                if isinstance(data, dict):
                    return data
            except (json.JSONDecodeError, TypeError):
                pass
        
        # 纯文本回退
        return {"chat_response": response_text, "ros2_commands": []}
    
    async def run(self) -> None:
        """运行系统（阻塞直到收到停止信号）"""
        await self.initialize()
        await self.start()
        
        try:
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()
            
    # ============== 属性访问 ==============
    
    @property
    def message_bus(self) -> Optional["MessageBus"]:
        return self._message_bus
        
    @property
    def super_agent(self) -> Optional["SuperAgent"]:
        return self._super_agent
    
    @property
    def behavior_executor(self) -> Optional["BehaviorExecutor"]:
        return self._behavior_executor
    
    @property
    def bridge(self) -> Optional["BrainCerebellumBridge"]:
        return self._bridge
    
    @property
    def agent_loop(self) -> Optional["AgentLoop"]:
        return self._agent_loop
    
    @property
    def memory_stream(self) -> Optional["MemoryStream"]:
        return self._memory_stream
    
    @property
    def memory_ranker(self) -> Optional["MemoryRanker"]:
        return self._memory_ranker
    
    @property
    def llm(self) -> Optional["BaseLLM"]:
        return self._llm
    
    @property
    def llm_available(self) -> bool:
        return self._llm_available
    
    @property
    def is_running(self) -> bool:
        return self._running
