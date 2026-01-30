"""
Brain Pipeline WebSocket Server

大脑管道的 WebSocket JSON 通信层。

设计原则：
- 大脑管道专注于高层次、非实时的多Agent协作
- 使用 WebSocket JSON 作为通信协议
- 与小脑管道（ROS2 DDS）完全解耦
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import uuid4

from kaibrain.system.services.logger import LoggerMixin, get_logger

logger = get_logger(__name__)


class WSMessageType(Enum):
    """WebSocket 消息类型"""
    # 连接管理
    CONNECT = "connect"
    DISCONNECT = "disconnect"
    HEARTBEAT = "heartbeat"
    
    # Agent 通信
    AGENT_MESSAGE = "agent.message"
    AGENT_REQUEST = "agent.request"
    AGENT_RESPONSE = "agent.response"
    AGENT_BROADCAST = "agent.broadcast"
    
    # 事件
    EVENT_LIFECYCLE = "event.lifecycle"
    EVENT_TOOL = "event.tool"
    EVENT_STREAM = "event.stream"
    
    # 同步（与小脑桥接）
    SYNC_STATE = "sync.state"
    SYNC_COMMAND = "sync.command"
    SYNC_FEEDBACK = "sync.feedback"
    
    # 错误
    ERROR = "error"


@dataclass
class WSMessage:
    """WebSocket 消息"""
    id: str = field(default_factory=lambda: str(uuid4()))
    type: WSMessageType = WSMessageType.AGENT_MESSAGE
    source: str = ""           # 发送者 ID
    target: Optional[str] = None  # 目标 ID (None 表示广播)
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    correlation_id: Optional[str] = None  # 用于请求-响应关联
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_json(self) -> str:
        """转换为 JSON 字符串"""
        return json.dumps({
            "id": self.id,
            "type": self.type.value,
            "source": self.source,
            "target": self.target,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "correlationId": self.correlation_id,
            "metadata": self.metadata,
        }, ensure_ascii=False)
        
    @classmethod
    def from_json(cls, data: str) -> "WSMessage":
        """从 JSON 字符串解析"""
        obj = json.loads(data)
        return cls(
            id=obj.get("id", str(uuid4())),
            type=WSMessageType(obj.get("type", "agent.message")),
            source=obj.get("source", ""),
            target=obj.get("target"),
            payload=obj.get("payload", {}),
            timestamp=obj.get("timestamp", datetime.now().isoformat()),
            correlation_id=obj.get("correlationId"),
            metadata=obj.get("metadata", {}),
        )


@dataclass
class WSClient:
    """WebSocket 客户端信息"""
    client_id: str
    agent_id: str
    websocket: Any  # WebSocket 连接对象
    connected_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_heartbeat: str = field(default_factory=lambda: datetime.now().isoformat())
    subscriptions: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)


# 回调类型
MessageCallback = Callable[[WSMessage, "WSClient"], Any]


class BrainWebSocketServer(LoggerMixin):
    """
    大脑管道 WebSocket 服务器
    
    提供多 Agent 协作的 WebSocket JSON 通信层。
    """
    
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8765,
        heartbeat_interval: float = 30.0,
    ):
        """
        初始化 WebSocket 服务器
        
        Args:
            host: 监听地址
            port: 监听端口
            heartbeat_interval: 心跳间隔（秒）
        """
        self._host = host
        self._port = port
        self._heartbeat_interval = heartbeat_interval
        
        self._running = False
        self._server = None
        
        # 客户端管理
        self._clients: Dict[str, WSClient] = {}  # client_id -> WSClient
        self._agent_clients: Dict[str, str] = {}  # agent_id -> client_id
        
        # 消息处理器
        self._handlers: Dict[WSMessageType, List[MessageCallback]] = {}
        
        # 等待响应的请求
        self._pending_requests: Dict[str, asyncio.Future] = {}
        
        # 主题订阅
        self._topic_subscribers: Dict[str, Set[str]] = {}  # topic -> set of client_ids
        
    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        return self._running
        
    @property
    def client_count(self) -> int:
        """连接的客户端数量"""
        return len(self._clients)
        
    def register_handler(
        self,
        message_type: WSMessageType,
        handler: MessageCallback,
    ) -> None:
        """
        注册消息处理器
        
        Args:
            message_type: 消息类型
            handler: 处理函数
        """
        if message_type not in self._handlers:
            self._handlers[message_type] = []
        self._handlers[message_type].append(handler)
        
    async def start(self) -> None:
        """启动 WebSocket 服务器"""
        try:
            import websockets
            
            self._running = True
            self._server = await websockets.serve(
                self._handle_connection,
                self._host,
                self._port,
            )
            
            self.logger.info(f"Brain WebSocket 服务器启动: ws://{self._host}:{self._port}")
            
            # 启动心跳检测
            asyncio.create_task(self._heartbeat_loop())
            
        except ImportError:
            self.logger.error("websockets 库未安装，无法启动 WebSocket 服务器")
            self._running = False
            
    async def stop(self) -> None:
        """停止服务器"""
        self._running = False
        
        # 关闭所有连接
        for client in list(self._clients.values()):
            try:
                await client.websocket.close()
            except Exception:
                pass
                
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            
        self._clients.clear()
        self._agent_clients.clear()
        
        self.logger.info("Brain WebSocket 服务器已停止")
        
    async def _handle_connection(self, websocket, path: str) -> None:
        """处理 WebSocket 连接"""
        client_id = str(uuid4())
        client: Optional[WSClient] = None
        
        try:
            # 等待连接消息
            connect_msg = await asyncio.wait_for(websocket.recv(), timeout=10.0)
            msg = WSMessage.from_json(connect_msg)
            
            if msg.type != WSMessageType.CONNECT:
                await websocket.close(1008, "Expected CONNECT message")
                return
                
            agent_id = msg.payload.get("agentId", msg.source)
            
            # 创建客户端
            client = WSClient(
                client_id=client_id,
                agent_id=agent_id,
                websocket=websocket,
                metadata=msg.metadata,
            )
            
            self._clients[client_id] = client
            self._agent_clients[agent_id] = client_id
            
            self.logger.info(f"Agent 连接: {agent_id} (client: {client_id})")
            
            # 发送连接确认
            await self._send_to_client(client, WSMessage(
                type=WSMessageType.CONNECT,
                source="server",
                target=agent_id,
                payload={"status": "connected", "clientId": client_id},
            ))
            
            # 消息循环
            async for raw_message in websocket:
                try:
                    message = WSMessage.from_json(raw_message)
                    message.source = agent_id
                    await self._process_message(message, client)
                except json.JSONDecodeError as e:
                    self.logger.warning(f"无效的 JSON 消息: {e}")
                except Exception as e:
                    self.logger.error(f"处理消息错误: {e}")
                    
        except asyncio.TimeoutError:
            self.logger.warning(f"连接超时: {client_id}")
        except Exception as e:
            self.logger.error(f"连接错误: {e}")
        finally:
            # 清理
            if client:
                self._cleanup_client(client)
                
    def _cleanup_client(self, client: WSClient) -> None:
        """清理断开的客户端"""
        self._clients.pop(client.client_id, None)
        self._agent_clients.pop(client.agent_id, None)
        
        # 清理订阅
        for subscribers in self._topic_subscribers.values():
            subscribers.discard(client.client_id)
            
        self.logger.info(f"Agent 断开: {client.agent_id}")
        
    async def _process_message(self, message: WSMessage, client: WSClient) -> None:
        """处理消息"""
        # 更新心跳
        client.last_heartbeat = datetime.now().isoformat()
        
        # 处理特殊消息类型
        if message.type == WSMessageType.HEARTBEAT:
            await self._send_to_client(client, WSMessage(
                type=WSMessageType.HEARTBEAT,
                source="server",
                target=client.agent_id,
                payload={"timestamp": datetime.now().isoformat()},
            ))
            return
            
        # 处理响应
        if message.type == WSMessageType.AGENT_RESPONSE:
            if message.correlation_id and message.correlation_id in self._pending_requests:
                future = self._pending_requests.pop(message.correlation_id)
                if not future.done():
                    future.set_result(message)
                return
                
        # 转发消息
        if message.target:
            # 点对点
            await self.send_to_agent(message.target, message)
        elif message.type == WSMessageType.AGENT_BROADCAST:
            # 广播
            await self.broadcast(message, exclude=[client.client_id])
            
        # 调用处理器
        handlers = self._handlers.get(message.type, [])
        for handler in handlers:
            try:
                result = handler(message, client)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                self.logger.error(f"消息处理器错误: {e}")
                
    async def _send_to_client(self, client: WSClient, message: WSMessage) -> bool:
        """发送消息到客户端"""
        try:
            await client.websocket.send(message.to_json())
            return True
        except Exception as e:
            self.logger.error(f"发送消息失败: {e}")
            return False
            
    async def send_to_agent(self, agent_id: str, message: WSMessage) -> bool:
        """
        发送消息到指定 Agent
        
        Args:
            agent_id: Agent ID
            message: 消息
            
        Returns:
            是否成功
        """
        client_id = self._agent_clients.get(agent_id)
        if not client_id:
            self.logger.warning(f"Agent 不在线: {agent_id}")
            return False
            
        client = self._clients.get(client_id)
        if not client:
            return False
            
        return await self._send_to_client(client, message)
        
    async def broadcast(
        self,
        message: WSMessage,
        exclude: Optional[List[str]] = None,
    ) -> int:
        """
        广播消息
        
        Args:
            message: 消息
            exclude: 排除的客户端 ID 列表
            
        Returns:
            发送成功的数量
        """
        exclude = exclude or []
        count = 0
        
        for client in self._clients.values():
            if client.client_id not in exclude:
                if await self._send_to_client(client, message):
                    count += 1
                    
        return count
        
    async def request(
        self,
        target_agent: str,
        payload: Dict[str, Any],
        timeout: float = 30.0,
    ) -> Optional[WSMessage]:
        """
        发送请求并等待响应
        
        Args:
            target_agent: 目标 Agent ID
            payload: 请求内容
            timeout: 超时时间
            
        Returns:
            响应消息
        """
        message = WSMessage(
            type=WSMessageType.AGENT_REQUEST,
            source="server",
            target=target_agent,
            payload=payload,
        )
        
        future: asyncio.Future = asyncio.Future()
        self._pending_requests[message.id] = future
        
        try:
            if not await self.send_to_agent(target_agent, message):
                return None
                
            response = await asyncio.wait_for(future, timeout=timeout)
            return response
            
        except asyncio.TimeoutError:
            self.logger.warning(f"请求超时: {target_agent}")
            return None
        finally:
            self._pending_requests.pop(message.id, None)
            
    async def _heartbeat_loop(self) -> None:
        """心跳检测循环"""
        while self._running:
            await asyncio.sleep(self._heartbeat_interval)
            
            now = datetime.now()
            timeout_threshold = self._heartbeat_interval * 3
            
            for client in list(self._clients.values()):
                last_hb = datetime.fromisoformat(client.last_heartbeat)
                if (now - last_hb).total_seconds() > timeout_threshold:
                    self.logger.warning(f"客户端心跳超时: {client.agent_id}")
                    try:
                        await client.websocket.close()
                    except Exception:
                        pass
                    self._cleanup_client(client)
                    
    def get_online_agents(self) -> List[str]:
        """获取在线 Agent 列表"""
        return list(self._agent_clients.keys())
        
    def is_agent_online(self, agent_id: str) -> bool:
        """检查 Agent 是否在线"""
        return agent_id in self._agent_clients
        
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "running": self._running,
            "host": self._host,
            "port": self._port,
            "client_count": len(self._clients),
            "online_agents": self.get_online_agents(),
            "pending_requests": len(self._pending_requests),
        }


class BrainWebSocketClient(LoggerMixin):
    """
    大脑管道 WebSocket 客户端
    
    用于 Agent 连接到 Brain WebSocket 服务器。
    """
    
    def __init__(
        self,
        agent_id: str,
        server_url: str = "ws://localhost:8765",
        auto_reconnect: bool = True,
        reconnect_interval: float = 5.0,
    ):
        """
        初始化客户端
        
        Args:
            agent_id: Agent ID
            server_url: 服务器 URL
            auto_reconnect: 是否自动重连
            reconnect_interval: 重连间隔
        """
        self._agent_id = agent_id
        self._server_url = server_url
        self._auto_reconnect = auto_reconnect
        self._reconnect_interval = reconnect_interval
        
        self._websocket = None
        self._connected = False
        self._running = False
        
        self._handlers: Dict[WSMessageType, List[MessageCallback]] = {}
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._receive_task: Optional[asyncio.Task] = None
        
    @property
    def is_connected(self) -> bool:
        return self._connected
        
    @property
    def agent_id(self) -> str:
        return self._agent_id
        
    def on_message(
        self,
        message_type: WSMessageType,
        handler: MessageCallback,
    ) -> None:
        """注册消息处理器"""
        if message_type not in self._handlers:
            self._handlers[message_type] = []
        self._handlers[message_type].append(handler)
        
    async def connect(self) -> bool:
        """连接到服务器"""
        try:
            import websockets
            
            self._running = True
            self._websocket = await websockets.connect(self._server_url)
            
            # 发送连接消息
            connect_msg = WSMessage(
                type=WSMessageType.CONNECT,
                source=self._agent_id,
                payload={"agentId": self._agent_id},
            )
            await self._websocket.send(connect_msg.to_json())
            
            # 等待确认
            response = await asyncio.wait_for(self._websocket.recv(), timeout=10.0)
            msg = WSMessage.from_json(response)
            
            if msg.type == WSMessageType.CONNECT and msg.payload.get("status") == "connected":
                self._connected = True
                self._receive_task = asyncio.create_task(self._receive_loop())
                self.logger.info(f"已连接到 Brain 服务器: {self._server_url}")
                return True
            else:
                self.logger.error("连接确认失败")
                return False
                
        except ImportError:
            self.logger.error("websockets 库未安装")
            return False
        except Exception as e:
            self.logger.error(f"连接失败: {e}")
            return False
            
    async def disconnect(self) -> None:
        """断开连接"""
        self._running = False
        self._connected = False
        
        if self._receive_task:
            self._receive_task.cancel()
            
        if self._websocket:
            await self._websocket.close()
            
    async def _receive_loop(self) -> None:
        """接收消息循环"""
        while self._running and self._websocket:
            try:
                raw_message = await self._websocket.recv()
                message = WSMessage.from_json(raw_message)
                await self._process_message(message)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"接收消息错误: {e}")
                self._connected = False
                
                if self._auto_reconnect:
                    await asyncio.sleep(self._reconnect_interval)
                    await self.connect()
                else:
                    break
                    
    async def _process_message(self, message: WSMessage) -> None:
        """处理消息"""
        # 处理响应
        if message.type == WSMessageType.AGENT_RESPONSE:
            if message.correlation_id and message.correlation_id in self._pending_requests:
                future = self._pending_requests.pop(message.correlation_id)
                if not future.done():
                    future.set_result(message)
                return
                
        # 调用处理器
        handlers = self._handlers.get(message.type, [])
        for handler in handlers:
            try:
                result = handler(message, None)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                self.logger.error(f"消息处理器错误: {e}")
                
    async def send(self, message: WSMessage) -> bool:
        """发送消息"""
        if not self._connected or not self._websocket:
            return False
            
        try:
            message.source = self._agent_id
            await self._websocket.send(message.to_json())
            return True
        except Exception as e:
            self.logger.error(f"发送消息失败: {e}")
            return False
            
    async def send_to_agent(
        self,
        target_agent: str,
        payload: Dict[str, Any],
    ) -> bool:
        """发送消息到另一个 Agent"""
        return await self.send(WSMessage(
            type=WSMessageType.AGENT_MESSAGE,
            target=target_agent,
            payload=payload,
        ))
        
    async def request(
        self,
        target_agent: str,
        payload: Dict[str, Any],
        timeout: float = 30.0,
    ) -> Optional[WSMessage]:
        """发送请求并等待响应"""
        message = WSMessage(
            type=WSMessageType.AGENT_REQUEST,
            source=self._agent_id,
            target=target_agent,
            payload=payload,
        )
        
        future: asyncio.Future = asyncio.Future()
        self._pending_requests[message.id] = future
        
        try:
            if not await self.send(message):
                return None
                
            response = await asyncio.wait_for(future, timeout=timeout)
            return response
        except asyncio.TimeoutError:
            return None
        finally:
            self._pending_requests.pop(message.id, None)
            
    async def respond(
        self,
        request: WSMessage,
        payload: Dict[str, Any],
    ) -> bool:
        """响应请求"""
        return await self.send(WSMessage(
            type=WSMessageType.AGENT_RESPONSE,
            target=request.source,
            payload=payload,
            correlation_id=request.id,
        ))
        
    async def broadcast(self, payload: Dict[str, Any]) -> bool:
        """广播消息"""
        return await self.send(WSMessage(
            type=WSMessageType.AGENT_BROADCAST,
            payload=payload,
        ))


# ============== 便捷函数 ==============

def create_brain_server(
    host: str = "0.0.0.0",
    port: int = 8765,
) -> BrainWebSocketServer:
    """创建 Brain WebSocket 服务器"""
    return BrainWebSocketServer(host=host, port=port)


def create_brain_client(
    agent_id: str,
    server_url: str = "ws://localhost:8765",
) -> BrainWebSocketClient:
    """创建 Brain WebSocket 客户端"""
    return BrainWebSocketClient(agent_id=agent_id, server_url=server_url)
