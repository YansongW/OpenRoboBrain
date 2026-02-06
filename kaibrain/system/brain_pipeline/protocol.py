"""
通信协议

定义Agent间通信的标准消息格式。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4


class MessageType(Enum):
    """消息类型"""
    # 任务相关
    TASK_REQUEST = "task_request"       # 任务请求
    TASK_RESPONSE = "task_response"     # 任务响应
    TASK_PROGRESS = "task_progress"     # 任务进度
    TASK_CANCEL = "task_cancel"         # 任务取消
    
    # Agent 管理
    AGENT_REGISTER = "agent_register"   # Agent注册
    AGENT_UNREGISTER = "agent_unregister"  # Agent注销
    AGENT_HEARTBEAT = "agent_heartbeat"    # Agent心跳
    AGENT_STATUS = "agent_status"       # Agent状态
    
    # Agent 间通信
    AGENT_MESSAGE = "agent_message"     # Agent间普通消息
    AGENT_REQUEST = "agent_request"     # Agent间请求
    AGENT_RESPONSE = "agent_response"   # Agent间响应
    
    # 数据相关
    DATA_QUERY = "data_query"           # 数据查询
    DATA_RESPONSE = "data_response"     # 数据响应
    DATA_UPDATE = "data_update"         # 数据更新
    
    # 系统相关
    SYSTEM_EVENT = "system_event"       # 系统事件
    SYSTEM_COMMAND = "system_command"   # 系统命令
    
    # 小脑桥接
    CEREBELLUM_COMMAND = "cerebellum_command"  # 发送到小脑的命令
    CEREBELLUM_FEEDBACK = "cerebellum_feedback"  # 小脑反馈


class MessagePriority(Enum):
    """消息优先级"""
    CRITICAL = 0  # 关键（安全相关）
    HIGH = 1      # 高
    NORMAL = 2    # 普通
    LOW = 3       # 低


@dataclass
class Message:
    """
    消息
    
    Agent间通信的标准消息格式。
    """
    # 消息标识
    message_id: str = field(default_factory=lambda: str(uuid4()))
    correlation_id: Optional[str] = None  # 关联ID，用于请求-响应关联
    
    # 消息类型
    type: MessageType = MessageType.TASK_REQUEST
    priority: MessagePriority = MessagePriority.NORMAL
    
    # 路由信息
    source: str = ""        # 发送者ID
    target: str = ""        # 接收者ID，空表示广播
    topic: str = ""         # 话题（用于发布-订阅）
    
    # 消息内容
    payload: Dict[str, Any] = field(default_factory=dict)
    
    # 元数据
    timestamp: datetime = field(default_factory=datetime.now)
    ttl: float = 60.0       # 生存时间（秒）
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_expired(self) -> bool:
        """检查消息是否已过期"""
        elapsed = (datetime.now() - self.timestamp).total_seconds()
        return elapsed > self.ttl
        
    def create_response(
        self,
        payload: Dict[str, Any],
        type: MessageType = MessageType.TASK_RESPONSE,
    ) -> Message:
        """创建响应消息"""
        return Message(
            correlation_id=self.message_id,
            type=type,
            source=self.target,
            target=self.source,
            payload=payload,
        )
        
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "message_id": self.message_id,
            "correlation_id": self.correlation_id,
            "type": self.type.value,
            "priority": self.priority.value,
            "source": self.source,
            "target": self.target,
            "topic": self.topic,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
            "ttl": self.ttl,
            "metadata": self.metadata,
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Message:
        """从字典创建"""
        return cls(
            message_id=data.get("message_id", str(uuid4())),
            correlation_id=data.get("correlation_id"),
            type=MessageType(data.get("type", "task_request")),
            priority=MessagePriority(data.get("priority", 2)),
            source=data.get("source", ""),
            target=data.get("target", ""),
            topic=data.get("topic", ""),
            payload=data.get("payload", {}),
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.now(),
            ttl=data.get("ttl", 60.0),
            metadata=data.get("metadata", {}),
        )


@dataclass
class TaskRequest:
    """任务请求"""
    task_id: str = field(default_factory=lambda: str(uuid4()))
    task_type: str = ""
    input_data: Dict[str, Any] = field(default_factory=dict)
    parameters: Dict[str, Any] = field(default_factory=dict)
    timeout: float = 60.0
    
    def to_message(self, source: str, target: str) -> Message:
        """转换为消息"""
        return Message(
            type=MessageType.TASK_REQUEST,
            source=source,
            target=target,
            payload={
                "task_id": self.task_id,
                "task_type": self.task_type,
                "input_data": self.input_data,
                "parameters": self.parameters,
                "timeout": self.timeout,
            },
        )


@dataclass
class TaskResponse:
    """任务响应"""
    task_id: str = ""
    success: bool = True
    result: Any = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    
    def to_message(self, source: str, target: str, correlation_id: str) -> Message:
        """转换为消息"""
        return Message(
            correlation_id=correlation_id,
            type=MessageType.TASK_RESPONSE,
            source=source,
            target=target,
            payload={
                "task_id": self.task_id,
                "success": self.success,
                "result": self.result,
                "error": self.error,
                "execution_time_ms": self.execution_time_ms,
            },
        )
