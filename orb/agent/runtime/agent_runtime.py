"""
Agent Runtime

Agent 运行时主类，整合所有组件提供完整的 Agent 运行时环境。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, TYPE_CHECKING

from orb.system.services.logger import LoggerMixin
from orb.agent.infrastructure.workspace import (
    WorkspaceManager,
    WorkspaceConfig,
    create_workspace_manager,
)
from orb.agent.infrastructure.agent_dir import (
    AgentDirManager,
    create_agent_dir_manager,
)
from orb.agent.infrastructure.session_store import (
    SessionStore,
    Session,
    SessionState,
    create_session_store,
)
from orb.agent.runtime.agent_loop import (
    AgentLoop,
    LoopConfig,
    RunContext,
    RunResult,
)
from orb.agent.runtime.context_builder import (
    ContextBuilder,
    ContextConfig,
    AgentContext,
)
from orb.agent.runtime.tool_executor import (
    ToolExecutor,
    ToolRegistry,
    ToolCall,
    ToolResult,
)
from orb.agent.security.tool_policy import (
    ToolPolicy,
    ToolPolicyConfig,
    create_tool_policy,
)
from orb.agent.runtime.stream_handler import (
    StreamHandler,
    StreamEvent,
    StreamEventType,
    create_stream_handler,
)


@dataclass
class RuntimeConfig:
    """运行时配置"""
    # Agent 标识
    agent_id: str = "main"
    
    # 工作空间
    workspace_path: Optional[str] = None
    skip_bootstrap: bool = False
    
    # 状态目录
    state_dir: Optional[str] = None
    
    # Loop 配置
    max_iterations: int = 50
    timeout_seconds: float = 600.0
    enable_streaming: bool = True
    enable_tool_calls: bool = True
    
    # 上下文配置
    max_history_messages: int = 50
    max_context_tokens: int = 100000
    inject_bootstrap: bool = True
    inject_memory: bool = True
    
    # 模型配置
    default_model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 4096
    
    # 安全配置
    tool_policy_profile: Optional[str] = None  # 工具策略预设：full, coding, messaging, readonly, safe
    tool_policy_allow: Optional[List[str]] = None  # 允许的工具列表
    tool_policy_deny: Optional[List[str]] = None  # 拒绝的工具列表
    enforce_tool_policy: bool = True  # 是否强制执行工具策略
    
    # 其他
    metadata: Dict[str, Any] = field(default_factory=dict)


# 类型定义
InferenceFunc = Callable[[AgentContext], AsyncIterator[str]]


class AgentRuntime(LoggerMixin):
    """
    Agent 运行时
    
    整合所有组件，提供完整的 Agent 运行时环境：
    - Workspace 管理
    - AgentDir 管理
    - Session Store
    - Agent Loop
    - Context Builder
    - Tool Executor
    - Stream Handler
    """
    
    def __init__(self, config: RuntimeConfig):
        """
        初始化 Agent 运行时
        
        Args:
            config: 运行时配置
        """
        self._config = config
        self._agent_id = config.agent_id
        self._initialized = False
        
        # 组件（延迟初始化）
        self._workspace: Optional[WorkspaceManager] = None
        self._agent_dir: Optional[AgentDirManager] = None
        self._session_store: Optional[SessionStore] = None
        self._loop: Optional[AgentLoop] = None
        self._context_builder: Optional[ContextBuilder] = None
        self._tool_executor: Optional[ToolExecutor] = None
        self._stream_handler: Optional[StreamHandler] = None
        self._tool_policy: Optional[ToolPolicy] = None
        
        # 推理函数
        self._inference_func: Optional[InferenceFunc] = None
        
        # 活跃运行
        self._active_runs: Dict[str, RunContext] = {}
        self._lock = asyncio.Lock()
        
    @property
    def agent_id(self) -> str:
        """Agent ID"""
        return self._agent_id
        
    @property
    def config(self) -> RuntimeConfig:
        """配置"""
        return self._config
        
    @property
    def workspace(self) -> Optional[WorkspaceManager]:
        """工作空间管理器"""
        return self._workspace
        
    @property
    def agent_dir(self) -> Optional[AgentDirManager]:
        """AgentDir 管理器"""
        return self._agent_dir
        
    @property
    def session_store(self) -> Optional[SessionStore]:
        """会话存储"""
        return self._session_store
        
    @property
    def tool_registry(self) -> Optional[ToolRegistry]:
        """工具注册表"""
        return self._tool_executor.registry if self._tool_executor else None
    
    @property
    def tool_policy(self) -> Optional[ToolPolicy]:
        """工具策略"""
        return self._tool_policy
        
    @property
    def is_initialized(self) -> bool:
        """是否已初始化"""
        return self._initialized
        
    async def initialize(self) -> bool:
        """
        初始化运行时
        
        Returns:
            是否成功
        """
        if self._initialized:
            return True
            
        self.logger.info(f"初始化 Agent 运行时: {self._agent_id}")
        
        try:
            # 1. 初始化 Workspace
            workspace_path = self._config.workspace_path
            if workspace_path:
                self._workspace = create_workspace_manager(
                    agent_id=self._agent_id,
                    base_dir=workspace_path,
                    skip_bootstrap=self._config.skip_bootstrap,
                )
            else:
                self._workspace = create_workspace_manager(
                    agent_id=self._agent_id,
                    skip_bootstrap=self._config.skip_bootstrap,
                )
            self._workspace.initialize()
            
            # 2. 初始化 AgentDir
            state_dir = self._config.state_dir
            if state_dir:
                base_path = Path(state_dir).expanduser()
            else:
                base_path = None
                
            self._agent_dir = create_agent_dir_manager(
                agent_id=self._agent_id,
                base_path=base_path,
            )
            self._agent_dir.initialize()
            
            # 3. 初始化 Session Store
            self._session_store = create_session_store(
                sessions_dir=self._agent_dir.sessions_dir,
                agent_id=self._agent_id,
            )
            
            # 4. 初始化工具策略
            if (self._config.tool_policy_profile or 
                self._config.tool_policy_allow or 
                self._config.tool_policy_deny):
                self._tool_policy = create_tool_policy(
                    profile=self._config.tool_policy_profile,
                    allow=self._config.tool_policy_allow,
                    deny=self._config.tool_policy_deny,
                )
                self.logger.info(
                    f"工具策略已配置: profile={self._config.tool_policy_profile}, "
                    f"enforce={self._config.enforce_tool_policy}"
                )
            
            # 5. 初始化 Tool Executor（传递策略）
            self._tool_executor = ToolExecutor(
                policy=self._tool_policy,
                enforce_policy=self._config.enforce_tool_policy,
            )
            
            # 6. 初始化 Context Builder
            context_config = ContextConfig(
                max_history_messages=self._config.max_history_messages,
                max_context_tokens=self._config.max_context_tokens,
                inject_bootstrap=self._config.inject_bootstrap,
                inject_memory=self._config.inject_memory,
            )
            self._context_builder = ContextBuilder(context_config, self._workspace)
            
            # 7. 初始化 Agent Loop
            loop_config = LoopConfig(
                max_iterations=self._config.max_iterations,
                timeout_seconds=self._config.timeout_seconds,
                enable_streaming=self._config.enable_streaming,
                enable_tool_calls=self._config.enable_tool_calls,
            )
            self._loop = AgentLoop(
                config=loop_config,
                context_builder=self._context_builder,
                tool_executor=self._tool_executor,
                session_store=self._session_store,
            )
            
            # 8. 初始化 Stream Handler
            self._stream_handler = create_stream_handler(
                use_chunking=self._config.enable_streaming,
            )
            
            self._initialized = True
            self.logger.info(f"Agent 运行时初始化完成: {self._agent_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Agent 运行时初始化失败: {e}")
            return False
            
    def set_inference_func(self, func: InferenceFunc) -> None:
        """
        设置推理函数
        
        Args:
            func: 推理函数
        """
        self._inference_func = func
        if self._loop:
            self._loop.set_inference_func(func)
    
    def set_tool_policy(self, policy: Optional[ToolPolicy]) -> None:
        """
        设置工具策略
        
        Args:
            policy: 工具策略（None 表示移除策略）
        """
        self._tool_policy = policy
        if self._tool_executor:
            self._tool_executor.set_policy(policy)
        self.logger.info(f"工具策略已更新: {'已配置' if policy else '无'}")
            
    def register_tool(
        self,
        name: str,
        handler: Callable,
        description: str = "",
        **kwargs,
    ) -> None:
        """
        注册工具
        
        Args:
            name: 工具名称
            handler: 处理函数
            description: 描述
            **kwargs: 其他参数
        """
        if self._tool_executor:
            self._tool_executor.registry.register(
                name=name,
                handler=handler,
                description=description,
                **kwargs,
            )
            
    async def run(
        self,
        user_input: str,
        session_id: Optional[str] = None,
        model: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RunResult:
        """
        执行 Agent
        
        Args:
            user_input: 用户输入
            session_id: 会话 ID（如果为空则创建新会话）
            model: 模型
            parameters: 参数
            metadata: 元数据
            
        Returns:
            运行结果
        """
        if not self._initialized:
            raise RuntimeError("运行时未初始化")
            
        if not self._loop:
            raise RuntimeError("Agent Loop 未初始化")
            
        # 确保有会话
        if session_id:
            session = await self._session_store.get_session(session_id)
            if not session:
                # 创建新会话
                session = await self._session_store.create_session(
                    model=model or self._config.default_model,
                    metadata=metadata,
                )
                session_id = session.session_id
        else:
            session = await self._session_store.create_session(
                model=model or self._config.default_model,
                metadata=metadata,
            )
            session_id = session.session_id
            
        # 激活会话
        await self._session_store.update_session_state(
            session_id,
            SessionState.ACTIVE,
        )
        
        # 设置流处理器上下文
        if self._stream_handler:
            self._stream_handler.set_run_context("", session_id)
            
        # 更新工具定义到上下文构建器
        if self._context_builder and self._tool_executor:
            self._context_builder.register_tools(
                self._tool_executor.registry.get_api_definitions()
            )
            
        # 执行 Loop
        result = await self._loop.run(
            session_id=session_id,
            user_input=user_input,
            agent_id=self._agent_id,
            model=model or self._config.default_model,
            parameters=parameters,
            metadata=metadata,
        )
        
        return result
        
    async def run_stream(
        self,
        user_input: str,
        session_id: Optional[str] = None,
        model: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[StreamEvent]:
        """
        流式执行 Agent
        
        Args:
            user_input: 用户输入
            session_id: 会话 ID
            model: 模型
            parameters: 参数
            metadata: 元数据
            
        Yields:
            流事件
        """
        if not self._stream_handler:
            raise RuntimeError("Stream Handler 未初始化")
            
        # 在后台启动运行
        run_task = asyncio.create_task(
            self.run(
                user_input=user_input,
                session_id=session_id,
                model=model,
                parameters=parameters,
                metadata=metadata,
            )
        )
        
        # 发射开始事件
        await self._stream_handler.emit_lifecycle_start()
        
        # 迭代流事件
        async for event in self._stream_handler.events():
            yield event
            
        # 等待运行完成
        result = await run_task
        
        # 发射结束事件
        if result.status == "success":
            await self._stream_handler.emit_lifecycle_end(
                status="success",
                summary=result.response[:100] if result.response else None,
            )
        else:
            await self._stream_handler.emit_lifecycle_error(
                error=result.error or "Unknown error",
            )
            
    async def create_session(
        self,
        session_key: Optional[str] = None,
        model: Optional[str] = None,
        channel: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Session:
        """
        创建会话
        
        Args:
            session_key: 会话键
            model: 模型
            channel: 通道
            metadata: 元数据
            
        Returns:
            会话对象
        """
        if not self._session_store:
            raise RuntimeError("Session Store 未初始化")
            
        return await self._session_store.create_session(
            session_key=session_key,
            model=model or self._config.default_model,
            channel=channel,
            metadata=metadata,
        )
        
    async def get_session(self, session_id: str) -> Optional[Session]:
        """
        获取会话
        
        Args:
            session_id: 会话 ID
            
        Returns:
            会话对象
        """
        if not self._session_store:
            return None
        return await self._session_store.get_session(session_id)
        
    def abort_run(self, run_id: Optional[str] = None) -> None:
        """
        中止运行
        
        Args:
            run_id: 运行 ID（如果为空则中止当前运行）
        """
        if self._loop:
            self._loop.abort()
            
    def get_info(self) -> Dict[str, Any]:
        """
        获取运行时信息
        
        Returns:
            运行时信息
        """
        info = {
            "agent_id": self._agent_id,
            "initialized": self._initialized,
            "config": {
                "max_iterations": self._config.max_iterations,
                "timeout_seconds": self._config.timeout_seconds,
                "enable_streaming": self._config.enable_streaming,
                "enable_tool_calls": self._config.enable_tool_calls,
                "default_model": self._config.default_model,
            },
        }
        
        if self._workspace:
            info["workspace"] = self._workspace.get_workspace_info()
            
        if self._agent_dir:
            info["agent_dir"] = self._agent_dir.get_info()
            
        if self._session_store:
            info["sessions"] = self._session_store.get_stats()
            
        if self._tool_executor:
            info["tools"] = self._tool_executor.get_stats()
            
        return info
        
    async def cleanup(self) -> None:
        """清理资源"""
        if self._workspace:
            self._workspace.cleanup()
            
        if self._agent_dir:
            self._agent_dir.cleanup()
            
        self._initialized = False


# 便捷函数
def create_agent_runtime(
    agent_id: str = "main",
    **config_kwargs,
) -> AgentRuntime:
    """
    创建 Agent 运行时
    
    Args:
        agent_id: Agent ID
        **config_kwargs: 配置参数
        
    Returns:
        AgentRuntime 实例
    """
    config = RuntimeConfig(agent_id=agent_id, **config_kwargs)
    return AgentRuntime(config)
