"""
资源调度服务

负责 CPU/GPU/内存 资源分配、任务优先级调度、资源隔离与限制。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from kaibrain.system.services.logger import LoggerMixin


class TaskPriority(IntEnum):
    """任务优先级"""
    CRITICAL = 0  # 关键任务（安全相关）
    HIGH = 1      # 高优先级
    NORMAL = 2    # 普通优先级
    LOW = 3       # 低优先级
    BACKGROUND = 4  # 后台任务


@dataclass
class ResourceRequest:
    """资源请求"""
    request_id: str = field(default_factory=lambda: str(uuid4()))
    requester_id: str = ""
    cpu_cores: float = 1.0  # CPU核心数
    memory_mb: int = 512    # 内存MB
    gpu_memory_mb: int = 0  # GPU显存MB
    priority: TaskPriority = TaskPriority.NORMAL
    timeout: float = 60.0   # 超时时间（秒）
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class ResourceAllocation:
    """资源分配"""
    allocation_id: str = field(default_factory=lambda: str(uuid4()))
    request: ResourceRequest = field(default_factory=ResourceRequest)
    allocated_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    is_active: bool = True


class ResourceScheduler(LoggerMixin):
    """
    资源调度器
    
    管理系统资源的分配和调度。
    """
    
    def __init__(
        self,
        total_cpu_cores: float = 8.0,
        total_memory_mb: int = 16384,
        total_gpu_memory_mb: int = 0,
    ):
        """
        初始化资源调度器
        
        Args:
            total_cpu_cores: 总CPU核心数
            total_memory_mb: 总内存MB
            total_gpu_memory_mb: 总GPU显存MB
        """
        self.total_cpu_cores = total_cpu_cores
        self.total_memory_mb = total_memory_mb
        self.total_gpu_memory_mb = total_gpu_memory_mb
        
        self._allocations: Dict[str, ResourceAllocation] = {}
        self._pending_requests: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._lock = asyncio.Lock()
        
    @property
    def available_cpu_cores(self) -> float:
        """可用CPU核心数"""
        used = sum(
            a.request.cpu_cores for a in self._allocations.values() if a.is_active
        )
        return max(0, self.total_cpu_cores - used)
        
    @property
    def available_memory_mb(self) -> int:
        """可用内存MB"""
        used = sum(
            a.request.memory_mb for a in self._allocations.values() if a.is_active
        )
        return max(0, self.total_memory_mb - used)
        
    @property
    def available_gpu_memory_mb(self) -> int:
        """可用GPU显存MB"""
        used = sum(
            a.request.gpu_memory_mb for a in self._allocations.values() if a.is_active
        )
        return max(0, self.total_gpu_memory_mb - used)
        
    async def request_resources(self, request: ResourceRequest) -> Optional[ResourceAllocation]:
        """
        请求资源
        
        Args:
            request: 资源请求
            
        Returns:
            ResourceAllocation 如果分配成功，否则 None
        """
        async with self._lock:
            # 检查资源是否足够
            if not self._can_allocate(request):
                self.logger.warning(
                    f"资源不足，请求被排队: {request.requester_id}"
                )
                return None
                
            # 创建分配
            allocation = ResourceAllocation(request=request)
            self._allocations[allocation.allocation_id] = allocation
            
            self.logger.info(
                f"资源分配成功: {request.requester_id} - "
                f"CPU: {request.cpu_cores}, MEM: {request.memory_mb}MB"
            )
            
            return allocation
            
    async def release_resources(self, allocation_id: str) -> None:
        """
        释放资源
        
        Args:
            allocation_id: 分配ID
        """
        async with self._lock:
            if allocation_id in self._allocations:
                allocation = self._allocations[allocation_id]
                allocation.is_active = False
                del self._allocations[allocation_id]
                
                self.logger.info(
                    f"资源释放: {allocation.request.requester_id}"
                )
                
    def _can_allocate(self, request: ResourceRequest) -> bool:
        """检查是否可以分配资源"""
        return (
            request.cpu_cores <= self.available_cpu_cores
            and request.memory_mb <= self.available_memory_mb
            and request.gpu_memory_mb <= self.available_gpu_memory_mb
        )
        
    def get_stats(self) -> Dict[str, Any]:
        """获取资源统计"""
        return {
            "cpu": {
                "total": self.total_cpu_cores,
                "available": self.available_cpu_cores,
                "used": self.total_cpu_cores - self.available_cpu_cores,
            },
            "memory": {
                "total_mb": self.total_memory_mb,
                "available_mb": self.available_memory_mb,
                "used_mb": self.total_memory_mb - self.available_memory_mb,
            },
            "gpu_memory": {
                "total_mb": self.total_gpu_memory_mb,
                "available_mb": self.available_gpu_memory_mb,
                "used_mb": self.total_gpu_memory_mb - self.available_gpu_memory_mb,
            },
            "active_allocations": len(self._allocations),
        }
