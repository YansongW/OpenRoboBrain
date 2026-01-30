"""
大脑管道 (Brain Pipeline)

系统层的核心组件，负责所有Agent间的通信。

架构设计原则：
- 大脑管道使用 WebSocket JSON 协议（非实时，高层次）
- 小脑管道使用 ROS2 DDS 协议（实时，低层次）
- 两者通过 BrainCerebellumBridge 进行状态同步
- 大小脑完全解耦，各自有独立的工具、记忆、沙箱机制

组件：
- MessageBus: 内存消息总线（进程内）
- WebSocket Server/Client: 多Agent协作通信
- BrainCerebellumBridge: 大小脑桥接器
- Protocol: 通信协议
- Routing: 消息路由
"""

from kaibrain.system.brain_pipeline.message_bus import MessageBus
from kaibrain.system.brain_pipeline.protocol import Message, MessageType
from kaibrain.system.brain_pipeline.routing import (
    MessageRouter,
    Binding,
    MatchRule,
    PeerMatch,
    PeerKind,
    MatchType,
    RoutingResult,
    create_router,
    create_capability_binding,
    create_channel_binding,
    create_peer_binding,
)
from kaibrain.system.brain_pipeline.websocket_server import (
    BrainWebSocketServer,
    BrainWebSocketClient,
    WSMessage,
    WSMessageType,
    WSClient,
    create_brain_server,
    create_brain_client,
)
from kaibrain.system.brain_pipeline.brain_cerebellum_bridge import (
    BrainCerebellumBridge,
    BrainCommand,
    CerebellumAction,
    CerebellumFeedback,
    CommandPriority,
    ExecutionStatus,
    SyncDirection,
    CommandTranslator,
    create_bridge,
)

__all__ = [
    # Message Bus (内存)
    "MessageBus",
    "Message",
    "MessageType",
    # WebSocket (网络)
    "BrainWebSocketServer",
    "BrainWebSocketClient",
    "WSMessage",
    "WSMessageType",
    "WSClient",
    "create_brain_server",
    "create_brain_client",
    # Brain-Cerebellum Bridge
    "BrainCerebellumBridge",
    "BrainCommand",
    "CerebellumAction",
    "CerebellumFeedback",
    "CommandPriority",
    "ExecutionStatus",
    "SyncDirection",
    "CommandTranslator",
    "create_bridge",
    # Routing
    "MessageRouter",
    "Binding",
    "MatchRule",
    "PeerMatch",
    "PeerKind",
    "MatchType",
    "RoutingResult",
    "create_router",
    "create_capability_binding",
    "create_channel_binding",
    "create_peer_binding",
]
