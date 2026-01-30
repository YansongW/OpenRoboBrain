"""
LLM消息类型定义

定义LLM交互中使用的消息、响应和相关数据结构。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union


class MessageRole(str, Enum):
    """消息角色"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class FinishReason(str, Enum):
    """完成原因"""
    STOP = "stop"              # 正常结束
    TOOL_CALLS = "tool_calls"  # 需要工具调用
    LENGTH = "length"          # 达到长度限制
    CONTENT_FILTER = "content_filter"  # 内容过滤
    ERROR = "error"            # 错误


@dataclass
class ToolCall:
    """工具调用请求"""
    id: str
    name: str
    arguments: Dict[str, Any]
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "arguments": self.arguments,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "ToolCall":
        """从字典创建"""
        return cls(
            id=data["id"],
            name=data["name"],
            arguments=data.get("arguments", {}),
        )


@dataclass
class ToolResult:
    """工具执行结果"""
    tool_call_id: str
    content: Any
    is_error: bool = False
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "tool_call_id": self.tool_call_id,
            "content": self.content,
            "is_error": self.is_error,
        }


@dataclass
class LLMMessage:
    """LLM消息"""
    role: MessageRole
    content: str
    name: Optional[str] = None  # 用于tool消息的函数名
    tool_calls: Optional[List[ToolCall]] = None  # assistant消息的工具调用
    tool_call_id: Optional[str] = None  # tool消息的调用ID
    
    def to_dict(self) -> dict:
        """转换为字典"""
        result = {
            "role": self.role.value if isinstance(self.role, MessageRole) else self.role,
            "content": self.content,
        }
        if self.name:
            result["name"] = self.name
        if self.tool_calls:
            result["tool_calls"] = [tc.to_dict() for tc in self.tool_calls]
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        return result
    
    @classmethod
    def from_dict(cls, data: dict) -> "LLMMessage":
        """从字典创建"""
        role = data["role"]
        if isinstance(role, str):
            role = MessageRole(role)
        
        tool_calls = None
        if data.get("tool_calls"):
            tool_calls = [ToolCall.from_dict(tc) for tc in data["tool_calls"]]
        
        return cls(
            role=role,
            content=data.get("content", ""),
            name=data.get("name"),
            tool_calls=tool_calls,
            tool_call_id=data.get("tool_call_id"),
        )
    
    @classmethod
    def system(cls, content: str) -> "LLMMessage":
        """创建系统消息"""
        return cls(role=MessageRole.SYSTEM, content=content)
    
    @classmethod
    def user(cls, content: str) -> "LLMMessage":
        """创建用户消息"""
        return cls(role=MessageRole.USER, content=content)
    
    @classmethod
    def assistant(
        cls, 
        content: str, 
        tool_calls: Optional[List[ToolCall]] = None
    ) -> "LLMMessage":
        """创建助手消息"""
        return cls(
            role=MessageRole.ASSISTANT, 
            content=content,
            tool_calls=tool_calls,
        )
    
    @classmethod
    def tool(cls, tool_call_id: str, content: str, name: Optional[str] = None) -> "LLMMessage":
        """创建工具结果消息"""
        return cls(
            role=MessageRole.TOOL,
            content=content,
            name=name,
            tool_call_id=tool_call_id,
        )


@dataclass
class Usage:
    """Token使用统计"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Usage":
        """从字典创建"""
        return cls(
            prompt_tokens=data.get("prompt_tokens", 0),
            completion_tokens=data.get("completion_tokens", 0),
            total_tokens=data.get("total_tokens", 0),
        )


@dataclass
class LLMResponse:
    """LLM响应"""
    content: str
    finish_reason: FinishReason
    tool_calls: Optional[List[ToolCall]] = None
    usage: Optional[Usage] = None
    model: Optional[str] = None
    raw_response: Optional[Any] = None  # 原始响应，用于调试
    
    def to_dict(self) -> dict:
        """转换为字典"""
        result = {
            "content": self.content,
            "finish_reason": self.finish_reason.value,
        }
        if self.tool_calls:
            result["tool_calls"] = [tc.to_dict() for tc in self.tool_calls]
        if self.usage:
            result["usage"] = self.usage.to_dict()
        if self.model:
            result["model"] = self.model
        return result
    
    @property
    def has_tool_calls(self) -> bool:
        """是否有工具调用"""
        return bool(self.tool_calls)
    
    @property
    def is_complete(self) -> bool:
        """是否正常完成（无工具调用）"""
        return self.finish_reason == FinishReason.STOP


@dataclass
class StreamChunk:
    """流式响应块"""
    content: str = ""
    tool_calls: Optional[List[ToolCall]] = None
    finish_reason: Optional[FinishReason] = None
    is_final: bool = False
