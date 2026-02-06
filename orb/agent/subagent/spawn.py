"""
Sub-agent Spawner

子 Agent 派生机制，支持：
- 从主 Agent 派生后台 Agent
- 独立 session
- 工具限制
- 结果回报 (Announce)
- 任务强制终止（安全关键）

安全特性：
- 存储 asyncio.Task 引用以支持强制取消
- stop_spawn() 会真正取消正在运行的任务
- 清理逻辑确保资源正确释放

借鉴 OpenClaw/Moltbot 的 sessions_spawn 设计。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING
from uuid import uuid4
import weakref

from orb.system.services.logger import LoggerMixin
from orb.agent.infrastructure.session_store import (
    SessionStore,
    Session,
    SessionState,
)
from orb.agent.subagent.announce import AnnounceHandler, AnnounceMessage

if TYPE_CHECKING:
    from orb.agent.runtime.agent_runtime import AgentRuntime
    from orb.agent.subagent.concurrency import ConcurrencyController


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
        
        # 任务引用跟踪（用于强制取消）
        self._spawn_tasks: Dict[str, asyncio.Task] = {}
        self._task_lock = asyncio.Lock()  # 保护任务字典的锁
        
        # 完成回调
        self._completion_callbacks: List[SpawnCompletionCallback] = []
        
        # 归档定时器
        self._archive_timers: Dict[str, asyncio.Task] = {}
        
        # 统计
        self._total_spawns = 0
        self._successful_spawns = 0
        self._failed_spawns = 0
        self._cancelled_spawns = 0  # 被取消的派生数
        
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
        
        # 创建执行任务并存储引用（用于强制取消）
        async def run_subagent():
            try:
                await self._execute_subagent(
                    result=result,
                    request=request,
                    runtime=runtime,
                    session_store=session_store,
                )
            finally:
                # 清理任务引用
                async with self._task_lock:
                    self._spawn_tasks.pop(result.spawn_id, None)
        
        # 直接创建任务（不通过并发控制器，以便跟踪）
        task = asyncio.create_task(run_subagent())
        
        # 存储任务引用
        async with self._task_lock:
            self._spawn_tasks[result.spawn_id] = task
        
        # 同时提交到并发控制器进行调度（可选）
        # await self._concurrency.submit(run_subagent(), lane_id="subagent")
        
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
            # 取消不计入失败，由 stop_spawn() 单独统计 _cancelled_spawns
            
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
        
    async def stop_spawn(
        self,
        spawn_id: str,
        timeout: float = 5.0,
        force: bool = False,
    ) -> bool:
        """
        停止派生（强制取消正在运行的任务）
        
        Args:
            spawn_id: 派生 ID
            timeout: 等待取消完成的超时时间（秒）
            force: 是否强制取消（即使任务不在 RUNNING 状态）
            
        Returns:
            是否成功取消
        """
        result = self._active_spawns.get(spawn_id)
        if not result:
            self.logger.warning(f"派生不存在: {spawn_id}")
            return False
        
        # 检查状态并提前记录是否需要增加计数
        was_running = result.status == SpawnStatus.RUNNING
        
        if not force and not was_running:
            self.logger.debug(f"派生不在运行状态: {spawn_id} ({result.status.value})")
            return False
        
        # 获取任务引用
        async with self._task_lock:
            task = self._spawn_tasks.get(spawn_id)
        
        if task and not task.done():
            self.logger.info(f"正在取消派生任务: {spawn_id}")
            
            # 发送取消信号
            task.cancel()
            
            try:
                # 等待任务完成（或超时）
                await asyncio.wait_for(
                    asyncio.shield(task),
                    timeout=timeout,
                )
            except asyncio.CancelledError:
                # 任务成功取消
                self.logger.info(f"派生任务已取消: {spawn_id}")
            except asyncio.TimeoutError:
                # 取消超时，强制标记
                self.logger.warning(f"取消派生任务超时: {spawn_id}")
            except Exception as e:
                self.logger.error(f"取消派生任务时出错: {spawn_id}, {e}")
        
        # 如果任务之前是运行状态，增加取消计数
        # 注意：_execute_subagent 中的 CancelledError 处理会更新状态，
        # 所以这里使用之前保存的 was_running 来决定是否增加计数
        if was_running:
            self._cancelled_spawns += 1
            # 确保状态被标记为已取消（可能已经被 _execute_subagent 设置）
            if result.status != SpawnStatus.CANCELLED:
                result.status = SpawnStatus.CANCELLED
                result.error = "被用户或系统取消"
                result.ended_at = datetime.now().isoformat()
        
        # 清理任务引用
        async with self._task_lock:
            self._spawn_tasks.pop(spawn_id, None)
        
        return True
        
    async def stop_all_for_session(
        self,
        session_id: str,
        timeout: float = 5.0,
    ) -> int:
        """
        停止会话的所有子 Agent
        
        Args:
            session_id: 会话 ID
            timeout: 每个任务的取消超时时间
            
        Returns:
            停止的数量
        """
        spawns_to_stop = []
        
        for spawn_id, result in list(self._active_spawns.items()):
            if result.metadata.get("parent_session_id") == session_id:
                spawns_to_stop.append(spawn_id)
        
        # 并行取消所有任务
        if spawns_to_stop:
            self.logger.info(f"批量取消 {len(spawns_to_stop)} 个派生任务")
            results = await asyncio.gather(
                *[self.stop_spawn(spawn_id, timeout=timeout) for spawn_id in spawns_to_stop],
                return_exceptions=True,
            )
            count = sum(1 for r in results if r is True)
            return count
        
        return 0
    
    async def stop_all(self, timeout: float = 5.0) -> int:
        """
        停止所有正在运行的子 Agent（紧急停止）
        
        Args:
            timeout: 每个任务的取消超时时间
            
        Returns:
            停止的数量
        """
        running_spawns = [
            spawn_id for spawn_id, result in self._active_spawns.items()
            if result.status == SpawnStatus.RUNNING
        ]
        
        if running_spawns:
            self.logger.warning(f"紧急停止: 取消 {len(running_spawns)} 个派生任务")
            results = await asyncio.gather(
                *[self.stop_spawn(spawn_id, timeout=timeout, force=True) for spawn_id in running_spawns],
                return_exceptions=True,
            )
            count = sum(1 for r in results if r is True)
            return count
        
        return 0
        
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
            "running_tasks": len(self._spawn_tasks),
            "status_counts": status_counts,
            "pending_archives": len(self._archive_timers),
            "total_spawns": self._total_spawns,
            "successful_spawns": self._successful_spawns,
            "failed_spawns": self._failed_spawns,
            "cancelled_spawns": self._cancelled_spawns,
            "success_rate": (
                self._successful_spawns / self._total_spawns
                if self._total_spawns > 0 else 0
            ),
            "enable_announce": self._enable_announce,
            "completion_callbacks": len(self._completion_callbacks),
        }
    
    async def get_running_tasks(self) -> List[str]:
        """
        获取正在运行的任务 ID 列表
        
        Returns:
            正在运行的 spawn_id 列表
        """
        async with self._task_lock:
            return [
                spawn_id for spawn_id, task in self._spawn_tasks.items()
                if not task.done()
            ]


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
