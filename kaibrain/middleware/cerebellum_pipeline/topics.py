"""
话题管理

管理ROS2话题的发布和订阅。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from kaibrain.system.services.logger import LoggerMixin

if TYPE_CHECKING:
    from kaibrain.middleware.cerebellum_pipeline.ros2_node import ROS2Node


@dataclass
class TopicInfo:
    """话题信息"""
    name: str
    msg_type: str
    direction: str  # publish, subscribe
    qos_depth: int = 10
    created_at: datetime = field(default_factory=datetime.now)
    message_count: int = 0
    last_message_time: Optional[datetime] = None


class TopicManager(LoggerMixin):
    """
    话题管理器
    
    管理所有ROS2话题的注册、发布和订阅。
    """
    
    # 预定义的话题类型
    TOPIC_TYPES = {
        # 传感器话题
        "sensor.imu": "sensor_msgs/Imu",
        "sensor.camera.rgb": "sensor_msgs/Image",
        "sensor.camera.depth": "sensor_msgs/Image",
        "sensor.lidar": "sensor_msgs/LaserScan",
        "sensor.force": "geometry_msgs/WrenchStamped",
        
        # 状态话题
        "state.robot": "std_msgs/String",
        "state.joint": "sensor_msgs/JointState",
        "state.odom": "nav_msgs/Odometry",
        
        # 控制话题
        "control.joint_cmd": "trajectory_msgs/JointTrajectory",
        "control.velocity": "geometry_msgs/Twist",
        "control.force": "geometry_msgs/WrenchStamped",
        
        # 导航话题
        "nav.goal": "geometry_msgs/PoseStamped",
        "nav.path": "nav_msgs/Path",
        "nav.map": "nav_msgs/OccupancyGrid",
    }
    
    def __init__(self, ros2_node: Optional[ROS2Node] = None):
        """
        初始化话题管理器
        
        Args:
            ros2_node: ROS2节点
        """
        self.ros2_node = ros2_node
        self._topics: Dict[str, TopicInfo] = {}
        self._callbacks: Dict[str, List[Callable]] = {}
        
    def register_publisher(
        self,
        topic_name: str,
        msg_type: Optional[Any] = None,
        qos_depth: int = 10,
    ) -> TopicInfo:
        """
        注册发布者
        
        Args:
            topic_name: 话题名称
            msg_type: 消息类型（如果为None则从预定义类型查找）
            qos_depth: QoS深度
            
        Returns:
            TopicInfo
        """
        # 获取消息类型
        type_str = self.TOPIC_TYPES.get(topic_name, "std_msgs/String")
        
        # 创建发布者
        if self.ros2_node:
            self.ros2_node.create_publisher(topic_name, msg_type, qos_depth)
            
        # 记录话题信息
        info = TopicInfo(
            name=topic_name,
            msg_type=type_str,
            direction="publish",
            qos_depth=qos_depth,
        )
        self._topics[topic_name] = info
        
        self.logger.info(f"注册发布者: {topic_name}")
        return info
        
    def register_subscriber(
        self,
        topic_name: str,
        callback: Callable,
        msg_type: Optional[Any] = None,
        qos_depth: int = 10,
    ) -> TopicInfo:
        """
        注册订阅者
        
        Args:
            topic_name: 话题名称
            callback: 回调函数
            msg_type: 消息类型
            qos_depth: QoS深度
            
        Returns:
            TopicInfo
        """
        # 注册回调
        if topic_name not in self._callbacks:
            self._callbacks[topic_name] = []
        self._callbacks[topic_name].append(callback)
        
        # 获取消息类型
        type_str = self.TOPIC_TYPES.get(topic_name, "std_msgs/String")
        
        # 创建订阅者
        if self.ros2_node:
            self.ros2_node.create_subscriber(
                topic_name, msg_type, self._on_message, qos_depth
            )
            
        # 记录话题信息
        info = TopicInfo(
            name=topic_name,
            msg_type=type_str,
            direction="subscribe",
            qos_depth=qos_depth,
        )
        self._topics[topic_name] = info
        
        self.logger.info(f"注册订阅者: {topic_name}")
        return info
        
    def _on_message(self, topic_name: str, message: Any) -> None:
        """消息回调"""
        # 更新统计
        if topic_name in self._topics:
            self._topics[topic_name].message_count += 1
            self._topics[topic_name].last_message_time = datetime.now()
            
        # 调用注册的回调
        callbacks = self._callbacks.get(topic_name, [])
        for callback in callbacks:
            try:
                callback(message)
            except Exception as e:
                self.logger.error(f"话题回调错误 [{topic_name}]: {e}")
                
    async def publish(self, topic_name: str, message: Any) -> bool:
        """
        发布消息
        
        Args:
            topic_name: 话题名称
            message: 消息
            
        Returns:
            是否成功
        """
        if topic_name not in self._topics:
            self.logger.warning(f"话题未注册: {topic_name}")
            return False
            
        if self.ros2_node:
            await self.ros2_node.publish(topic_name, message)
            
        # 更新统计
        self._topics[topic_name].message_count += 1
        self._topics[topic_name].last_message_time = datetime.now()
        
        return True
        
    def get_topic_info(self, topic_name: str) -> Optional[TopicInfo]:
        """获取话题信息"""
        return self._topics.get(topic_name)
        
    def list_topics(self) -> List[TopicInfo]:
        """列出所有话题"""
        return list(self._topics.values())
