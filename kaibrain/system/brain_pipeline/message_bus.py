"""
消息总线

Agent间异步消息传递的核心组件。
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Set, TYPE_CHECKING

from kaibrain.system.brain_pipeline.protocol import Message, MessageType
from kaibrain.system.services.logger import LoggerMixin

if TYPE_CHECKING:
    from kaibrain.system.services.config_center import ConfigCenter


# 消息处理器类型
MessageHandler = Callable[[Message], Any]


class MessageBus(LoggerMixin):
    """
    消息总线
    
    提供Agent间的异步消息传递能力。
    支持：
    - 点对点消息
    - 发布-订阅
    - 请求-响应
    """
    
    def __init__(self, config: Optional[ConfigCenter] = None):
        """
        初始化消息总线
        
        Args:
            config: 配置中心
        """
        self.config = config
        
        # 消息队列
        self._queues: Dict[str, asyncio.Queue] = {}
        
        # 订阅关系：topic -> set of subscriber_ids
        self._subscriptions: Dict[str, Set[str]] = defaultdict(set)
        
        # 消息处理器：agent_id -> handler
        self._handlers: Dict[str, MessageHandler] = {}
        
        # 等待响应的请求：correlation_id -> Future
        self._pending_responses: Dict[str, asyncio.Future] = {}
        
        # 运行状态
        self._running = False
        self._dispatch_task: Optional[asyncio.Task] = None
        
    async def initialize(self) -> None:
        """初始化消息总线"""
        self.logger.info("初始化消息总线...")
        self._running = True
        
    async def shutdown(self) -> None:
        """关闭消息总线"""
        self.logger.info("关闭消息总线...")
        self._running = False
        
        # 取消所有等待的响应
        for future in self._pending_responses.values():
            if not future.done():
                future.cancel()
        self._pending_responses.clear()
        
    def register(self, agent_id: str, handler: Optional[MessageHandler] = None) -> asyncio.Queue:
        """
        注册Agent
        
        Args:
            agent_id: Agent ID
            handler: 消息处理器
            
        Returns:
            该Agent的消息队列
        """
        if agent_id in self._queues:
            self.logger.warning(f"Agent已注册: {agent_id}")
            return self._queues[agent_id]
            
        queue: asyncio.Queue = asyncio.Queue()
        self._queues[agent_id] = queue
        
        if handler:
            self._handlers[agent_id] = handler
            
        self.logger.info(f"Agent注册到消息总线: {agent_id}")
        return queue
        
    def unregister(self, agent_id: str) -> None:
        """注销Agent"""
        if agent_id in self._queues:
            del self._queues[agent_id]
            
        if agent_id in self._handlers:
            del self._handlers[agent_id]
            
        # 移除所有订阅
        for subscribers in self._subscriptions.values():
            subscribers.discard(agent_id)
            
        self.logger.info(f"Agent从消息总线注销: {agent_id}")
        
    def subscribe(self, agent_id: str, topic: str) -> None:
        """
        订阅话题
        
        Args:
            agent_id: Agent ID
            topic: 话题
        """
        self._subscriptions[topic].add(agent_id)
        self.logger.debug(f"Agent {agent_id} 订阅话题: {topic}")
        
    def unsubscribe(self, agent_id: str, topic: str) -> None:
        """取消订阅"""
        self._subscriptions[topic].discard(agent_id)
        
    async def send(self, message: Message) -> None:
        """
        发送消息
        
        Args:
            message: 消息
        """
        if message.is_expired():
            self.logger.warning(f"消息已过期，丢弃: {message.message_id}")
            return
            
        # 点对点消息
        if message.target:
            await self._send_to_target(message)
            
        # 发布到话题
        elif message.topic:
            await self._publish_to_topic(message)
            
        else:
            self.logger.warning(f"消息没有目标或话题: {message.message_id}")
            
    async def _send_to_target(self, message: Message) -> None:
        """发送到指定目标"""
        queue = self._queues.get(message.target)
        if queue:
            await queue.put(message)
            self.logger.debug(
                f"消息发送: {message.source} -> {message.target} [{message.type.value}]"
            )
        else:
            self.logger.warning(f"目标Agent不存在: {message.target}")
            
    async def _publish_to_topic(self, message: Message) -> None:
        """发布到话题"""
        subscribers = self._subscriptions.get(message.topic, set())
        
        for subscriber_id in subscribers:
            queue = self._queues.get(subscriber_id)
            if queue:
                await queue.put(message)
                
        self.logger.debug(
            f"消息发布: {message.source} -> [{message.topic}] ({len(subscribers)} 订阅者)"
        )
        
    async def request(
        self,
        message: Message,
        timeout: float = 30.0,
    ) -> Optional[Message]:
        """
        发送请求并等待响应
        
        Args:
            message: 请求消息
            timeout: 超时时间（秒）
            
        Returns:
            响应消息，超时返回 None
        """
        # 创建Future等待响应
        future: asyncio.Future = asyncio.Future()
        self._pending_responses[message.message_id] = future
        
        try:
            # 发送请求
            await self.send(message)
            
            # 等待响应
            response = await asyncio.wait_for(future, timeout=timeout)
            return response
            
        except asyncio.TimeoutError:
            self.logger.warning(f"请求超时: {message.message_id}")
            return None
            
        finally:
            self._pending_responses.pop(message.message_id, None)
            
    async def respond(self, response: Message) -> None:
        """
        发送响应
        
        Args:
            response: 响应消息（需要设置 correlation_id）
        """
        # 检查是否有等待的请求
        if response.correlation_id and response.correlation_id in self._pending_responses:
            future = self._pending_responses[response.correlation_id]
            if not future.done():
                future.set_result(response)
                return
                
        # 否则正常发送
        await self.send(response)
        
    async def receive(self, agent_id: str, timeout: Optional[float] = None) -> Optional[Message]:
        """
        接收消息
        
        Args:
            agent_id: Agent ID
            timeout: 超时时间，None表示永久等待
            
        Returns:
            消息，超时返回 None
        """
        queue = self._queues.get(agent_id)
        if not queue:
            self.logger.warning(f"Agent未注册: {agent_id}")
            return None
            
        try:
            if timeout is not None:
                message = await asyncio.wait_for(queue.get(), timeout=timeout)
            else:
                message = await queue.get()
            return message
            
        except asyncio.TimeoutError:
            return None
            
    def get_queue_size(self, agent_id: str) -> int:
        """获取Agent消息队列大小"""
        queue = self._queues.get(agent_id)
        return queue.qsize() if queue else 0
        
    def get_registered_agents(self) -> List[str]:
        """获取已注册的Agent列表"""
        return list(self._queues.keys())
