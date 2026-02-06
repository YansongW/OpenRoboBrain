"""
任务管道管理器

管理多任务场景下的 MessageBus 实例。

设计说明：
- OpenRoboBrain 采用多Agent架构，多任务并发时可能产生消息混乱
- 解决方案：使用消息队列策略，Agent 逐个处理任务，输出到对应任务ID的管道
- TaskPipelineManager 负责管理所有活跃的 MessageBus 实例

多任务处理流程：
1. 任务到达 → 分配 task_id
2. TaskPipelineManager.create_bus(task_id) 创建专属 MessageBus
3. Agent 使用该 MessageBus 处理任务
4. 处理完成 → 结果通过该 MessageBus 输出
5. TaskPipelineManager.close_bus(task_id) 清理资源
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING
from uuid import uuid4

from orb.system.brain_pipeline.message_bus import MessageBus
from orb.system.services.logger import LoggerMixin

if TYPE_CHECKING:
    from orb.system.services.config_center import ConfigCenter


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"      # 等待处理
    PROCESSING = "processing"  # 处理中
    COMPLETED = "completed"   # 已完成
    FAILED = "failed"        # 失败
    CANCELLED = "cancelled"   # 已取消


@dataclass
class TaskInfo:
    """任务信息"""
    task_id: str
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result": self.result,
            "error": self.error,
            "metadata": self.metadata,
        }


# 任务完成回调类型
TaskCompletionCallback = Callable[[str, Any], Any]


class TaskPipelineManager(LoggerMixin):
    """
    任务管道管理器
    
    负责管理多任务场景下的 MessageBus 实例：
    - 为每个任务创建独立的 MessageBus
    - 维护任务队列，串行处理
    - 管理 MessageBus 生命周期
    - 收集任务统计信息
    
    设计原则：
    - 任务隔离：不同任务的消息不会混淆
    - 状态清晰：每个 MessageBus 只负责一个任务
    - 生命周期管理：任务结束，对应的 MessageBus 可以被清理
    """
    
    def __init__(
        self,
        config: Optional[ConfigCenter] = None,
        max_concurrent_tasks: int = 10,
        auto_cleanup: bool = True,
        cleanup_delay_seconds: float = 60.0,
    ):
        """
        初始化任务管道管理器
        
        Args:
            config: 配置中心
            max_concurrent_tasks: 最大并发任务数
            auto_cleanup: 是否自动清理已完成的任务
            cleanup_delay_seconds: 自动清理延迟（秒）
        """
        self._config = config
        self._max_concurrent = max_concurrent_tasks
        self._auto_cleanup = auto_cleanup
        self._cleanup_delay = cleanup_delay_seconds
        
        # MessageBus 注册表：task_id -> MessageBus
        self._bus_registry: Dict[str, MessageBus] = {}
        
        # 任务信息：task_id -> TaskInfo
        self._task_info: Dict[str, TaskInfo] = {}
        
        # 任务队列（等待处理的任务）
        self._task_queue: asyncio.Queue[str] = asyncio.Queue()
        
        # 并发控制
        self._semaphore = asyncio.Semaphore(max_concurrent_tasks)
        
        # 清理定时器
        self._cleanup_timers: Dict[str, asyncio.Task] = {}
        
        # 完成回调
        self._completion_callbacks: List[TaskCompletionCallback] = []
        
        # 统计
        self._total_tasks = 0
        self._completed_tasks = 0
        self._failed_tasks = 0
        
        # 运行状态
        self._running = False
        
    @property
    def is_running(self) -> bool:
        """是否运行中"""
        return self._running
    
    @property
    def active_task_count(self) -> int:
        """活跃任务数"""
        return len(self._bus_registry)
    
    @property
    def pending_task_count(self) -> int:
        """等待处理的任务数"""
        return self._task_queue.qsize()
    
    async def initialize(self) -> None:
        """初始化管理器"""
        self._running = True
        self.logger.info("TaskPipelineManager 初始化完成")
    
    async def shutdown(self) -> None:
        """关闭管理器"""
        self._running = False
        
        # 取消所有清理定时器
        for timer in self._cleanup_timers.values():
            timer.cancel()
        self._cleanup_timers.clear()
        
        # 关闭所有 MessageBus
        for task_id in list(self._bus_registry.keys()):
            await self.close_bus(task_id)
        
        self.logger.info("TaskPipelineManager 已关闭")
    
    def generate_task_id(self) -> str:
        """
        生成任务ID
        
        Returns:
            唯一的任务ID
        """
        return f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    
    async def create_bus(
        self,
        task_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MessageBus:
        """
        创建任务专属的 MessageBus
        
        Args:
            task_id: 任务ID（可选，自动生成）
            metadata: 任务元数据
            
        Returns:
            MessageBus 实例
        """
        # 生成或使用提供的 task_id
        task_id = task_id or self.generate_task_id()
        
        # 检查是否已存在
        if task_id in self._bus_registry:
            self.logger.warning(f"任务 {task_id} 的 MessageBus 已存在")
            return self._bus_registry[task_id]
        
        # 创建 MessageBus
        bus = MessageBus(task_id=task_id, config=self._config)
        await bus.initialize()
        
        # 注册
        self._bus_registry[task_id] = bus
        
        # 创建任务信息
        self._task_info[task_id] = TaskInfo(
            task_id=task_id,
            status=TaskStatus.PENDING,
            metadata=metadata or {},
        )
        
        self._total_tasks += 1
        self.logger.info(f"创建 MessageBus: task_id={task_id}")
        
        return bus
    
    def get_bus(self, task_id: str) -> Optional[MessageBus]:
        """
        获取指定任务的 MessageBus
        
        Args:
            task_id: 任务ID
            
        Returns:
            MessageBus 实例，不存在返回 None
        """
        return self._bus_registry.get(task_id)
    
    async def close_bus(self, task_id: str) -> bool:
        """
        关闭并移除 MessageBus
        
        Args:
            task_id: 任务ID
            
        Returns:
            是否成功
        """
        bus = self._bus_registry.pop(task_id, None)
        if not bus:
            return False
        
        # 关闭 MessageBus
        await bus.shutdown()
        
        # 取消清理定时器
        timer = self._cleanup_timers.pop(task_id, None)
        if timer:
            timer.cancel()
        
        self.logger.info(f"关闭 MessageBus: task_id={task_id}")
        return True
    
    def mark_task_processing(self, task_id: str) -> None:
        """标记任务为处理中"""
        if task_id in self._task_info:
            info = self._task_info[task_id]
            info.status = TaskStatus.PROCESSING
            info.started_at = datetime.now()
    
    async def mark_task_completed(
        self,
        task_id: str,
        result: Any = None,
    ) -> None:
        """
        标记任务完成
        
        Args:
            task_id: 任务ID
            result: 任务结果
        """
        if task_id in self._task_info:
            info = self._task_info[task_id]
            info.status = TaskStatus.COMPLETED
            info.completed_at = datetime.now()
            info.result = result
            self._completed_tasks += 1
            
            # 触发回调
            await self._notify_completion(task_id, result)
            
            # 自动清理
            if self._auto_cleanup:
                self._schedule_cleanup(task_id)
    
    async def mark_task_failed(
        self,
        task_id: str,
        error: str,
    ) -> None:
        """
        标记任务失败
        
        Args:
            task_id: 任务ID
            error: 错误信息
        """
        if task_id in self._task_info:
            info = self._task_info[task_id]
            info.status = TaskStatus.FAILED
            info.completed_at = datetime.now()
            info.error = error
            self._failed_tasks += 1
            
            # 自动清理
            if self._auto_cleanup:
                self._schedule_cleanup(task_id)
    
    def _schedule_cleanup(self, task_id: str) -> None:
        """设置清理定时器"""
        async def cleanup_later():
            await asyncio.sleep(self._cleanup_delay)
            await self.close_bus(task_id)
            self._task_info.pop(task_id, None)
            self._cleanup_timers.pop(task_id, None)
        
        if task_id not in self._cleanup_timers:
            task = asyncio.create_task(cleanup_later())
            self._cleanup_timers[task_id] = task
    
    def on_task_completion(self, callback: TaskCompletionCallback) -> None:
        """
        注册任务完成回调
        
        Args:
            callback: 回调函数 (task_id, result) -> Any
        """
        self._completion_callbacks.append(callback)
    
    async def _notify_completion(self, task_id: str, result: Any) -> None:
        """通知任务完成"""
        for callback in self._completion_callbacks:
            try:
                cb_result = callback(task_id, result)
                if asyncio.iscoroutine(cb_result):
                    await cb_result
            except Exception as e:
                self.logger.warning(f"任务完成回调执行失败: {e}")
    
    def get_task_info(self, task_id: str) -> Optional[TaskInfo]:
        """
        获取任务信息
        
        Args:
            task_id: 任务ID
            
        Returns:
            TaskInfo 或 None
        """
        return self._task_info.get(task_id)
    
    def list_active_tasks(self) -> List[str]:
        """
        列出所有活跃任务的ID
        
        Returns:
            任务ID列表
        """
        return list(self._bus_registry.keys())
    
    def list_tasks_by_status(self, status: TaskStatus) -> List[TaskInfo]:
        """
        按状态列出任务
        
        Args:
            status: 任务状态
            
        Returns:
            TaskInfo 列表
        """
        return [
            info for info in self._task_info.values()
            if info.status == status
        ]
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息
        
        Returns:
            统计字典
        """
        status_counts = {}
        for status in TaskStatus:
            status_counts[status.value] = sum(
                1 for info in self._task_info.values()
                if info.status == status
            )
        
        return {
            "running": self._running,
            "total_tasks": self._total_tasks,
            "completed_tasks": self._completed_tasks,
            "failed_tasks": self._failed_tasks,
            "active_buses": len(self._bus_registry),
            "pending_cleanups": len(self._cleanup_timers),
            "status_counts": status_counts,
            "success_rate": (
                self._completed_tasks / self._total_tasks
                if self._total_tasks > 0 else 0
            ),
        }
    
    def get_bus_info(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        获取指定 MessageBus 的详细信息
        
        Args:
            task_id: 任务ID
            
        Returns:
            MessageBus 信息字典
        """
        bus = self._bus_registry.get(task_id)
        if not bus:
            return None
        
        task_info = self._task_info.get(task_id)
        
        return {
            "bus": bus.get_info(),
            "task": task_info.to_dict() if task_info else None,
        }


# ============== 便捷函数 ==============

_default_manager: Optional[TaskPipelineManager] = None


async def get_pipeline_manager(
    config: Optional[ConfigCenter] = None,
) -> TaskPipelineManager:
    """
    获取默认的任务管道管理器
    
    Args:
        config: 配置中心（仅首次调用有效）
        
    Returns:
        TaskPipelineManager 实例
    """
    global _default_manager
    
    if _default_manager is None:
        _default_manager = TaskPipelineManager(config=config)
        await _default_manager.initialize()
    
    return _default_manager


async def close_pipeline_manager() -> None:
    """关闭默认的任务管道管理器"""
    global _default_manager
    
    if _default_manager:
        await _default_manager.shutdown()
        _default_manager = None


def create_pipeline_manager(
    max_concurrent_tasks: int = 10,
    auto_cleanup: bool = True,
    cleanup_delay_seconds: float = 60.0,
    config: Optional[ConfigCenter] = None,
) -> TaskPipelineManager:
    """
    创建任务管道管理器
    
    Args:
        max_concurrent_tasks: 最大并发任务数
        auto_cleanup: 是否自动清理
        cleanup_delay_seconds: 清理延迟
        config: 配置中心
        
    Returns:
        TaskPipelineManager 实例
    """
    return TaskPipelineManager(
        config=config,
        max_concurrent_tasks=max_concurrent_tasks,
        auto_cleanup=auto_cleanup,
        cleanup_delay_seconds=cleanup_delay_seconds,
    )
