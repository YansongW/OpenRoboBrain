"""
LLM基础设施模块

提供大语言模型的统一接口、多Provider支持和工具调用能力。

支持的Provider:
- OpenAI (GPT-4o, GPT-4, GPT-3.5等)
- Anthropic (Claude系列)
- Kimi (月之暗面 Moonshot)
- GLM (智谱清言)
- Qwen (通义千问)
- Doubao (字节豆包)
- DeepSeek
- Ollama (本地模型)
"""

from kaibrain.system.llm.base import BaseLLM, LLMCapabilities
from kaibrain.system.llm.message import (
    LLMMessage,
    LLMResponse,
    MessageRole,
    FinishReason,
    Usage,
    ToolCall,
    ToolResult,
)
from kaibrain.system.llm.config import (
    LLMConfig, 
    ProviderConfig,
    OPENAI_COMPATIBLE_ENDPOINTS,
    DEFAULT_MODELS,
)
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
    "ToolCall",
    "ToolResult",
    # 配置
    "LLMConfig",
    "ProviderConfig",
    "OPENAI_COMPATIBLE_ENDPOINTS",
    "DEFAULT_MODELS",
    # 工厂
    "LLMFactory",
    "create_llm",
]
