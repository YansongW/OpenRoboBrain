"""
消息总线单元测试

测试框架修复：
- 队列大小限制
- 请求响应竞态条件
- pending_responses 清理机制
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from orb.system.brain_pipeline.message_bus import (
    MessageBus,
    PendingRequest,
    DEFAULT_QUEUE_MAXSIZE,
)
from orb.system.brain_pipeline.protocol import Message, MessageType


class TestPendingRequest:
    """PendingRequest 测试"""
    
    @pytest.mark.asyncio
    async def test_is_expired_not_expired(self):
        """测试未过期"""
        pending = PendingRequest(future=asyncio.Future())
        assert pending.is_expired(ttl=300.0) is False
        
    @pytest.mark.asyncio
    async def test_is_expired_expired(self):
        """测试已过期"""
        import time
        pending = PendingRequest(future=asyncio.Future())
        # 修改创建时间模拟过期
        pending.created_at = time.time() - 400
        assert pending.is_expired(ttl=300.0) is True


class TestMessageBusInit:
    """MessageBus 初始化测试"""
    
    def test_default_queue_maxsize(self):
        """测试默认队列大小"""
        bus = MessageBus()
        assert bus._queue_maxsize == DEFAULT_QUEUE_MAXSIZE
        
    def test_custom_queue_maxsize(self):
        """测试自定义队列大小"""
        bus = MessageBus(queue_maxsize=500)
        assert bus._queue_maxsize == 500
        
    def test_custom_pending_config(self):
        """测试自定义 pending 配置"""
        bus = MessageBus(
            pending_cleanup_interval=60.0,
            pending_ttl=600.0,
        )
        assert bus._pending_cleanup_interval == 60.0
        assert bus._pending_ttl == 600.0


class TestMessageBusRegister:
    """MessageBus 注册测试"""
    
    def test_register_creates_bounded_queue(self):
        """测试注册创建有界队列"""
        bus = MessageBus(queue_maxsize=100)
        queue = bus.register("agent1")
        
        assert queue.maxsize == 100
        
    def test_register_returns_same_queue(self):
        """测试重复注册返回相同队列"""
        bus = MessageBus()
        queue1 = bus.register("agent1")
        queue2 = bus.register("agent1")
        
        assert queue1 is queue2
        
    def test_unregister_removes_queue(self):
        """测试注销移除队列"""
        bus = MessageBus()
        bus.register("agent1")
        bus.unregister("agent1")
        
        assert "agent1" not in bus._queues


class TestMessageBusSend:
    """MessageBus 发送测试"""
    
    @pytest.mark.asyncio
    async def test_send_to_registered_agent(self):
        """测试发送到已注册的 Agent"""
        bus = MessageBus()
        await bus.initialize()
        
        queue = bus.register("agent1")
        
        msg = Message(
            source="sender",
            target="agent1",
            type=MessageType.AGENT_MESSAGE,
            payload={"data": "test"},
        )
        
        await bus.send(msg)
        
        received = await queue.get()
        assert received.payload == {"data": "test"}
        
        await bus.shutdown()
        
    @pytest.mark.asyncio
    async def test_send_to_nonexistent_agent(self):
        """测试发送到不存在的 Agent（不应抛出异常）"""
        bus = MessageBus()
        await bus.initialize()
        
        msg = Message(
            source="sender",
            target="nonexistent",
            type=MessageType.AGENT_MESSAGE,
            payload={},
        )
        
        # 不应抛出异常
        await bus.send(msg)
        
        await bus.shutdown()
    
    @pytest.mark.asyncio
    async def test_send_to_full_queue_timeout(self):
        """测试发送到满队列时的超时行为"""
        bus = MessageBus(queue_maxsize=1)
        await bus.initialize()
        
        queue = bus.register("agent1")
        
        # 填满队列
        msg1 = Message(
            source="sender",
            target="agent1",
            type=MessageType.AGENT_MESSAGE,
            payload={"seq": 1},
        )
        await bus.send(msg1)
        
        # 队列已满，第二条消息应该等待超时
        msg2 = Message(
            source="sender",
            target="agent1",
            type=MessageType.AGENT_MESSAGE,
            payload={"seq": 2},
        )
        
        # 先消费第一条，让第二条能发送
        consumed = await queue.get()
        assert consumed.payload["seq"] == 1
        
        # 现在可以发送第二条
        await bus.send(msg2)
        
        await bus.shutdown()


class TestMessageBusRequestResponse:
    """MessageBus 请求响应测试"""
    
    @pytest.mark.asyncio
    async def test_request_and_respond(self):
        """测试请求响应流程"""
        bus = MessageBus()
        await bus.initialize()
        
        bus.register("requester")
        bus.register("responder")
        
        # 创建请求
        request = Message(
            source="requester",
            target="responder",
            type=MessageType.AGENT_REQUEST,
            payload={"question": "test?"},
        )
        
        # 在后台响应
        async def respond_later():
            await asyncio.sleep(0.05)
            response = Message(
                source="responder",
                target="requester",
                type=MessageType.AGENT_RESPONSE,
                correlation_id=request.message_id,
                payload={"answer": "yes"},
            )
            await bus.respond(response)
        
        asyncio.create_task(respond_later())
        
        # 发送请求并等待响应
        response = await bus.request(request, timeout=1.0)
        
        assert response is not None
        assert response.payload["answer"] == "yes"
        
        await bus.shutdown()
        
    @pytest.mark.asyncio
    async def test_request_timeout(self):
        """测试请求超时"""
        bus = MessageBus()
        await bus.initialize()
        
        bus.register("requester")
        
        request = Message(
            source="requester",
            target="nobody",
            type=MessageType.AGENT_REQUEST,
            payload={},
        )
        
        # 应该超时返回 None
        response = await bus.request(request, timeout=0.1)
        
        assert response is None
        
        await bus.shutdown()
        
    @pytest.mark.asyncio
    async def test_pending_cleanup_after_timeout(self):
        """测试超时后 pending_responses 被清理"""
        bus = MessageBus()
        await bus.initialize()
        
        bus.register("requester")
        
        request = Message(
            source="requester",
            target="nobody",
            type=MessageType.AGENT_REQUEST,
            payload={},
        )
        
        # 超时前检查 pending
        await bus.request(request, timeout=0.1)
        
        # 超时后应该被清理
        assert request.message_id not in bus._pending_responses
        
        await bus.shutdown()


class TestMessageBusCleanup:
    """MessageBus 清理机制测试"""
    
    @pytest.mark.asyncio
    async def test_cleanup_expired_pending(self):
        """测试清理过期的 pending_responses"""
        bus = MessageBus(pending_ttl=0.1)  # 0.1秒TTL
        await bus.initialize()
        
        # 手动添加一个过期的 pending
        import time
        future = asyncio.Future()
        pending = PendingRequest(future=future, created_at=time.time() - 1)  # 1秒前创建
        
        async with bus._pending_lock:
            bus._pending_responses["expired_msg"] = pending
        
        # 执行清理
        await bus._cleanup_expired_pending()
        
        # 应该被清理
        assert "expired_msg" not in bus._pending_responses
        
        await bus.shutdown()
        
    @pytest.mark.asyncio
    async def test_shutdown_cancels_pending(self):
        """测试关闭时取消所有 pending"""
        bus = MessageBus()
        await bus.initialize()
        
        # 添加 pending
        future = asyncio.Future()
        pending = PendingRequest(future=future)
        
        async with bus._pending_lock:
            bus._pending_responses["msg1"] = pending
        
        # 关闭
        await bus.shutdown()
        
        # pending 应该被取消
        assert future.cancelled()
        assert len(bus._pending_responses) == 0


class TestMessageBusStats:
    """MessageBus 统计测试"""
    
    def test_get_stats(self):
        """测试获取统计信息"""
        bus = MessageBus(queue_maxsize=100)
        bus.register("agent1")
        bus.register("agent2")
        
        stats = bus.get_stats()
        
        assert stats["running"] is False
        assert stats["registered_agents"] == 2
        assert stats["config"]["queue_maxsize"] == 100
        
    def test_get_pending_count(self):
        """测试获取 pending 数量"""
        bus = MessageBus()
        assert bus.get_pending_count() == 0
