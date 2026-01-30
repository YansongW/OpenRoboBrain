"""
执行器接口定义

定义各类执行器的具体接口。
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from kaibrain.hardware.abstraction import (
    ActuatorInterface,
    DeviceInfo,
    DeviceType,
    DeviceState,
)


# ============== 电机执行器 ==============

class ControlMode(Enum):
    """控制模式"""
    POSITION = "position"
    VELOCITY = "velocity"
    TORQUE = "torque"
    IMPEDANCE = "impedance"


@dataclass
class MotorState:
    """电机状态"""
    timestamp: datetime = field(default_factory=datetime.now)
    
    # 位置 (rad)
    position: float = 0.0
    
    # 速度 (rad/s)
    velocity: float = 0.0
    
    # 力矩 (Nm)
    torque: float = 0.0
    
    # 电流 (A)
    current: float = 0.0
    
    # 温度 (°C)
    temperature: float = 25.0
    
    # 控制模式
    control_mode: ControlMode = ControlMode.POSITION
    
    # 是否使能
    is_enabled: bool = False
    
    # 是否有错误
    has_error: bool = False
    error_code: int = 0


class MotorActuator(ActuatorInterface):
    """电机执行器接口"""
    
    @abstractmethod
    async def set_position(self, position: float, velocity: float = 0.0) -> bool:
        """设置目标位置"""
        pass
        
    @abstractmethod
    async def set_velocity(self, velocity: float) -> bool:
        """设置目标速度"""
        pass
        
    @abstractmethod
    async def set_torque(self, torque: float) -> bool:
        """设置目标力矩"""
        pass
        
    @abstractmethod
    async def set_control_mode(self, mode: ControlMode) -> bool:
        """设置控制模式"""
        pass
        
    @abstractmethod
    async def read_motor_state(self) -> MotorState:
        """读取电机状态"""
        pass
        
    @abstractmethod
    async def set_pid_gains(
        self,
        kp: float,
        ki: float,
        kd: float,
    ) -> bool:
        """设置PID参数"""
        pass


# ============== 关节执行器 ==============

@dataclass
class JointState:
    """关节状态"""
    timestamp: datetime = field(default_factory=datetime.now)
    
    # 关节名称
    name: str = ""
    
    # 位置 (rad)
    position: float = 0.0
    
    # 速度 (rad/s)
    velocity: float = 0.0
    
    # 加速度 (rad/s^2)
    acceleration: float = 0.0
    
    # 力矩 (Nm)
    torque: float = 0.0
    
    # 关节限位
    position_min: float = -3.14
    position_max: float = 3.14
    
    # 是否到达限位
    at_limit: bool = False


class JointActuator(ActuatorInterface):
    """关节执行器接口"""
    
    @abstractmethod
    async def set_joint_position(
        self,
        position: float,
        velocity: float = 1.0,
        acceleration: float = 1.0,
    ) -> bool:
        """设置关节位置"""
        pass
        
    @abstractmethod
    async def set_joint_velocity(self, velocity: float) -> bool:
        """设置关节速度"""
        pass
        
    @abstractmethod
    async def set_joint_torque(self, torque: float) -> bool:
        """设置关节力矩"""
        pass
        
    @abstractmethod
    async def read_joint_state(self) -> JointState:
        """读取关节状态"""
        pass
        
    @abstractmethod
    async def go_home(self) -> bool:
        """回到初始位置"""
        pass
        
    @abstractmethod
    async def check_limits(self) -> bool:
        """检查是否在限位内"""
        pass


# ============== 夹爪执行器 ==============

class GripperState(Enum):
    """夹爪状态"""
    OPEN = "open"
    CLOSED = "closed"
    MOVING = "moving"
    HOLDING = "holding"
    ERROR = "error"


@dataclass
class GripperInfo:
    """夹爪信息"""
    timestamp: datetime = field(default_factory=datetime.now)
    
    # 开合度 (0-1, 0=全闭合, 1=全张开)
    opening: float = 1.0
    
    # 夹持力 (N)
    force: float = 0.0
    
    # 状态
    state: GripperState = GripperState.OPEN
    
    # 是否检测到物体
    object_detected: bool = False


class GripperActuator(ActuatorInterface):
    """夹爪执行器接口"""
    
    @abstractmethod
    async def open(self, speed: float = 1.0) -> bool:
        """打开夹爪"""
        pass
        
    @abstractmethod
    async def close(self, force: float = 10.0) -> bool:
        """闭合夹爪"""
        pass
        
    @abstractmethod
    async def set_opening(self, opening: float, speed: float = 1.0) -> bool:
        """设置开合度"""
        pass
        
    @abstractmethod
    async def set_force(self, force: float) -> bool:
        """设置夹持力"""
        pass
        
    @abstractmethod
    async def read_gripper_info(self) -> GripperInfo:
        """读取夹爪信息"""
        pass
        
    @abstractmethod
    async def is_holding_object(self) -> bool:
        """是否夹持物体"""
        pass
