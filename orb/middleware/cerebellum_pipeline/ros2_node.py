"""
ROS2节点封装

提供ROS2节点的统一封装，方便与ROS2系统集成。
注意：实际使用需要安装ROS2环境和rclpy。
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING
from dataclasses import dataclass, field

from orb.system.services.logger import LoggerMixin

# ROS2 是可选依赖
try:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
    ROS2_AVAILABLE = True
except ImportError:
    ROS2_AVAILABLE = False
    Node = object


@dataclass
class TopicConfig:
    """话题配置"""
    name: str
    msg_type: str
    qos_reliability: str = "reliable"  # reliable, best_effort
    qos_history: str = "keep_last"     # keep_last, keep_all
    qos_depth: int = 10


@dataclass
class ServiceConfig:
    """服务配置"""
    name: str
    srv_type: str


class ROS2Node(LoggerMixin):
    """
    ROS2节点封装
    
    封装ROS2节点的创建、发布、订阅等功能。
    如果ROS2不可用，会以模拟模式运行。
    """
    
    def __init__(self, node_name: str = "orb_node"):
        """
        初始化ROS2节点
        
        Args:
            node_name: 节点名称
        """
        self.node_name = node_name
        self._node: Optional[Any] = None
        self._publishers: Dict[str, Any] = {}
        self._subscribers: Dict[str, Any] = {}
        self._services: Dict[str, Any] = {}
        self._clients: Dict[str, Any] = {}
        self._running = False
        self._spin_task: Optional[asyncio.Task] = None
        
        # 消息回调
        self._topic_callbacks: Dict[str, List[Callable]] = {}
        
    @property
    def is_ros2_available(self) -> bool:
        """ROS2是否可用"""
        return ROS2_AVAILABLE
        
    async def initialize(self) -> bool:
        """
        初始化ROS2节点
        
        Returns:
            是否成功
        """
        if not ROS2_AVAILABLE:
            self.logger.warning("ROS2不可用，以模拟模式运行")
            self._running = True
            return True
            
        try:
            if not rclpy.ok():
                rclpy.init()
                
            self._node = rclpy.create_node(self.node_name)
            self._running = True
            
            # 启动spin任务
            self._spin_task = asyncio.create_task(self._spin_loop())
            
            self.logger.info(f"ROS2节点初始化成功: {self.node_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"ROS2节点初始化失败: {e}")
            return False
            
    async def shutdown(self) -> None:
        """关闭ROS2节点"""
        self._running = False
        
        if self._spin_task and not self._spin_task.done():
            self._spin_task.cancel()
            try:
                await self._spin_task
            except asyncio.CancelledError:
                pass
                
        if self._node and ROS2_AVAILABLE:
            self._node.destroy_node()
            if rclpy.ok():
                rclpy.shutdown()
                
        self.logger.info(f"ROS2节点已关闭: {self.node_name}")
        
    async def _spin_loop(self) -> None:
        """ROS2 spin循环"""
        if not ROS2_AVAILABLE or not self._node:
            return
            
        while self._running:
            rclpy.spin_once(self._node, timeout_sec=0.1)
            await asyncio.sleep(0.01)
            
    def create_publisher(
        self,
        topic_name: str,
        msg_type: Any,
        qos_depth: int = 10,
    ) -> Optional[Any]:
        """
        创建发布者
        
        Args:
            topic_name: 话题名称
            msg_type: 消息类型
            qos_depth: QoS深度
            
        Returns:
            发布者对象
        """
        if not ROS2_AVAILABLE or not self._node:
            self.logger.debug(f"[模拟] 创建发布者: {topic_name}")
            self._publishers[topic_name] = {"topic": topic_name, "msg_type": msg_type}
            return None
            
        publisher = self._node.create_publisher(msg_type, topic_name, qos_depth)
        self._publishers[topic_name] = publisher
        self.logger.info(f"创建发布者: {topic_name}")
        return publisher
        
    def create_subscriber(
        self,
        topic_name: str,
        msg_type: Any,
        callback: Callable,
        qos_depth: int = 10,
    ) -> Optional[Any]:
        """
        创建订阅者
        
        Args:
            topic_name: 话题名称
            msg_type: 消息类型
            callback: 消息回调函数
            qos_depth: QoS深度
            
        Returns:
            订阅者对象
        """
        # 注册回调
        if topic_name not in self._topic_callbacks:
            self._topic_callbacks[topic_name] = []
        self._topic_callbacks[topic_name].append(callback)
        
        if not ROS2_AVAILABLE or not self._node:
            self.logger.debug(f"[模拟] 创建订阅者: {topic_name}")
            self._subscribers[topic_name] = {"topic": topic_name, "msg_type": msg_type}
            return None
            
        subscriber = self._node.create_subscription(
            msg_type, topic_name, callback, qos_depth
        )
        self._subscribers[topic_name] = subscriber
        self.logger.info(f"创建订阅者: {topic_name}")
        return subscriber
        
    async def publish(self, topic_name: str, message: Any) -> bool:
        """
        发布消息
        
        Args:
            topic_name: 话题名称
            message: 消息
            
        Returns:
            是否成功
        """
        if topic_name not in self._publishers:
            self.logger.warning(f"发布者不存在: {topic_name}")
            return False
            
        if not ROS2_AVAILABLE:
            # 模拟模式：直接调用订阅者回调
            callbacks = self._topic_callbacks.get(topic_name, [])
            for callback in callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(message)
                    else:
                        callback(message)
                except Exception as e:
                    self.logger.error(f"回调执行错误: {e}")
            return True
            
        publisher = self._publishers[topic_name]
        publisher.publish(message)
        return True
        
    def create_service(
        self,
        service_name: str,
        srv_type: Any,
        callback: Callable,
    ) -> Optional[Any]:
        """
        创建服务
        
        Args:
            service_name: 服务名称
            srv_type: 服务类型
            callback: 服务回调函数
            
        Returns:
            服务对象
        """
        if not ROS2_AVAILABLE or not self._node:
            self.logger.debug(f"[模拟] 创建服务: {service_name}")
            self._services[service_name] = {"name": service_name, "callback": callback}
            return None
            
        service = self._node.create_service(srv_type, service_name, callback)
        self._services[service_name] = service
        self.logger.info(f"创建服务: {service_name}")
        return service
        
    def create_client(
        self,
        service_name: str,
        srv_type: Any,
    ) -> Optional[Any]:
        """
        创建服务客户端
        
        Args:
            service_name: 服务名称
            srv_type: 服务类型
            
        Returns:
            客户端对象
        """
        if not ROS2_AVAILABLE or not self._node:
            self.logger.debug(f"[模拟] 创建客户端: {service_name}")
            self._clients[service_name] = {"name": service_name, "srv_type": srv_type}
            return None
            
        client = self._node.create_client(srv_type, service_name)
        self._clients[service_name] = client
        self.logger.info(f"创建客户端: {service_name}")
        return client
        
    async def call_service(
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
        if service_name not in self._clients:
            self.logger.warning(f"客户端不存在: {service_name}")
            return None
            
        if not ROS2_AVAILABLE:
            # 模拟模式：直接调用服务回调
            service = self._services.get(service_name)
            if service and "callback" in service:
                return service["callback"](request, None)
            return None
            
        client = self._clients[service_name]
        
        if not client.wait_for_service(timeout_sec=timeout):
            self.logger.warning(f"服务不可用: {service_name}")
            return None
            
        future = client.call_async(request)
        
        try:
            response = await asyncio.wait_for(
                asyncio.wrap_future(future),
                timeout=timeout,
            )
            return response
        except asyncio.TimeoutError:
            self.logger.warning(f"服务调用超时: {service_name}")
            return None
