"""
LLM Providers

各个LLM提供商的实现。
"""

from typing import TYPE_CHECKING

# 懒加载，避免未安装依赖时报错
__all__ = ["OpenAILLM", "AnthropicLLM", "OllamaLLM"]


def __getattr__(name: str):
    """懒加载Provider类"""
    if name == "OpenAILLM":
        from orb.system.llm.providers.openai import OpenAILLM
        return OpenAILLM
    elif name == "AnthropicLLM":
        from orb.system.llm.providers.anthropic import AnthropicLLM
        return AnthropicLLM
    elif name == "OllamaLLM":
        from orb.system.llm.providers.ollama import OllamaLLM
        return OllamaLLM
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
