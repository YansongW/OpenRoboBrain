"""
管道桥接器

连接大脑管道和小脑管道（ROS2 DDS），实现消息转换和路由。
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, Optional, TYPE_CHECKING

from kaibrain.system.brain_pipeline.protocol import Message, MessageType
from kaibrain.system.services.logger import LoggerMixin

if TYPE_CHECKING:
    from kaibrain.system.brain_pipeline.message_bus import MessageBus


class PipelineBridge(LoggerMixin):
    """
    管道桥接器
    
    负责大脑管道和小脑管道之间的消息转换和路由。
    """
    
    def __init__(self, message_bus: MessageBus):
        """
        初始化桥接器
        
        Args:
            message_bus: 大脑管道消息总线
        """
        self.message_bus = message_bus
        self._cerebellum_client: Optional[Any] = None  # ROS2客户端
        self._running = False
        self._bridge_task: Optional[asyncio.Task] = None
        
        # 消息转换器
        self._brain_to_cerebellum: Dict[MessageType, Callable] = {}
        self._cerebellum_to_brain: Dict[str, Callable] = {}
        
    async def initialize(self, cerebellum_client: Optional[Any] = None) -> None:
        """
        初始化桥接器
        
        Args:
            cerebellum_client: 小脑管道客户端（ROS2节点）
        """
        self.logger.info("初始化管道桥接器...")
        
        self._cerebellum_client = cerebellum_client
        
        # 注册到消息总线
        self.message_bus.register("bridge", handler=self._handle_brain_message)
        self.message_bus.subscribe("bridge", "cerebellum.command")
        
        self._running = True
        
        self.logger.info("管道桥接器初始化完成")
        
    async def shutdown(self) -> None:
        """关闭桥接器"""
        self.logger.info("关闭管道桥接器...")
        self._running = False
        
        if self._bridge_task and not self._bridge_task.done():
            self._bridge_task.cancel()
            
        self.message_bus.unregister("bridge")
        
    async def _handle_brain_message(self, message: Message) -> None:
        """
        处理来自大脑管道的消息
        
        Args:
            message: 大脑管道消息
        """
        if message.type == MessageType.CEREBELLUM_COMMAND:
            await self._forward_to_cerebellum(message)
            
    async def _forward_to_cerebellum(self, message: Message) -> None:
        """
        转发消息到小脑管道
        
        Args:
            message: 大脑管道消息
        """
        if not self._cerebellum_client:
            self.logger.warning("小脑管道客户端未初始化，消息丢弃")
            return
            
        # 转换消息格式
        ros2_message = self._convert_to_ros2(message)
        
        # TODO: 通过ROS2客户端发送
        # await self._cerebellum_client.publish(ros2_message)
        
        self.logger.debug(f"消息转发到小脑: {message.message_id}")
        
    def _convert_to_ros2(self, message: Message) -> Dict[str, Any]:
        """
        将大脑消息转换为ROS2消息格式
        
        Args:
            message: 大脑管道消息
            
        Returns:
            ROS2消息（字典格式）
        """
        # 基本转换
        ros2_msg = {
            "header": {
                "message_id": message.message_id,
                "timestamp": message.timestamp.isoformat(),
            },
            "command_type": message.payload.get("command_type", ""),
            "parameters": message.payload.get("parameters", {}),
        }
        
        # 检查是否有自定义转换器
        converter = self._brain_to_cerebellum.get(message.type)
        if converter:
            ros2_msg = converter(message)
            
        return ros2_msg
        
    async def receive_from_cerebellum(self, ros2_message: Dict[str, Any]) -> None:
        """
        接收来自小脑管道的消息
        
        Args:
            ros2_message: ROS2消息
        """
        # 转换为大脑消息
        message = self._convert_from_ros2(ros2_message)
        
        # 发送到大脑管道
        await self.message_bus.send(message)
        
        self.logger.debug(f"从小脑接收消息: {message.message_id}")
        
    def _convert_from_ros2(self, ros2_message: Dict[str, Any]) -> Message:
        """
        将ROS2消息转换为大脑消息格式
        
        Args:
            ros2_message: ROS2消息
            
        Returns:
            大脑管道消息
        """
        # 基本转换
        message = Message(
            type=MessageType.CEREBELLUM_FEEDBACK,
            source="cerebellum",
            payload=ros2_message,
        )
        
        # 检查是否有自定义转换器
        topic = ros2_message.get("topic", "")
        converter = self._cerebellum_to_brain.get(topic)
        if converter:
            message = converter(ros2_message)
            
        return message
        
    def register_brain_converter(
        self,
        message_type: MessageType,
        converter: Callable[[Message], Dict[str, Any]],
    ) -> None:
        """注册大脑到小脑的消息转换器"""
        self._brain_to_cerebellum[message_type] = converter
        
    def register_cerebellum_converter(
        self,
        topic: str,
        converter: Callable[[Dict[str, Any]], Message],
    ) -> None:
        """注册小脑到大脑的消息转换器"""
        self._cerebellum_to_brain[topic] = converter
