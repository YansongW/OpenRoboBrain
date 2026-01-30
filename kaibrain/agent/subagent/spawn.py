"""
Sub-agent Spawner

子 Agent 派生机制，支持：
- 从主 Agent 派生后台 Agent
- 独立 session
- 工具限制
- 结果回报 (Announce)

借鉴 OpenClaw/Moltbot 的 sessions_spawn 设计。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING
from uuid import uuid4

from kaibrain.system.services.logger import LoggerMixin
from kaibrain.agent.infrastructure.session_store import (
    SessionStore,
    Session,
    SessionState,
)
from kaibrain.agent.subagent.announce import AnnounceHandler, AnnounceMessage

if TYPE_CHECKING:
    from kaibrain.agent.runtime.agent_runtime import AgentRuntime
    from kaibrain.agent.subagent.concurrency import ConcurrencyController


# 回调类型
SpawnCompletionCallback = Callable[["SpawnResult"], Any]


class SpawnStatus(Enum):
    """派生状态"""
    ACCEPTED = "accepted"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class SpawnRequest:
    """派生请求"""
    task: str                                    # 任务描述
    parent_agent_id: str                         # 父 Agent ID
    parent_session_id: str                       # 父会话 ID
    target_agent_id: Optional[str] = None        # 目标 Agent ID（默认与父相同）
    label: Optional[str] = None                  # 标签
    model: Optional[str] = None                  # 模型
    thinking: Optional[str] = None               # thinking 级别
    run_timeout_seconds: float = 0               # 运行超时（0 表示无限）
    cleanup: str = "keep"                        # 清理策略：keep | delete
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SpawnResult:
    """派生结果"""
    spawn_id: str = field(default_factory=lambda: str(uuid4()))
    status: SpawnStatus = SpawnStatus.ACCEPTED
    run_id: str = ""
    child_session_key: str = ""
    child_session_id: str = ""
    response: Optional[str] = None
    error: Optional[str] = None
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    ended_at: Optional[str] = None
    runtime_seconds: float = 0
    tokens_used: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "spawn_id": self.spawn_id,
            "status": self.status.value,
            "run_id": self.run_id,
            "child_session_key": self.child_session_key,
            "child_session_id": self.child_session_id,
            "response": self.response,
            "error": self.error,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "runtime_seconds": self.runtime_seconds,
            "tokens_used": self.tokens_used,
            "metadata": self.metadata,
        }


class SubAgentSpawner(LoggerMixin):
    """
    子 Agent 派生器
    
    负责创建和管理子 Agent 运行。
    支持：
    - 动态创建子 Agent
    - 结果回报 (Announce) 机制
    - 并发控制
    - 自动归档
    """
    
    # 子 Agent 默认禁止的工具
    DEFAULT_DENIED_TOOLS = [
        "sessions_list",
        "sessions_history",
        "sessions_send",
        "sessions_spawn",  # 禁止嵌套派生
        "session_status",
    ]
    
    def __init__(
        self,
        concurrency_controller: "ConcurrencyController",
        announce_handler: Optional[AnnounceHandler] = None,
        default_model: Optional[str] = None,
        max_concurrent: int = 8,
        archive_after_minutes: int = 60,
        enable_announce: bool = True,
    ):
        """
        初始化派生器
        
        Args:
            concurrency_controller: 并发控制器
            announce_handler: Announce 处理器
            default_model: 默认模型
            max_concurrent: 最大并发数
            archive_after_minutes: 归档延迟（分钟）
            enable_announce: 是否启用 announce
        """
        self._concurrency = concurrency_controller
        self._announce_handler = announce_handler or AnnounceHandler()
        self._default_model = default_model
        self._max_concurrent = max_concurrent
        self._archive_after_minutes = archive_after_minutes
        self._enable_announce = enable_announce
        
        # 活跃的子 Agent
        self._active_spawns: Dict[str, SpawnResult] = {}
        
        # 完成回调
        self._completion_callbacks: List[SpawnCompletionCallback] = []
        
        # 归档定时器
        self._archive_timers: Dict[str, asyncio.Task] = {}
        
        # 统计
        self._total_spawns = 0
        self._successful_spawns = 0
        self._failed_spawns = 0
        
    @property
    def active_spawns(self) -> Dict[str, SpawnResult]:
        """活跃的派生"""
        return self._active_spawns.copy()
        
    @property
    def announce_handler(self) -> AnnounceHandler:
        """Announce 处理器"""
        return self._announce_handler
        
    @property
    def enable_announce(self) -> bool:
        """是否启用 announce"""
        return self._enable_announce
        
    @enable_announce.setter
    def enable_announce(self, value: bool) -> None:
        """设置是否启用 announce"""
        self._enable_announce = value
        
    def on_completion(self, callback: SpawnCompletionCallback) -> None:
        """
        注册完成回调
        
        Args:
            callback: 回调函数
        """
        self._completion_callbacks.append(callback)
        
    def remove_completion_callback(self, callback: SpawnCompletionCallback) -> bool:
        """
        移除完成回调
        
        Args:
            callback: 回调函数
            
        Returns:
            是否成功
        """
        if callback in self._completion_callbacks:
            self._completion_callbacks.remove(callback)
            return True
        return False
        
    def generate_subagent_session_key(
        self,
        agent_id: str,
    ) -> str:
        """
        生成子 Agent 会话键
        
        Args:
            agent_id: Agent ID
            
        Returns:
            会话键
        """
        subagent_id = str(uuid4())
        return f"agent:{agent_id}:subagent:{subagent_id}"
        
    async def spawn(
        self,
        request: SpawnRequest,
        runtime: AgentRuntime,
        session_store: SessionStore,
    ) -> SpawnResult:
        """
        派生子 Agent（非阻塞）
        
        Args:
            request: 派生请求
            runtime: Agent 运行时
            session_store: 会话存储
            
        Returns:
            派生结果（立即返回 accepted 状态）
        """
        target_agent_id = request.target_agent_id or request.parent_agent_id
        
        # 生成会话键
        session_key = self.generate_subagent_session_key(target_agent_id)
        
        # 创建子 Agent 会话
        session = await session_store.create_session(
            session_key=session_key,
            model=request.model or self._default_model,
            parent_session_id=request.parent_session_id,
            metadata={
                "is_subagent": True,
                "parent_agent_id": request.parent_agent_id,
                "task": request.task,
                "label": request.label,
            },
        )
        
        # 创建结果
        result = SpawnResult(
            status=SpawnStatus.ACCEPTED,
            child_session_key=session_key,
            child_session_id=session.session_id,
            metadata={
                "task": request.task,
                "label": request.label,
                "parent_session_id": request.parent_session_id,
            },
        )
        
        # 保存活跃派生
        self._active_spawns[result.spawn_id] = result
        
        # 提交到并发控制器（后台执行）
        async def run_subagent():
            await self._execute_subagent(
                result=result,
                request=request,
                runtime=runtime,
                session_store=session_store,
            )
            
        await self._concurrency.submit(
            run_subagent(),
            lane_id="subagent",
        )
        
        self.logger.info(f"子 Agent 已派生: {result.spawn_id} -> {session_key}")
        return result
        
    async def _execute_subagent(
        self,
        result: SpawnResult,
        request: SpawnRequest,
        runtime: "AgentRuntime",
        session_store: SessionStore,
    ) -> None:
        """
        执行子 Agent
        
        Args:
            result: 派生结果
            request: 派生请求
            runtime: Agent 运行时
            session_store: 会话存储
        """
        result.status = SpawnStatus.RUNNING
        start_time = datetime.now()
        self._total_spawns += 1
        
        try:
            # 设置超时
            timeout = request.run_timeout_seconds if request.run_timeout_seconds > 0 else None
            
            # 执行任务
            if timeout:
                run_result = await asyncio.wait_for(
                    runtime.run(
                        user_input=request.task,
                        session_id=result.child_session_id,
                        model=request.model,
                        metadata={
                            "is_subagent": True,
                            "spawn_id": result.spawn_id,
                        },
                    ),
                    timeout=timeout,
                )
            else:
                run_result = await runtime.run(
                    user_input=request.task,
                    session_id=result.child_session_id,
                    model=request.model,
                    metadata={
                        "is_subagent": True,
                        "spawn_id": result.spawn_id,
                    },
                )
                
            # 更新结果
            result.run_id = run_result.run_id
            result.response = run_result.response
            result.tokens_used = run_result.tokens_used
            result.status = (
                SpawnStatus.COMPLETED
                if run_result.status == "success"
                else SpawnStatus.ERROR
            )
            
            if run_result.error:
                result.error = run_result.error
                
            if result.status == SpawnStatus.COMPLETED:
                self._successful_spawns += 1
            else:
                self._failed_spawns += 1
                
        except asyncio.TimeoutError:
            result.status = SpawnStatus.TIMEOUT
            result.error = f"执行超时 ({request.run_timeout_seconds}s)"
            self._failed_spawns += 1
            
        except asyncio.CancelledError:
            result.status = SpawnStatus.CANCELLED
            result.error = "执行被取消"
            self._failed_spawns += 1
            
        except Exception as e:
            result.status = SpawnStatus.ERROR
            result.error = str(e)
            self._failed_spawns += 1
            self.logger.error(f"子 Agent 执行失败 {result.spawn_id}: {e}")
            
        finally:
            # 记录结束时间
            result.ended_at = datetime.now().isoformat()
            result.runtime_seconds = (datetime.now() - start_time).total_seconds()
            
            # 关闭会话
            await session_store.close_session(result.child_session_id)
            
            # 发送 Announce
            if self._enable_announce:
                await self._send_announce(result, request)
                
            # 触发完成回调
            await self._notify_completion(result)
            
            # 设置归档定时器
            if request.cleanup == "delete":
                await self._archive_session(result.child_session_id, session_store)
            else:
                self._schedule_archive(
                    result.spawn_id,
                    result.child_session_id,
                    session_store,
                )
                
            self.logger.info(
                f"子 Agent 完成: {result.spawn_id} "
                f"({result.status.value}, {result.runtime_seconds:.1f}s)"
            )
            
    async def _send_announce(
        self,
        result: SpawnResult,
        request: SpawnRequest,
    ) -> Optional[AnnounceMessage]:
        """发送 Announce"""
        try:
            message = await self._announce_handler.announce(
                spawn_result=result,
                summary=f"Task: {request.task[:100]}" if request.task else None,
            )
            return message
        except Exception as e:
            self.logger.error(f"发送 Announce 失败: {e}")
            return None
            
    async def _notify_completion(self, result: SpawnResult) -> None:
        """通知完成回调"""
        for callback in self._completion_callbacks:
            try:
                cb_result = callback(result)
                if asyncio.iscoroutine(cb_result):
                    await cb_result
            except Exception as e:
                self.logger.warning(f"完成回调执行失败: {e}")
            
    def _schedule_archive(
        self,
        spawn_id: str,
        session_id: str,
        session_store: SessionStore,
    ) -> None:
        """设置归档定时器"""
        async def archive_later():
            await asyncio.sleep(self._archive_after_minutes * 60)
            await self._archive_session(session_id, session_store)
            self._archive_timers.pop(spawn_id, None)
            self._active_spawns.pop(spawn_id, None)
            
        task = asyncio.create_task(archive_later())
        self._archive_timers[spawn_id] = task
        
    async def _archive_session(
        self,
        session_id: str,
        session_store: SessionStore,
    ) -> None:
        """归档会话"""
        await session_store.archive_session(session_id)
        
    def get_spawn_result(self, spawn_id: str) -> Optional[SpawnResult]:
        """获取派生结果"""
        return self._active_spawns.get(spawn_id)
        
    def list_active_spawns(
        self,
        parent_session_id: Optional[str] = None,
    ) -> List[SpawnResult]:
        """
        列出活跃的派生
        
        Args:
            parent_session_id: 过滤父会话 ID
            
        Returns:
            派生结果列表
        """
        spawns = list(self._active_spawns.values())
        
        if parent_session_id:
            spawns = [
                s for s in spawns
                if s.metadata.get("parent_session_id") == parent_session_id
            ]
            
        return spawns
        
    async def stop_spawn(self, spawn_id: str) -> bool:
        """
        停止派生
        
        Args:
            spawn_id: 派生 ID
            
        Returns:
            是否成功
        """
        result = self._active_spawns.get(spawn_id)
        if not result:
            return False
            
        if result.status == SpawnStatus.RUNNING:
            result.status = SpawnStatus.CANCELLED
            # 实际的取消需要更复杂的实现
            return True
            
        return False
        
    async def stop_all_for_session(self, session_id: str) -> int:
        """
        停止会话的所有子 Agent
        
        Args:
            session_id: 会话 ID
            
        Returns:
            停止的数量
        """
        count = 0
        for spawn_id, result in list(self._active_spawns.items()):
            if result.metadata.get("parent_session_id") == session_id:
                if await self.stop_spawn(spawn_id):
                    count += 1
        return count
        
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        status_counts = {}
        for status in SpawnStatus:
            status_counts[status.value] = sum(
                1 for s in self._active_spawns.values()
                if s.status == status
            )
            
        return {
            "total_active": len(self._active_spawns),
            "status_counts": status_counts,
            "pending_archives": len(self._archive_timers),
            "total_spawns": self._total_spawns,
            "successful_spawns": self._successful_spawns,
            "failed_spawns": self._failed_spawns,
            "success_rate": (
                self._successful_spawns / self._total_spawns
                if self._total_spawns > 0 else 0
            ),
            "enable_announce": self._enable_announce,
            "completion_callbacks": len(self._completion_callbacks),
        }


# ============== 便捷函数 ==============

def create_subagent_spawner(
    concurrency_controller: "ConcurrencyController",
    announce_handler: Optional[AnnounceHandler] = None,
    default_model: Optional[str] = None,
    max_concurrent: int = 8,
    archive_after_minutes: int = 60,
    enable_announce: bool = True,
) -> SubAgentSpawner:
    """
    创建子 Agent 派生器
    
    Args:
        concurrency_controller: 并发控制器
        announce_handler: Announce 处理器
        default_model: 默认模型
        max_concurrent: 最大并发数
        archive_after_minutes: 归档延迟
        enable_announce: 是否启用 announce
        
    Returns:
        SubAgentSpawner 实例
    """
    return SubAgentSpawner(
        concurrency_controller=concurrency_controller,
        announce_handler=announce_handler,
        default_model=default_model,
        max_concurrent=max_concurrent,
        archive_after_minutes=archive_after_minutes,
        enable_announce=enable_announce,
    )
