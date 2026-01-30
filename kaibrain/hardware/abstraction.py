"""
硬件抽象层

提供统一的硬件访问接口，屏蔽底层硬件差异。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Type

from kaibrain.system.services.logger import LoggerMixin


class DeviceType(Enum):
    """设备类型"""
    # 传感器
    SENSOR_IMU = "sensor_imu"
    SENSOR_CAMERA = "sensor_camera"
    SENSOR_LIDAR = "sensor_lidar"
    SENSOR_FORCE = "sensor_force"
    SENSOR_ENCODER = "sensor_encoder"
    SENSOR_TACTILE = "sensor_tactile"
    
    # 执行器
    ACTUATOR_MOTOR = "actuator_motor"
    ACTUATOR_JOINT = "actuator_joint"
    ACTUATOR_GRIPPER = "actuator_gripper"
    
    # 计算单元
    COMPUTE_MAIN = "compute_main"
    COMPUTE_EDGE = "compute_edge"


class DeviceState(Enum):
    """设备状态"""
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    INITIALIZING = "initializing"
    READY = "ready"
    RUNNING = "running"
    ERROR = "error"
    DISABLED = "disabled"


@dataclass
class DeviceInfo:
    """设备信息"""
    device_id: str
    device_type: DeviceType
    name: str
    state: DeviceState = DeviceState.DISCONNECTED
    driver: str = ""
    firmware_version: str = ""
    config: Dict[str, Any] = field(default_factory=dict)
    last_update: datetime = field(default_factory=datetime.now)
    error_message: Optional[str] = None


# ============== 接口定义 ==============

class DeviceInterface(ABC):
    """设备接口基类"""
    
    @property
    @abstractmethod
    def device_info(self) -> DeviceInfo:
        """获取设备信息"""
        pass
        
    @abstractmethod
    async def connect(self) -> bool:
        """连接设备"""
        pass
        
    @abstractmethod
    async def disconnect(self) -> None:
        """断开设备"""
        pass
        
    @abstractmethod
    async def initialize(self) -> bool:
        """初始化设备"""
        pass
        
    @abstractmethod
    async def shutdown(self) -> None:
        """关闭设备"""
        pass
        
    @property
    @abstractmethod
    def is_ready(self) -> bool:
        """设备是否就绪"""
        pass


class SensorInterface(DeviceInterface):
    """
    传感器接口
    
    所有传感器驱动需要实现此接口。
    """
    
    @abstractmethod
    async def read(self) -> Dict[str, Any]:
        """
        读取传感器数据
        
        Returns:
            传感器数据
        """
        pass
        
    @abstractmethod
    async def get_calibration(self) -> Dict[str, Any]:
        """获取标定参数"""
        pass
        
    @abstractmethod
    async def set_calibration(self, params: Dict[str, Any]) -> bool:
        """设置标定参数"""
        pass


class ActuatorInterface(DeviceInterface):
    """
    执行器接口
    
    所有执行器驱动需要实现此接口。
    """
    
    @abstractmethod
    async def set_command(self, command: Dict[str, Any]) -> bool:
        """
        设置控制指令
        
        Args:
            command: 控制指令
            
        Returns:
            是否成功
        """
        pass
        
    @abstractmethod
    async def get_state(self) -> Dict[str, Any]:
        """
        获取执行器状态
        
        Returns:
            执行器状态
        """
        pass
        
    @abstractmethod
    async def emergency_stop(self) -> None:
        """紧急停止"""
        pass
        
    @abstractmethod
    async def enable(self) -> bool:
        """使能"""
        pass
        
    @abstractmethod
    async def disable(self) -> None:
        """失能"""
        pass


# ============== 控制接口 ==============

class MotionControlInterface(ABC):
    """
    运动控制接口
    
    控制系统软件层的运动控制模块需要实现此接口。
    """
    
    @abstractmethod
    async def set_joint_positions(
        self,
        positions: Dict[str, float],
        duration: float = 1.0,
    ) -> bool:
        """
        设置关节位置
        
        Args:
            positions: 关节名称到目标位置的映射
            duration: 运动时间（秒）
            
        Returns:
            是否成功
        """
        pass
        
    @abstractmethod
    async def set_joint_velocities(
        self,
        velocities: Dict[str, float],
    ) -> bool:
        """设置关节速度"""
        pass
        
    @abstractmethod
    async def set_cartesian_pose(
        self,
        position: Dict[str, float],
        orientation: Dict[str, float],
        duration: float = 1.0,
    ) -> bool:
        """设置笛卡尔空间位姿"""
        pass
        
    @abstractmethod
    async def get_joint_positions(self) -> Dict[str, float]:
        """获取当前关节位置"""
        pass
        
    @abstractmethod
    async def get_cartesian_pose(self) -> Dict[str, Any]:
        """获取当前笛卡尔位姿"""
        pass


class BalanceControlInterface(ABC):
    """
    平衡控制接口
    
    控制系统软件层的平衡控制模块需要实现此接口。
    """
    
    @abstractmethod
    async def get_com_position(self) -> Dict[str, float]:
        """获取质心位置"""
        pass
        
    @abstractmethod
    async def get_zmp(self) -> Dict[str, float]:
        """获取ZMP位置"""
        pass
        
    @abstractmethod
    async def is_balanced(self) -> bool:
        """检查是否平衡"""
        pass
        
    @abstractmethod
    async def enable_balance_control(self) -> bool:
        """启用平衡控制"""
        pass
        
    @abstractmethod
    async def disable_balance_control(self) -> None:
        """禁用平衡控制"""
        pass


class ForceControlInterface(ABC):
    """
    力控制接口
    
    控制系统软件层的力控制模块需要实现此接口。
    """
    
    @abstractmethod
    async def set_force_target(
        self,
        force: Dict[str, float],
        torque: Dict[str, float],
    ) -> bool:
        """设置目标力/力矩"""
        pass
        
    @abstractmethod
    async def get_current_force(self) -> Dict[str, float]:
        """获取当前力"""
        pass
        
    @abstractmethod
    async def set_impedance_params(
        self,
        stiffness: Dict[str, float],
        damping: Dict[str, float],
    ) -> bool:
        """设置阻抗参数"""
        pass
        
    @abstractmethod
    async def enable_collision_detection(self, threshold: float) -> bool:
        """启用碰撞检测"""
        pass


# ============== 硬件抽象层 ==============

class HardwareAbstraction(LoggerMixin):
    """
    硬件抽象层
    
    管理所有硬件设备，提供统一的访问接口。
    """
    
    def __init__(self):
        self._devices: Dict[str, DeviceInterface] = {}
        self._device_infos: Dict[str, DeviceInfo] = {}
        
        # 控制接口
        self._motion_control: Optional[MotionControlInterface] = None
        self._balance_control: Optional[BalanceControlInterface] = None
        self._force_control: Optional[ForceControlInterface] = None
        
    def register_device(self, device: DeviceInterface) -> None:
        """注册设备"""
        info = device.device_info
        self._devices[info.device_id] = device
        self._device_infos[info.device_id] = info
        self.logger.info(f"注册设备: {info.name} ({info.device_id})")
        
    def unregister_device(self, device_id: str) -> None:
        """注销设备"""
        if device_id in self._devices:
            del self._devices[device_id]
            del self._device_infos[device_id]
            self.logger.info(f"注销设备: {device_id}")
            
    def get_device(self, device_id: str) -> Optional[DeviceInterface]:
        """获取设备"""
        return self._devices.get(device_id)
        
    def get_devices_by_type(self, device_type: DeviceType) -> List[DeviceInterface]:
        """按类型获取设备"""
        return [
            device for device in self._devices.values()
            if device.device_info.device_type == device_type
        ]
        
    def list_devices(self) -> List[DeviceInfo]:
        """列出所有设备"""
        return list(self._device_infos.values())
        
    async def initialize_all(self) -> bool:
        """初始化所有设备"""
        success = True
        for device_id, device in self._devices.items():
            try:
                if await device.connect():
                    if await device.initialize():
                        self.logger.info(f"设备初始化成功: {device_id}")
                    else:
                        self.logger.error(f"设备初始化失败: {device_id}")
                        success = False
                else:
                    self.logger.error(f"设备连接失败: {device_id}")
                    success = False
            except Exception as e:
                self.logger.error(f"设备初始化异常: {device_id} - {e}")
                success = False
        return success
        
    async def shutdown_all(self) -> None:
        """关闭所有设备"""
        for device_id, device in self._devices.items():
            try:
                await device.shutdown()
                await device.disconnect()
                self.logger.info(f"设备关闭: {device_id}")
            except Exception as e:
                self.logger.error(f"设备关闭异常: {device_id} - {e}")
                
    def set_motion_control(self, control: MotionControlInterface) -> None:
        """设置运动控制模块"""
        self._motion_control = control
        
    def set_balance_control(self, control: BalanceControlInterface) -> None:
        """设置平衡控制模块"""
        self._balance_control = control
        
    def set_force_control(self, control: ForceControlInterface) -> None:
        """设置力控制模块"""
        self._force_control = control
        
    @property
    def motion_control(self) -> Optional[MotionControlInterface]:
        """获取运动控制模块"""
        return self._motion_control
        
    @property
    def balance_control(self) -> Optional[BalanceControlInterface]:
        """获取平衡控制模块"""
        return self._balance_control
        
    @property
    def force_control(self) -> Optional[ForceControlInterface]:
        """获取力控制模块"""
        return self._force_control
