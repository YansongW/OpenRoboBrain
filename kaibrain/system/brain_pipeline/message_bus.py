"""
消息总线

Agent间异步消息传递的核心组件。
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, TYPE_CHECKING

from kaibrain.system.brain_pipeline.protocol import Message, MessageType
from kaibrain.system.services.logger import LoggerMixin

if TYPE_CHECKING:
    from kaibrain.system.services.config_center import ConfigCenter


# 消息处理器类型
MessageHandler = Callable[[Message], Any]

# 默认配置
DEFAULT_QUEUE_MAXSIZE = 1000  # 默认队列最大大小
DEFAULT_PENDING_CLEANUP_INTERVAL = 30.0  # 默认清理间隔（秒）
DEFAULT_PENDING_TTL = 300.0  # 默认 pending response 存活时间（秒）


@dataclass
class PendingRequest:
    """待处理请求的包装器，包含创建时间用于清理"""
    future: asyncio.Future
    created_at: float = field(default_factory=time.time)
    
    def is_expired(self, ttl: float) -> bool:
        """检查是否已过期"""
        return time.time() - self.created_at > ttl


class MessageBus(LoggerMixin):
    """
    消息总线
    
    提供Agent间的异步消息传递能力。
    支持：
    - 点对点消息
    - 发布-订阅
    - 请求-响应
    
    安全特性：
    - 队列大小限制，防止内存溢出
    - pending_responses 定时清理，防止内存泄漏
    - 原子操作防止竞态条件
    """
    
    def __init__(
        self,
        config: Optional[ConfigCenter] = None,
        queue_maxsize: int = DEFAULT_QUEUE_MAXSIZE,
        pending_cleanup_interval: float = DEFAULT_PENDING_CLEANUP_INTERVAL,
        pending_ttl: float = DEFAULT_PENDING_TTL,
    ):
        """
        初始化消息总线
        
        Args:
            config: 配置中心
            queue_maxsize: 队列最大大小，防止内存溢出
            pending_cleanup_interval: pending_responses 清理间隔（秒）
            pending_ttl: pending_responses 存活时间（秒）
        """
        self.config = config
        
        # 配置参数
        self._queue_maxsize = queue_maxsize
        self._pending_cleanup_interval = pending_cleanup_interval
        self._pending_ttl = pending_ttl
        
        # 消息队列
        self._queues: Dict[str, asyncio.Queue] = {}
        
        # 订阅关系：topic -> set of subscriber_ids
        self._subscriptions: Dict[str, Set[str]] = defaultdict(set)
        
        # 消息处理器：agent_id -> handler
        self._handlers: Dict[str, MessageHandler] = {}
        
        # 等待响应的请求：correlation_id -> PendingRequest
        self._pending_responses: Dict[str, PendingRequest] = {}
        self._pending_lock = asyncio.Lock()  # 保护 pending_responses 的锁
        
        # 运行状态
        self._running = False
        self._dispatch_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        
    async def initialize(self) -> None:
        """初始化消息总线"""
        self.logger.info("初始化消息总线...")
        self._running = True
        
        # 启动 pending_responses 清理任务
        self._cleanup_task = asyncio.create_task(self._cleanup_pending_loop())
        self.logger.info(
            f"消息总线配置: queue_maxsize={self._queue_maxsize}, "
            f"pending_ttl={self._pending_ttl}s, cleanup_interval={self._pending_cleanup_interval}s"
        )
        
    async def shutdown(self) -> None:
        """关闭消息总线"""
        self.logger.info("关闭消息总线...")
        self._running = False
        
        # 停止清理任务
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
        
        # 取消所有等待的响应
        async with self._pending_lock:
            for pending in self._pending_responses.values():
                if not pending.future.done():
                    pending.future.cancel()
            self._pending_responses.clear()
    
    async def _cleanup_pending_loop(self) -> None:
        """定时清理过期的 pending_responses，防止内存泄漏"""
        while self._running:
            try:
                await asyncio.sleep(self._pending_cleanup_interval)
                await self._cleanup_expired_pending()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"清理 pending_responses 时出错: {e}")
    
    async def _cleanup_expired_pending(self) -> None:
        """清理已过期的 pending_responses"""
        expired_ids = []
        
        async with self._pending_lock:
            for msg_id, pending in self._pending_responses.items():
                if pending.is_expired(self._pending_ttl) or pending.future.done():
                    expired_ids.append(msg_id)
            
            for msg_id in expired_ids:
                pending = self._pending_responses.pop(msg_id, None)
                if pending and not pending.future.done():
                    pending.future.cancel()
        
        if expired_ids:
            self.logger.debug(f"清理了 {len(expired_ids)} 个过期的 pending_responses")
        
    def register(self, agent_id: str, handler: Optional[MessageHandler] = None) -> asyncio.Queue:
        """
        注册Agent
        
        Args:
            agent_id: Agent ID
            handler: 消息处理器
            
        Returns:
            该Agent的消息队列（有大小限制）
        """
        if agent_id in self._queues:
            self.logger.warning(f"Agent已注册: {agent_id}")
            return self._queues[agent_id]
        
        # 创建有界队列，防止内存溢出
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._queue_maxsize)
        self._queues[agent_id] = queue
        
        if handler:
            self._handlers[agent_id] = handler
            
        self.logger.info(f"Agent注册到消息总线: {agent_id} (queue_maxsize={self._queue_maxsize})")
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
            try:
                # 使用 put_nowait 检测队列是否满
                # 如果满了，使用超时等待，避免无限阻塞
                if queue.full():
                    self.logger.warning(
                        f"目标队列已满，等待空间: {message.target} "
                        f"(size={queue.qsize()}/{self._queue_maxsize})"
                    )
                await asyncio.wait_for(queue.put(message), timeout=5.0)
                self.logger.debug(
                    f"消息发送: {message.source} -> {message.target} [{message.type.value}]"
                )
            except asyncio.TimeoutError:
                self.logger.error(
                    f"发送消息超时，目标队列持续满: {message.target}, 消息丢弃"
                )
        else:
            self.logger.warning(f"目标Agent不存在: {message.target}")
            
    async def _publish_to_topic(self, message: Message) -> None:
        """发布到话题"""
        subscribers = self._subscriptions.get(message.topic, set())
        
        for subscriber_id in subscribers:
            queue = self._queues.get(subscriber_id)
            if queue:
                try:
                    if queue.full():
                        self.logger.warning(
                            f"订阅者队列已满: {subscriber_id} "
                            f"(size={queue.qsize()}/{self._queue_maxsize})"
                        )
                    await asyncio.wait_for(queue.put(message), timeout=5.0)
                except asyncio.TimeoutError:
                    self.logger.error(
                        f"发布消息超时，订阅者队列持续满: {subscriber_id}, 消息丢弃"
                    )
                
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
        # 创建 Future 等待响应，使用 PendingRequest 包装以支持清理
        future: asyncio.Future = asyncio.Future()
        pending = PendingRequest(future=future)
        
        # 使用锁保护 pending_responses 的访问，防止竞态条件
        async with self._pending_lock:
            self._pending_responses[message.message_id] = pending
        
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
            # 清理 pending_responses
            async with self._pending_lock:
                self._pending_responses.pop(message.message_id, None)
            
    async def respond(self, response: Message) -> None:
        """
        发送响应
        
        Args:
            response: 响应消息（需要设置 correlation_id）
        """
        if not response.correlation_id:
            # 没有 correlation_id，正常发送
            await self.send(response)
            return
        
        # 使用锁保护，原子操作防止竞态条件
        async with self._pending_lock:
            pending = self._pending_responses.get(response.correlation_id)
            
            if pending:
                if not pending.future.done():
                    # 设置响应结果
                    pending.future.set_result(response)
                    return
                else:
                    # Future 已完成（可能是超时），清理该条目
                    self._pending_responses.pop(response.correlation_id, None)
                
        # 没有找到等待的请求，或请求已完成，正常发送
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
    
    def get_pending_count(self) -> int:
        """获取当前等待响应的请求数量"""
        return len(self._pending_responses)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取消息总线统计信息
        
        Returns:
            包含各项统计的字典
        """
        queue_stats = {}
        for agent_id, queue in self._queues.items():
            queue_stats[agent_id] = {
                "size": queue.qsize(),
                "maxsize": self._queue_maxsize,
                "full": queue.full(),
            }
        
        return {
            "running": self._running,
            "registered_agents": len(self._queues),
            "pending_responses": len(self._pending_responses),
            "subscriptions": {
                topic: len(subscribers) 
                for topic, subscribers in self._subscriptions.items()
            },
            "queue_stats": queue_stats,
            "config": {
                "queue_maxsize": self._queue_maxsize,
                "pending_ttl": self._pending_ttl,
                "pending_cleanup_interval": self._pending_cleanup_interval,
            },
        }
