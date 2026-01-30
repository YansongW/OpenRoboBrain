"""
传感器接口定义

定义各类传感器的具体接口。
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from kaibrain.hardware.abstraction import (
    SensorInterface,
    DeviceInfo,
    DeviceType,
    DeviceState,
)


# ============== IMU 传感器 ==============

@dataclass
class IMUData:
    """IMU数据"""
    timestamp: datetime = field(default_factory=datetime.now)
    
    # 加速度 (m/s^2)
    acceleration: Dict[str, float] = field(default_factory=lambda: {"x": 0.0, "y": 0.0, "z": 0.0})
    
    # 角速度 (rad/s)
    angular_velocity: Dict[str, float] = field(default_factory=lambda: {"x": 0.0, "y": 0.0, "z": 0.0})
    
    # 姿态 (rad)
    orientation: Dict[str, float] = field(default_factory=lambda: {"roll": 0.0, "pitch": 0.0, "yaw": 0.0})
    
    # 四元数
    quaternion: Dict[str, float] = field(default_factory=lambda: {"w": 1.0, "x": 0.0, "y": 0.0, "z": 0.0})


class IMUSensor(SensorInterface):
    """IMU传感器接口"""
    
    @abstractmethod
    async def read_imu(self) -> IMUData:
        """读取IMU数据"""
        pass
        
    @abstractmethod
    async def reset_orientation(self) -> bool:
        """重置姿态"""
        pass


# ============== 相机传感器 ==============

@dataclass
class CameraData:
    """相机数据"""
    timestamp: datetime = field(default_factory=datetime.now)
    
    # RGB图像 (numpy array)
    rgb_image: Optional[Any] = None
    
    # 深度图像
    depth_image: Optional[Any] = None
    
    # 点云
    point_cloud: Optional[Any] = None
    
    # 相机内参
    intrinsics: Dict[str, float] = field(default_factory=dict)


class CameraSensor(SensorInterface):
    """相机传感器接口"""
    
    @abstractmethod
    async def read_rgb(self) -> Optional[Any]:
        """读取RGB图像"""
        pass
        
    @abstractmethod
    async def read_depth(self) -> Optional[Any]:
        """读取深度图像"""
        pass
        
    @abstractmethod
    async def read_point_cloud(self) -> Optional[Any]:
        """读取点云"""
        pass
        
    @abstractmethod
    async def set_resolution(self, width: int, height: int) -> bool:
        """设置分辨率"""
        pass
        
    @abstractmethod
    async def set_fps(self, fps: int) -> bool:
        """设置帧率"""
        pass


# ============== 激光雷达传感器 ==============

@dataclass
class LidarData:
    """激光雷达数据"""
    timestamp: datetime = field(default_factory=datetime.now)
    
    # 点云 (N x 3 array)
    point_cloud: Optional[Any] = None
    
    # 距离数据
    ranges: List[float] = field(default_factory=list)
    
    # 角度范围
    angle_min: float = 0.0
    angle_max: float = 6.28  # 2*pi
    angle_increment: float = 0.01


class LidarSensor(SensorInterface):
    """激光雷达传感器接口"""
    
    @abstractmethod
    async def read_scan(self) -> LidarData:
        """读取扫描数据"""
        pass
        
    @abstractmethod
    async def set_scan_range(self, angle_min: float, angle_max: float) -> bool:
        """设置扫描范围"""
        pass


# ============== 力/力矩传感器 ==============

@dataclass
class ForceData:
    """力/力矩数据"""
    timestamp: datetime = field(default_factory=datetime.now)
    
    # 力 (N)
    force: Dict[str, float] = field(default_factory=lambda: {"x": 0.0, "y": 0.0, "z": 0.0})
    
    # 力矩 (Nm)
    torque: Dict[str, float] = field(default_factory=lambda: {"x": 0.0, "y": 0.0, "z": 0.0})


class ForceSensor(SensorInterface):
    """力/力矩传感器接口"""
    
    @abstractmethod
    async def read_force(self) -> ForceData:
        """读取力/力矩数据"""
        pass
        
    @abstractmethod
    async def zero(self) -> bool:
        """零点校准"""
        pass
        
    @abstractmethod
    async def set_filter(self, cutoff_freq: float) -> bool:
        """设置滤波器"""
        pass
