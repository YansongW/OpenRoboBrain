"""
状态同步

保持大脑和小脑对机器人状态的一致视图。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from kaibrain.system.services.logger import LoggerMixin

if TYPE_CHECKING:
    from kaibrain.system.brain_pipeline.message_bus import MessageBus
    from kaibrain.system.brain_pipeline.bridge import PipelineBridge


@dataclass
class RobotState:
    """机器人状态"""
    # 基本信息
    timestamp: datetime = field(default_factory=datetime.now)
    
    # 位姿状态
    position: Dict[str, float] = field(default_factory=lambda: {"x": 0.0, "y": 0.0, "z": 0.0})
    orientation: Dict[str, float] = field(default_factory=lambda: {"roll": 0.0, "pitch": 0.0, "yaw": 0.0})
    
    # 关节状态
    joint_positions: Dict[str, float] = field(default_factory=dict)
    joint_velocities: Dict[str, float] = field(default_factory=dict)
    
    # 传感器状态
    battery_level: float = 100.0
    temperature: float = 25.0
    
    # 运行状态
    is_moving: bool = False
    is_stable: bool = True
    current_action: str = "idle"
    
    # 错误状态
    errors: List[str] = field(default_factory=list)


@dataclass
class EnvironmentState:
    """环境状态"""
    timestamp: datetime = field(default_factory=datetime.now)
    
    # 检测到的物体
    detected_objects: List[Dict[str, Any]] = field(default_factory=list)
    
    # 检测到的人
    detected_persons: List[Dict[str, Any]] = field(default_factory=list)
    
    # 障碍物
    obstacles: List[Dict[str, Any]] = field(default_factory=list)
    
    # 场景信息
    scene_description: str = ""
    lighting_condition: str = "normal"


@dataclass
class TaskState:
    """任务状态"""
    timestamp: datetime = field(default_factory=datetime.now)
    
    # 当前任务
    current_task_id: Optional[str] = None
    current_task_type: str = ""
    current_task_progress: float = 0.0
    
    # 任务队列
    pending_tasks: List[str] = field(default_factory=list)
    completed_tasks: List[str] = field(default_factory=list)


class StateSync(LoggerMixin):
    """
    状态同步器
    
    维护大脑和小脑共享的状态视图。
    """
    
    def __init__(
        self,
        message_bus: Optional[MessageBus] = None,
        bridge: Optional[PipelineBridge] = None,
    ):
        """
        初始化状态同步器
        
        Args:
            message_bus: 大脑管道消息总线
            bridge: 管道桥接器
        """
        self.message_bus = message_bus
        self.bridge = bridge
        
        # 状态存储
        self._robot_state = RobotState()
        self._environment_state = EnvironmentState()
        self._task_state = TaskState()
        
        # 同步控制
        self._running = False
        self._sync_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        
        # 状态变更回调
        self._state_callbacks: List[callable] = []
        
    async def initialize(self) -> None:
        """初始化状态同步器"""
        self.logger.info("初始化状态同步器...")
        self._running = True
        
    async def shutdown(self) -> None:
        """关闭状态同步器"""
        self.logger.info("关闭状态同步器...")
        self._running = False
        
        if self._sync_task and not self._sync_task.done():
            self._sync_task.cancel()
            
    async def update_robot_state(self, updates: Dict[str, Any]) -> None:
        """
        更新机器人状态
        
        Args:
            updates: 状态更新
        """
        async with self._lock:
            for key, value in updates.items():
                if hasattr(self._robot_state, key):
                    setattr(self._robot_state, key, value)
                    
            self._robot_state.timestamp = datetime.now()
            
        await self._notify_state_change("robot", updates)
        
    async def update_environment_state(self, updates: Dict[str, Any]) -> None:
        """更新环境状态"""
        async with self._lock:
            for key, value in updates.items():
                if hasattr(self._environment_state, key):
                    setattr(self._environment_state, key, value)
                    
            self._environment_state.timestamp = datetime.now()
            
        await self._notify_state_change("environment", updates)
        
    async def update_task_state(self, updates: Dict[str, Any]) -> None:
        """更新任务状态"""
        async with self._lock:
            for key, value in updates.items():
                if hasattr(self._task_state, key):
                    setattr(self._task_state, key, value)
                    
            self._task_state.timestamp = datetime.now()
            
        await self._notify_state_change("task", updates)
        
    def get_robot_state(self) -> RobotState:
        """获取机器人状态"""
        return self._robot_state
        
    def get_environment_state(self) -> EnvironmentState:
        """获取环境状态"""
        return self._environment_state
        
    def get_task_state(self) -> TaskState:
        """获取任务状态"""
        return self._task_state
        
    def get_full_state(self) -> Dict[str, Any]:
        """获取完整状态"""
        return {
            "robot": self._robot_state.__dict__,
            "environment": self._environment_state.__dict__,
            "task": self._task_state.__dict__,
        }
        
    def add_state_callback(self, callback: callable) -> None:
        """添加状态变更回调"""
        self._state_callbacks.append(callback)
        
    async def _notify_state_change(self, state_type: str, updates: Dict[str, Any]) -> None:
        """通知状态变更"""
        for callback in self._state_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(state_type, updates)
                else:
                    callback(state_type, updates)
            except Exception as e:
                self.logger.error(f"状态回调执行错误: {e}")
