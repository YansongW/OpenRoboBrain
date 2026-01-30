"""
LLM基础设施模块

提供大语言模型的统一接口、多Provider支持和工具调用能力。
"""

from kaibrain.system.llm.base import BaseLLM, LLMCapabilities
from kaibrain.system.llm.message import (
    LLMMessage,
    LLMResponse,
    MessageRole,
    FinishReason,
    Usage,
)
from kaibrain.system.llm.config import LLMConfig, ProviderConfig
from kaibrain.system.llm.factory import LLMFactory, create_llm

__all__ = [
    # 基类
    "BaseLLM",
    "LLMCapabilities",
    # 消息类型
    "LLMMessage",
    "LLMResponse",
    "MessageRole",
    "FinishReason",
    "Usage",
    # 配置
    "LLMConfig",
    "ProviderConfig",
    # 工厂
    "LLMFactory",
    "create_llm",
]
