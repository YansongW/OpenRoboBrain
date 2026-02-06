"""
Sub-agent Manager

子 Agent 管理器，整合 spawn、announce 和并发控制。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from orb.system.services.logger import LoggerMixin
from orb.agent.subagent.spawn import (
    SubAgentSpawner,
    SpawnRequest,
    SpawnResult,
    SpawnStatus,
)
from orb.agent.subagent.announce import (
    AnnounceHandler,
    AnnounceMessage,
    AnnounceStatus,
)
from orb.agent.subagent.concurrency import (
    ConcurrencyController,
    LaneType,
)

if TYPE_CHECKING:
    from orb.agent.runtime.agent_runtime import AgentRuntime
    from orb.agent.infrastructure.session_store import SessionStore


@dataclass
class SubAgentConfig:
    """子 Agent 配置"""
    max_concurrent: int = 8
    default_model: Optional[str] = None
    archive_after_minutes: int = 60
    allowed_agents: List[str] = field(default_factory=lambda: ["*"])  # ["*"] 表示允许所有
    denied_tools: List[str] = field(default_factory=list)


class SubAgentManager(LoggerMixin):
    """
    子 Agent 管理器
    
    整合所有子 Agent 相关功能：
    - Spawn: 派生子 Agent
    - Announce: 结果回报
    - Concurrency: 并发控制
    - Cleanup: 资源清理
    """
    
    def __init__(self, config: Optional[SubAgentConfig] = None):
        """
        初始化子 Agent 管理器
        
        Args:
            config: 配置
        """
        self._config = config or SubAgentConfig()
        
        # 初始化组件
        self._concurrency = ConcurrencyController(
            default_max_concurrent=self._config.max_concurrent,
        )
        
        self._spawner = SubAgentSpawner(
            concurrency_controller=self._concurrency,
            default_model=self._config.default_model,
            max_concurrent=self._config.max_concurrent,
            archive_after_minutes=self._config.archive_after_minutes,
        )
        
        self._announce = AnnounceHandler()
        
        # 运行时注册表
        self._runtimes: Dict[str, AgentRuntime] = {}
        self._session_stores: Dict[str, SessionStore] = {}
        
    @property
    def config(self) -> SubAgentConfig:
        """配置"""
        return self._config
        
    @property
    def spawner(self) -> SubAgentSpawner:
        """派生器"""
        return self._spawner
        
    @property
    def announce_handler(self) -> AnnounceHandler:
        """Announce 处理器"""
        return self._announce
        
    @property
    def concurrency(self) -> ConcurrencyController:
        """并发控制器"""
        return self._concurrency
        
    def register_runtime(
        self,
        agent_id: str,
        runtime: AgentRuntime,
        session_store: SessionStore,
    ) -> None:
        """
        注册 Agent 运行时
        
        Args:
            agent_id: Agent ID
            runtime: 运行时
            session_store: 会话存储
        """
        self._runtimes[agent_id] = runtime
        self._session_stores[agent_id] = session_store
        
    def unregister_runtime(self, agent_id: str) -> None:
        """
        注销 Agent 运行时
        
        Args:
            agent_id: Agent ID
        """
        self._runtimes.pop(agent_id, None)
        self._session_stores.pop(agent_id, None)
        
    def is_agent_allowed(self, agent_id: str, requester_agent_id: str) -> bool:
        """
        检查是否允许派生到目标 Agent
        
        Args:
            agent_id: 目标 Agent ID
            requester_agent_id: 请求者 Agent ID
            
        Returns:
            是否允许
        """
        allowed = self._config.allowed_agents
        
        # "*" 表示允许所有
        if "*" in allowed:
            return True
            
        # 允许派生到自己
        if agent_id == requester_agent_id:
            return True
            
        return agent_id in allowed
        
    async def spawn(
        self,
        task: str,
        parent_agent_id: str,
        parent_session_id: str,
        target_agent_id: Optional[str] = None,
        label: Optional[str] = None,
        model: Optional[str] = None,
        run_timeout_seconds: float = 0,
        cleanup: str = "keep",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SpawnResult:
        """
        派生子 Agent
        
        Args:
            task: 任务描述
            parent_agent_id: 父 Agent ID
            parent_session_id: 父会话 ID
            target_agent_id: 目标 Agent ID
            label: 标签
            model: 模型
            run_timeout_seconds: 运行超时
            cleanup: 清理策略
            metadata: 元数据
            
        Returns:
            派生结果
        """
        target_id = target_agent_id or parent_agent_id
        
        # 检查权限
        if not self.is_agent_allowed(target_id, parent_agent_id):
            return SpawnResult(
                status=SpawnStatus.ERROR,
                error=f"不允许派生到 Agent: {target_id}",
            )
            
        # 获取运行时和会话存储
        runtime = self._runtimes.get(target_id)
        session_store = self._session_stores.get(target_id)
        
        if not runtime or not session_store:
            return SpawnResult(
                status=SpawnStatus.ERROR,
                error=f"Agent 运行时未注册: {target_id}",
            )
            
        # 创建请求
        request = SpawnRequest(
            task=task,
            parent_agent_id=parent_agent_id,
            parent_session_id=parent_session_id,
            target_agent_id=target_id,
            label=label,
            model=model,
            run_timeout_seconds=run_timeout_seconds,
            cleanup=cleanup,
            metadata=metadata or {},
        )
        
        # 派生
        result = await self._spawner.spawn(request, runtime, session_store)
        
        return result
        
    async def spawn_and_wait(
        self,
        task: str,
        parent_agent_id: str,
        parent_session_id: str,
        target_agent_id: Optional[str] = None,
        timeout: Optional[float] = None,
        **kwargs,
    ) -> SpawnResult:
        """
        派生子 Agent 并等待完成
        
        Args:
            task: 任务描述
            parent_agent_id: 父 Agent ID
            parent_session_id: 父会话 ID
            target_agent_id: 目标 Agent ID
            timeout: 等待超时
            **kwargs: 其他参数
            
        Returns:
            派生结果
        """
        result = await self.spawn(
            task=task,
            parent_agent_id=parent_agent_id,
            parent_session_id=parent_session_id,
            target_agent_id=target_agent_id,
            **kwargs,
        )
        
        if result.status == SpawnStatus.ERROR:
            return result
            
        # 等待完成
        import asyncio
        start = asyncio.get_event_loop().time()
        
        while True:
            current_result = self._spawner.get_spawn_result(result.spawn_id)
            if not current_result:
                break
                
            if current_result.status not in [SpawnStatus.ACCEPTED, SpawnStatus.RUNNING]:
                return current_result
                
            if timeout:
                elapsed = asyncio.get_event_loop().time() - start
                if elapsed >= timeout:
                    return SpawnResult(
                        spawn_id=result.spawn_id,
                        status=SpawnStatus.TIMEOUT,
                        error=f"等待超时 ({timeout}s)",
                    )
                    
            await asyncio.sleep(0.1)
            
        return result
        
    async def announce_result(
        self,
        spawn_id: str,
        summary: Optional[str] = None,
    ) -> Optional[AnnounceMessage]:
        """
        发送 announce
        
        Args:
            spawn_id: 派生 ID
            summary: 摘要
            
        Returns:
            Announce 消息
        """
        result = self._spawner.get_spawn_result(spawn_id)
        if not result:
            return None
            
        return await self._announce.announce(result, summary)
        
    def register_announce_callback(
        self,
        callback: Callable[[AnnounceMessage], Any],
    ) -> None:
        """
        注册 announce 回调
        
        Args:
            callback: 回调函数
        """
        self._announce.register_callback(callback)
        
    def list_active(
        self,
        parent_session_id: Optional[str] = None,
    ) -> List[SpawnResult]:
        """
        列出活跃的子 Agent
        
        Args:
            parent_session_id: 过滤父会话 ID
            
        Returns:
            派生结果列表
        """
        return self._spawner.list_active_spawns(parent_session_id)
        
    async def stop(self, spawn_id: str) -> bool:
        """
        停止子 Agent
        
        Args:
            spawn_id: 派生 ID
            
        Returns:
            是否成功
        """
        return await self._spawner.stop_spawn(spawn_id)
        
    async def stop_all_for_session(self, session_id: str) -> int:
        """
        停止会话的所有子 Agent
        
        Args:
            session_id: 会话 ID
            
        Returns:
            停止的数量
        """
        return await self._spawner.stop_all_for_session(session_id)
        
    def get_spawn_info(self, spawn_id: str) -> Optional[Dict[str, Any]]:
        """
        获取派生信息
        
        Args:
            spawn_id: 派生 ID
            
        Returns:
            派生信息
        """
        result = self._spawner.get_spawn_result(spawn_id)
        if not result:
            return None
        return result.to_dict()
        
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "spawner": self._spawner.get_stats(),
            "announce": self._announce.get_stats(),
            "concurrency": self._concurrency.get_all_stats(),
            "registered_runtimes": list(self._runtimes.keys()),
        }


# 便捷函数
def create_subagent_manager(
    max_concurrent: int = 8,
    default_model: Optional[str] = None,
    **kwargs,
) -> SubAgentManager:
    """
    创建子 Agent 管理器
    
    Args:
        max_concurrent: 最大并发数
        default_model: 默认模型
        **kwargs: 其他配置
        
    Returns:
        SubAgentManager 实例
    """
    config = SubAgentConfig(
        max_concurrent=max_concurrent,
        default_model=default_model,
        **kwargs,
    )
    return SubAgentManager(config)
