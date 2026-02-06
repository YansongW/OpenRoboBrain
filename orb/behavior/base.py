"""
行为基类

定义行为的基本结构和生命周期。
支持与Agent层（Orchestrator）的连接，收集BrainCommand。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING
from uuid import uuid4

from orb.system.services.logger import BehaviorLoggerMixin, trace_context, Layer

if TYPE_CHECKING:
    from orb.data.explicit.workflow_memory import WorkflowMemory
    from orb.agent.orchestrator.orchestrator import OrchestratorAgent
    from orb.system.brain_pipeline.brain_cerebellum_bridge import BrainCommand


class BehaviorStatus(Enum):
    """行为状态"""
    IDLE = "idle"               # 空闲
    PREPARING = "preparing"     # 准备中
    EXECUTING = "executing"     # 执行中
    COMPLETED = "completed"     # 已完成
    FAILED = "failed"           # 失败
    CANCELLED = "cancelled"     # 已取消


@dataclass
class BehaviorConfig:
    """行为配置"""
    # 基本信息
    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    
    # 能力组合
    required_capabilities: List[str] = field(default_factory=list)
    
    # 执行配置
    timeout_seconds: float = 300.0
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    
    # 工作流记忆关联
    enable_workflow_memory: bool = True
    min_success_rate: float = 0.7  # 最小成功率才认为行为可用
    
    # 元数据
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BehaviorResult:
    """行为执行结果"""
    behavior_id: str
    behavior_name: str
    status: BehaviorStatus = BehaviorStatus.COMPLETED
    result: Any = None
    error: Optional[str] = None
    started_at: str = ""
    ended_at: str = field(default_factory=lambda: datetime.now().isoformat())
    duration_ms: float = 0.0
    
    # 执行详情
    steps_executed: List[Dict[str, Any]] = field(default_factory=list)
    capabilities_used: List[str] = field(default_factory=list)
    
    # 工作流记忆
    workflow_matched: bool = False  # 是否匹配到已有工作流
    workflow_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "behavior_id": self.behavior_id,
            "behavior_name": self.behavior_name,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_ms": self.duration_ms,
            "steps_executed": self.steps_executed,
            "capabilities_used": self.capabilities_used,
            "workflow_matched": self.workflow_matched,
            "workflow_id": self.workflow_id,
        }


@dataclass
class BehaviorContext:
    """行为执行上下文"""
    behavior_id: str = field(default_factory=lambda: str(uuid4()))
    request_id: str = ""
    trace_id: str = ""  # 追踪ID，用于日志关联
    user_input: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    
    # 工作流信息
    workflow_id: Optional[str] = None
    workflow_matched: bool = False
    previous_steps: List[Dict[str, Any]] = field(default_factory=list)
    
    # 执行状态
    current_step: int = 0
    total_steps: int = 0
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # 收集的ROS2命令
    ros2_commands: List[Dict[str, Any]] = field(default_factory=list)
    
    # 对话响应
    chat_response: str = ""
    
    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_ros2_command(
        self,
        command_type: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> None:
        """添加ROS2命令"""
        self.ros2_commands.append({
            "command_type": command_type,
            "parameters": parameters or {},
        })


class Behavior(ABC, BehaviorLoggerMixin):
    """
    行为基类
    
    行为是多个原子能力的组合，代表可复用的复杂行为模式。
    子类需要实现 `execute` 方法来定义具体的行为逻辑。
    
    支持：
    - 与Orchestrator Agent连接
    - 收集ROS2命令（通过BehaviorContext）
    - 生成对话响应
    """
    
    def __init__(self, config: BehaviorConfig):
        """
        初始化行为
        
        Args:
            config: 行为配置
        """
        self._config = config
        self._status = BehaviorStatus.IDLE
        self._workflow_memory: Optional[WorkflowMemory] = None
        self._orchestrator: Optional["OrchestratorAgent"] = None
        
        # 生命周期钩子
        self._before_execute_hooks: List[Callable] = []
        self._after_execute_hooks: List[Callable] = []
        self._on_error_hooks: List[Callable] = []
        
    @property
    def name(self) -> str:
        """行为名称"""
        return self._config.name
    
    @property
    def description(self) -> str:
        """行为描述"""
        return self._config.description
    
    @property
    def config(self) -> BehaviorConfig:
        """配置"""
        return self._config
    
    @property
    def status(self) -> BehaviorStatus:
        """当前状态"""
        return self._status
    
    @property
    def required_capabilities(self) -> List[str]:
        """所需能力列表"""
        return self._config.required_capabilities
    
    def set_workflow_memory(self, memory: "WorkflowMemory") -> None:
        """设置工作流记忆"""
        self._workflow_memory = memory
    
    def set_orchestrator(self, orchestrator: "OrchestratorAgent") -> None:
        """设置编排Agent"""
        self._orchestrator = orchestrator
    
    @property
    def orchestrator(self) -> Optional["OrchestratorAgent"]:
        """获取编排Agent"""
        return self._orchestrator
    
    def register_before_hook(self, hook: Callable) -> None:
        """注册执行前钩子"""
        self._before_execute_hooks.append(hook)
    
    def register_after_hook(self, hook: Callable) -> None:
        """注册执行后钩子"""
        self._after_execute_hooks.append(hook)
    
    def register_error_hook(self, hook: Callable) -> None:
        """注册错误钩子"""
        self._on_error_hooks.append(hook)
    
    async def run(
        self,
        user_input: str,
        parameters: Optional[Dict[str, Any]] = None,
        context: Optional[BehaviorContext] = None,
        trace_id: Optional[str] = None,
    ) -> BehaviorResult:
        """
        运行行为
        
        Args:
            user_input: 用户输入
            parameters: 参数
            context: 执行上下文
            trace_id: 追踪ID
            
        Returns:
            执行结果
        """
        start_time = datetime.now()
        
        # 创建上下文
        ctx = context or BehaviorContext(
            user_input=user_input,
            parameters=parameters or {},
            trace_id=trace_id or f"trace-{uuid4().hex[:8]}",
        )
        
        # 如果提供了trace_id，更新上下文
        if trace_id:
            ctx.trace_id = trace_id
        
        result = BehaviorResult(
            behavior_id=ctx.behavior_id,
            behavior_name=self.name,
            started_at=ctx.started_at,
        )
        
        # 使用trace上下文
        with trace_context(trace_id=ctx.trace_id, layer=Layer.BEHAVIOR, component=self.name):
            try:
                # 准备阶段
                self._status = BehaviorStatus.PREPARING
                self.logger.info(f"开始执行行为: {self.name}")
                
                # 检查工作流记忆
                if self._config.enable_workflow_memory and self._workflow_memory:
                    workflow = await self._match_workflow(user_input, parameters)
                    if workflow:
                        ctx.workflow_matched = True
                        ctx.workflow_id = workflow["task_id"]
                        ctx.previous_steps = workflow.get("exec_history", [])
                        result.workflow_matched = True
                        result.workflow_id = workflow["task_id"]
                        self.logger.info(f"匹配到工作流: {workflow['task_id']}")
                
                # 执行前钩子
                for hook in self._before_execute_hooks:
                    await self._call_hook(hook, ctx)
                
                # 执行阶段
                self._status = BehaviorStatus.EXECUTING
                self.logger.info("执行行为逻辑...")
                
                # 执行行为逻辑
                exec_result = await self.execute(ctx)
                
                # 完成
                self._status = BehaviorStatus.COMPLETED
                result.status = BehaviorStatus.COMPLETED
                result.capabilities_used = self._config.required_capabilities
                
                # 合并执行结果，包含chat_response和ros2_commands
                if isinstance(exec_result, dict):
                    # 保留原始结果
                    result.result = exec_result
                    # 确保包含chat_response和ros2_commands
                    if "chat_response" not in exec_result:
                        exec_result["chat_response"] = ctx.chat_response
                    if "ros2_commands" not in exec_result:
                        exec_result["ros2_commands"] = ctx.ros2_commands
                else:
                    result.result = {
                        "data": exec_result,
                        "chat_response": ctx.chat_response,
                        "ros2_commands": ctx.ros2_commands,
                    }
                
                self.logger.info(f"行为执行完成，生成 {len(ctx.ros2_commands)} 个ROS2命令")
                
                # 执行后钩子
                for hook in self._after_execute_hooks:
                    await self._call_hook(hook, ctx, result)
                
                # 记录到工作流记忆
                if self._config.enable_workflow_memory and self._workflow_memory:
                    await self._record_execution(ctx, result)
                
            except Exception as e:
                self._status = BehaviorStatus.FAILED
                result.status = BehaviorStatus.FAILED
                result.error = str(e)
                self.logger.error(f"行为执行失败 {self.name}: {e}")
                
                # 错误钩子
                for hook in self._on_error_hooks:
                    await self._call_hook(hook, ctx, e)
                
                # 记录失败
                if self._config.enable_workflow_memory and self._workflow_memory:
                    await self._record_execution(ctx, result)
            
            finally:
                end_time = datetime.now()
                result.ended_at = end_time.isoformat()
                result.duration_ms = (end_time - start_time).total_seconds() * 1000
                self._status = BehaviorStatus.IDLE
                self.logger.info(f"行为耗时: {result.duration_ms:.2f}ms")
        
        return result
    
    @abstractmethod
    async def execute(self, context: BehaviorContext) -> Any:
        """
        执行行为逻辑（子类实现）
        
        Args:
            context: 执行上下文
            
        Returns:
            执行结果
        """
        pass
    
    async def _match_workflow(
        self,
        user_input: str,
        parameters: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """匹配工作流记忆"""
        if not self._workflow_memory:
            return None
        
        # 构建任务 ID
        task_id = f"{self.name}:{hash(user_input) % 10000}"
        
        # 尝试精确匹配
        workflow = await self._workflow_memory.get(task_id)
        if workflow and workflow.get("success_rate", 0) >= self._config.min_success_rate:
            return workflow
        
        # 尝试相似匹配
        similar = await self._workflow_memory.find_similar(self.name, limit=1)
        if similar and similar[0].get("success_rate", 0) >= self._config.min_success_rate:
            return similar[0]
        
        return None
    
    async def _record_execution(
        self,
        context: BehaviorContext,
        result: BehaviorResult,
    ) -> None:
        """记录执行到工作流记忆"""
        if not self._workflow_memory:
            return
        
        task_id = context.workflow_id or f"{self.name}:{hash(context.user_input) % 10000}"
        
        # 保存工作流定义
        await self._workflow_memory.save(
            task_id=task_id,
            agent_chain=self._config.required_capabilities,
            expected_result=context.user_input,
            influence_factors=context.parameters,
        )
        
        # 记录执行
        await self._workflow_memory.record_execution(
            task_id=task_id,
            success=result.status == BehaviorStatus.COMPLETED,
            result=result.result,
            execution_time_ms=result.duration_ms,
            error=result.error,
            context={
                "behavior_id": result.behavior_id,
                "workflow_matched": result.workflow_matched,
            },
        )
    
    async def _call_hook(self, hook: Callable, *args) -> None:
        """调用钩子"""
        import asyncio
        try:
            result = hook(*args)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            self.logger.warning(f"钩子执行失败: {e}")
    
    def can_handle(self, user_input: str) -> float:
        """
        评估是否可以处理该输入
        
        Args:
            user_input: 用户输入
            
        Returns:
            置信度 (0.0 - 1.0)
        """
        # 默认实现：子类可以覆盖
        return 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "description": self.description,
            "version": self._config.version,
            "required_capabilities": self._config.required_capabilities,
            "tags": self._config.tags,
            "status": self._status.value,
        }
