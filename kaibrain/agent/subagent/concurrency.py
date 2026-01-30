"""
Concurrency Controller

子 Agent 并发控制，包括：
- 队列通道管理
- 并发限制
- 任务调度

借鉴 Moltbot 的队列系统设计。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Awaitable
from uuid import uuid4

from kaibrain.system.services.logger import LoggerMixin


class LaneType(Enum):
    """队列通道类型"""
    SESSION = "session"      # 每 session 一个通道
    AGENT = "agent"          # 每 agent 一个通道
    GLOBAL = "global"        # 全局通道
    SUBAGENT = "subagent"    # 子 agent 专用通道


@dataclass
class QueuedTask:
    """队列中的任务"""
    task_id: str = field(default_factory=lambda: str(uuid4()))
    coroutine: Awaitable = None
    lane_id: str = ""
    priority: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QueueLane:
    """队列通道"""
    lane_id: str
    lane_type: LaneType = LaneType.SESSION
    max_concurrent: int = 1
    current_count: int = 0
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    running_tasks: Dict[str, QueuedTask] = field(default_factory=dict)
    
    @property
    def is_at_capacity(self) -> bool:
        """是否达到并发上限"""
        return self.current_count >= self.max_concurrent


class ConcurrencyController(LoggerMixin):
    """
    并发控制器
    
    管理多个队列通道，控制任务并发执行。
    """
    
    def __init__(
        self,
        default_max_concurrent: int = 8,
        session_max_concurrent: int = 1,
    ):
        """
        初始化并发控制器
        
        Args:
            default_max_concurrent: 默认最大并发数
            session_max_concurrent: 每 session 最大并发数
        """
        self._default_max_concurrent = default_max_concurrent
        self._session_max_concurrent = session_max_concurrent
        
        self._lanes: Dict[str, QueueLane] = {}
        self._global_lock = asyncio.Lock()
        
        # 全局子 agent 通道
        self._subagent_lane = QueueLane(
            lane_id="subagent",
            lane_type=LaneType.SUBAGENT,
            max_concurrent=default_max_concurrent,
        )
        self._lanes["subagent"] = self._subagent_lane
        
    def _get_or_create_lane(
        self,
        lane_id: str,
        lane_type: LaneType = LaneType.SESSION,
    ) -> QueueLane:
        """获取或创建队列通道"""
        if lane_id not in self._lanes:
            max_concurrent = (
                self._session_max_concurrent
                if lane_type == LaneType.SESSION
                else self._default_max_concurrent
            )
            self._lanes[lane_id] = QueueLane(
                lane_id=lane_id,
                lane_type=lane_type,
                max_concurrent=max_concurrent,
            )
        return self._lanes[lane_id]
        
    async def submit(
        self,
        coroutine: Awaitable,
        lane_id: str = "subagent",
        lane_type: LaneType = LaneType.SUBAGENT,
        priority: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        提交任务到队列
        
        Args:
            coroutine: 协程
            lane_id: 通道 ID
            lane_type: 通道类型
            priority: 优先级
            metadata: 元数据
            
        Returns:
            任务 ID
        """
        task = QueuedTask(
            coroutine=coroutine,
            lane_id=lane_id,
            priority=priority,
            metadata=metadata or {},
        )
        
        lane = self._get_or_create_lane(lane_id, lane_type)
        await lane.queue.put(task)
        
        self.logger.debug(f"任务已提交: {task.task_id} -> {lane_id}")
        
        # 尝试执行
        asyncio.create_task(self._process_lane(lane))
        
        return task.task_id
        
    async def _process_lane(self, lane: QueueLane) -> None:
        """处理队列通道"""
        async with lane.lock:
            if lane.is_at_capacity:
                return
                
            if lane.queue.empty():
                return
                
            # 获取任务
            task = await lane.queue.get()
            task.started_at = datetime.now().isoformat()
            
            # 标记正在运行
            lane.current_count += 1
            lane.running_tasks[task.task_id] = task
            
        try:
            # 执行任务
            await task.coroutine
            
        except Exception as e:
            self.logger.error(f"任务执行失败 {task.task_id}: {e}")
            
        finally:
            # 完成任务
            async with lane.lock:
                lane.current_count -= 1
                lane.running_tasks.pop(task.task_id, None)
                
            # 处理下一个任务
            if not lane.queue.empty():
                asyncio.create_task(self._process_lane(lane))
                
    async def submit_and_wait(
        self,
        coroutine: Awaitable,
        lane_id: str = "subagent",
        lane_type: LaneType = LaneType.SUBAGENT,
        timeout: Optional[float] = None,
    ) -> Any:
        """
        提交任务并等待完成
        
        Args:
            coroutine: 协程
            lane_id: 通道 ID
            lane_type: 通道类型
            timeout: 超时时间
            
        Returns:
            任务结果
        """
        result_future: asyncio.Future = asyncio.Future()
        
        async def wrapped_coroutine():
            try:
                result = await coroutine
                result_future.set_result(result)
            except Exception as e:
                result_future.set_exception(e)
                
        await self.submit(
            wrapped_coroutine(),
            lane_id=lane_id,
            lane_type=lane_type,
        )
        
        if timeout:
            return await asyncio.wait_for(result_future, timeout)
        return await result_future
        
    def get_lane_stats(self, lane_id: str) -> Optional[Dict[str, Any]]:
        """
        获取通道统计
        
        Args:
            lane_id: 通道 ID
            
        Returns:
            统计信息
        """
        lane = self._lanes.get(lane_id)
        if not lane:
            return None
            
        return {
            "lane_id": lane.lane_id,
            "lane_type": lane.lane_type.value,
            "max_concurrent": lane.max_concurrent,
            "current_count": lane.current_count,
            "queue_size": lane.queue.qsize(),
            "running_tasks": list(lane.running_tasks.keys()),
        }
        
    def get_all_stats(self) -> Dict[str, Any]:
        """获取所有统计"""
        return {
            lane_id: self.get_lane_stats(lane_id)
            for lane_id in self._lanes
        }
        
    async def cancel_task(self, task_id: str) -> bool:
        """
        取消任务
        
        Args:
            task_id: 任务 ID
            
        Returns:
            是否成功
        """
        for lane in self._lanes.values():
            if task_id in lane.running_tasks:
                # 无法取消正在运行的任务
                return False
                
        # 从队列中移除（需要遍历队列）
        return False  # 简化实现
        
    def cleanup_lane(self, lane_id: str) -> None:
        """清理通道"""
        if lane_id in self._lanes and lane_id != "subagent":
            del self._lanes[lane_id]
