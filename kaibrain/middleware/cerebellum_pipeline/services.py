"""
服务管理

管理ROS2服务的创建和调用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from kaibrain.system.services.logger import LoggerMixin

if TYPE_CHECKING:
    from kaibrain.middleware.cerebellum_pipeline.ros2_node import ROS2Node


@dataclass
class ServiceInfo:
    """服务信息"""
    name: str
    srv_type: str
    role: str  # server, client
    created_at: datetime = field(default_factory=datetime.now)
    call_count: int = 0
    last_call_time: Optional[datetime] = None


class ServiceManager(LoggerMixin):
    """
    服务管理器
    
    管理ROS2服务的注册和调用。
    """
    
    # 预定义的服务类型
    SERVICE_TYPES = {
        # 运动控制服务
        "motion.set_joint_positions": "control_msgs/SetJointPositions",
        "motion.set_cartesian_pose": "control_msgs/SetCartesianPose",
        "motion.stop": "std_srvs/Trigger",
        "motion.home": "std_srvs/Trigger",
        
        # 导航服务
        "nav.set_goal": "nav_msgs/SetGoal",
        "nav.cancel": "std_srvs/Trigger",
        
        # 夹爪服务
        "gripper.open": "std_srvs/Trigger",
        "gripper.close": "std_srvs/Trigger",
        "gripper.set_opening": "control_msgs/SetOpening",
        
        # 系统服务
        "system.get_state": "std_srvs/GetState",
        "system.emergency_stop": "std_srvs/Trigger",
        "system.reset": "std_srvs/Trigger",
    }
    
    def __init__(self, ros2_node: Optional[ROS2Node] = None):
        """
        初始化服务管理器
        
        Args:
            ros2_node: ROS2节点
        """
        self.ros2_node = ros2_node
        self._services: Dict[str, ServiceInfo] = {}
        self._handlers: Dict[str, Callable] = {}
        
    def register_service(
        self,
        service_name: str,
        handler: Callable,
        srv_type: Optional[Any] = None,
    ) -> ServiceInfo:
        """
        注册服务（作为服务端）
        
        Args:
            service_name: 服务名称
            handler: 服务处理函数
            srv_type: 服务类型
            
        Returns:
            ServiceInfo
        """
        # 保存处理函数
        self._handlers[service_name] = handler
        
        # 获取服务类型
        type_str = self.SERVICE_TYPES.get(service_name, "std_srvs/Trigger")
        
        # 创建服务
        if self.ros2_node:
            self.ros2_node.create_service(service_name, srv_type, self._service_callback)
            
        # 记录服务信息
        info = ServiceInfo(
            name=service_name,
            srv_type=type_str,
            role="server",
        )
        self._services[service_name] = info
        
        self.logger.info(f"注册服务: {service_name}")
        return info
        
    def register_client(
        self,
        service_name: str,
        srv_type: Optional[Any] = None,
    ) -> ServiceInfo:
        """
        注册服务客户端
        
        Args:
            service_name: 服务名称
            srv_type: 服务类型
            
        Returns:
            ServiceInfo
        """
        # 获取服务类型
        type_str = self.SERVICE_TYPES.get(service_name, "std_srvs/Trigger")
        
        # 创建客户端
        if self.ros2_node:
            self.ros2_node.create_client(service_name, srv_type)
            
        # 记录服务信息
        info = ServiceInfo(
            name=service_name,
            srv_type=type_str,
            role="client",
        )
        self._services[service_name] = info
        
        self.logger.info(f"注册客户端: {service_name}")
        return info
        
    def _service_callback(self, request: Any, response: Any) -> Any:
        """服务回调"""
        service_name = getattr(request, '_service_name', 'unknown')
        
        handler = self._handlers.get(service_name)
        if handler:
            try:
                return handler(request, response)
            except Exception as e:
                self.logger.error(f"服务处理错误 [{service_name}]: {e}")
                
        return response
        
    async def call(
        self,
        service_name: str,
        request: Any,
        timeout: float = 5.0,
    ) -> Optional[Any]:
        """
        调用服务
        
        Args:
            service_name: 服务名称
            request: 请求
            timeout: 超时时间
            
        Returns:
            响应
        """
        if service_name not in self._services:
            self.logger.warning(f"服务未注册: {service_name}")
            return None
            
        info = self._services[service_name]
        if info.role != "client":
            self.logger.warning(f"不是客户端: {service_name}")
            return None
            
        response = None
        if self.ros2_node:
            response = await self.ros2_node.call_service(service_name, request, timeout)
            
        # 更新统计
        info.call_count += 1
        info.last_call_time = datetime.now()
        
        return response
        
    def get_service_info(self, service_name: str) -> Optional[ServiceInfo]:
        """获取服务信息"""
        return self._services.get(service_name)
        
    def list_services(self) -> List[ServiceInfo]:
        """列出所有服务"""
        return list(self._services.values())
