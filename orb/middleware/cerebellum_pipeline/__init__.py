"""
小脑管道 (Cerebellum Pipeline)

基于 ROS2 DDS 的实时通信管道，由小脑主导。

组件：
- ros2_node: ROS2节点封装
- topics: 话题管理
- services: 服务管理
- actions: Action管理
"""

from orb.middleware.cerebellum_pipeline.ros2_node import ROS2Node
from orb.middleware.cerebellum_pipeline.topics import TopicManager
from orb.middleware.cerebellum_pipeline.services import ServiceManager

__all__ = ["ROS2Node", "TopicManager", "ServiceManager"]
