"""
进程管理服务

负责 Agent/服务的生命周期管理、启停控制、依赖关系管理。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

from kaibrain.system.services.logger import LoggerMixin


class ProcessState(Enum):
    """进程状态"""
    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass
class ProcessInfo:
    """进程信息"""
    process_id: str
    name: str
    state: ProcessState = ProcessState.CREATED
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    error: Optional[str] = None
    dependencies: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)


class ProcessManager(LoggerMixin):
    """
    进程管理器
    
    管理所有Agent和服务的生命周期。
    """
    
    def __init__(self):
        self._processes: Dict[str, ProcessInfo] = {}
        self._start_handlers: Dict[str, Callable] = {}
        self._stop_handlers: Dict[str, Callable] = {}
        self._lock = asyncio.Lock()
        
    async def register(
        self,
        process_id: str,
        name: str,
        start_handler: Callable,
        stop_handler: Callable,
        dependencies: Optional[Set[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ProcessInfo:
        """
        注册进程
        
        Args:
            process_id: 进程ID
            name: 进程名称
            start_handler: 启动处理函数
            stop_handler: 停止处理函数
            dependencies: 依赖的进程ID集合
            metadata: 元数据
            
        Returns:
            ProcessInfo 实例
        """
        async with self._lock:
            if process_id in self._processes:
                raise ValueError(f"进程已存在: {process_id}")
                
            info = ProcessInfo(
                process_id=process_id,
                name=name,
                dependencies=dependencies or set(),
                metadata=metadata or {},
            )
            
            self._processes[process_id] = info
            self._start_handlers[process_id] = start_handler
            self._stop_handlers[process_id] = stop_handler
            
            self.logger.info(f"注册进程: {name} ({process_id})")
            return info
            
    async def unregister(self, process_id: str) -> None:
        """注销进程"""
        async with self._lock:
            if process_id not in self._processes:
                return
                
            info = self._processes[process_id]
            if info.state == ProcessState.RUNNING:
                await self.stop(process_id)
                
            del self._processes[process_id]
            del self._start_handlers[process_id]
            del self._stop_handlers[process_id]
            
            self.logger.info(f"注销进程: {info.name} ({process_id})")
            
    async def start(self, process_id: str) -> None:
        """
        启动进程
        
        会先启动所有依赖的进程。
        """
        info = self._processes.get(process_id)
        if not info:
            raise ValueError(f"进程不存在: {process_id}")
            
        if info.state == ProcessState.RUNNING:
            return
            
        # 先启动依赖
        for dep_id in info.dependencies:
            await self.start(dep_id)
            
        info.state = ProcessState.STARTING
        
        try:
            handler = self._start_handlers[process_id]
            if asyncio.iscoroutinefunction(handler):
                await handler()
            else:
                handler()
                
            info.state = ProcessState.RUNNING
            info.started_at = datetime.now()
            self.logger.info(f"进程启动成功: {info.name}")
            
        except Exception as e:
            info.state = ProcessState.FAILED
            info.error = str(e)
            self.logger.error(f"进程启动失败: {info.name} - {e}")
            raise
            
    async def stop(self, process_id: str) -> None:
        """停止进程"""
        info = self._processes.get(process_id)
        if not info:
            return
            
        if info.state != ProcessState.RUNNING:
            return
            
        info.state = ProcessState.STOPPING
        
        try:
            handler = self._stop_handlers[process_id]
            if asyncio.iscoroutinefunction(handler):
                await handler()
            else:
                handler()
                
            info.state = ProcessState.STOPPED
            info.stopped_at = datetime.now()
            self.logger.info(f"进程停止成功: {info.name}")
            
        except Exception as e:
            info.state = ProcessState.FAILED
            info.error = str(e)
            self.logger.error(f"进程停止失败: {info.name} - {e}")
            
    async def start_all(self) -> None:
        """启动所有进程"""
        for process_id in self._processes:
            if self._processes[process_id].state != ProcessState.RUNNING:
                await self.start(process_id)
                
    async def stop_all(self) -> None:
        """停止所有进程"""
        # 按依赖关系反向停止
        for process_id in reversed(list(self._processes.keys())):
            await self.stop(process_id)
            
    def get_info(self, process_id: str) -> Optional[ProcessInfo]:
        """获取进程信息"""
        return self._processes.get(process_id)
        
    def list_processes(self) -> List[ProcessInfo]:
        """列出所有进程"""
        return list(self._processes.values())
