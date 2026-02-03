"""
LLM工厂

提供统一的LLM创建入口。
"""

from __future__ import annotations

from typing import Dict, Optional, Type

from kaibrain.system.llm.base import BaseLLM
from kaibrain.system.llm.config import LLMConfig, ProviderConfig
from kaibrain.system.services.logger import LoggerMixin, get_logger

logger = get_logger(__name__)


class LLMFactory(LoggerMixin):
    """
    LLM工厂
    
    统一的LLM创建入口，支持多Provider。
    """
    
    # 已注册的Provider类
    _providers: Dict[str, Type[BaseLLM]] = {}
    
    @classmethod
    def register(cls, name: str, provider_class: Type[BaseLLM]) -> None:
        """
        注册Provider
        
        Args:
            name: Provider名称
            provider_class: Provider类
        """
        cls._providers[name] = provider_class
        logger.info(f"Registered LLM provider: {name}")
    
    @classmethod
    def get_provider_class(cls, name: str) -> Type[BaseLLM]:
        """
        获取Provider类
        
        Args:
            name: Provider名称
            
        Returns:
            Provider类
            
        Raises:
            ValueError: Provider未注册
        """
        if name not in cls._providers:
            # 尝试懒加载
            cls._lazy_load_provider(name)
        
        if name not in cls._providers:
            raise ValueError(
                f"Unknown provider: {name}. "
                f"Available: {list(cls._providers.keys())}"
            )
        
        return cls._providers[name]
    
    # OpenAI兼容的Provider列表
    OPENAI_COMPATIBLE_PROVIDERS = {
        "kimi", "glm", "qwen", "doubao", "deepseek", 
        "yi", "baichuan", "minimax", "zhipu"
    }
    
    @classmethod
    def _lazy_load_provider(cls, name: str) -> None:
        """懒加载Provider"""
        try:
            if name == "openai":
                from kaibrain.system.llm.providers.openai import OpenAILLM
                cls._providers["openai"] = OpenAILLM
            elif name == "anthropic":
                from kaibrain.system.llm.providers.anthropic import AnthropicLLM
                cls._providers["anthropic"] = AnthropicLLM
            elif name == "ollama":
                from kaibrain.system.llm.providers.ollama import OllamaLLM
                cls._providers["ollama"] = OllamaLLM
            elif name in cls.OPENAI_COMPATIBLE_PROVIDERS:
                # 国产模型都使用OpenAI兼容接口
                from kaibrain.system.llm.providers.openai import OpenAILLM
                cls._providers[name] = OpenAILLM
        except ImportError as e:
            logger.warning(f"Failed to load provider {name}: {e}")
    
    @classmethod
    def create(
        cls,
        provider: str,
        config: Optional[ProviderConfig] = None,
        **kwargs,
    ) -> BaseLLM:
        """
        创建LLM实例
        
        Args:
            provider: Provider名称
            config: Provider配置
            **kwargs: 额外参数（会覆盖config中的值）
            
        Returns:
            BaseLLM实例
        """
        provider_class = cls.get_provider_class(provider)
        
        # 合并配置
        init_kwargs = {}
        if config:
            init_kwargs.update({
                "model": config.model,
                "api_key": config.api_key,
                "base_url": config.base_url,
                "timeout": config.timeout,
                "max_retries": config.max_retries,
                **config.extra,
            })
        init_kwargs.update(kwargs)
        
        # 移除None值
        init_kwargs = {k: v for k, v in init_kwargs.items() if v is not None}
        
        return provider_class(**init_kwargs)
    
    @classmethod
    def create_from_config(
        cls,
        llm_config: LLMConfig,
        provider: Optional[str] = None,
        **kwargs,
    ) -> BaseLLM:
        """
        从配置创建LLM实例
        
        Args:
            llm_config: LLM配置
            provider: Provider名称（可选，默认使用配置中的default_provider）
            **kwargs: 额外参数
            
        Returns:
            BaseLLM实例
        """
        provider = provider or llm_config.default_provider
        provider_config = llm_config.get_provider_config(provider)
        
        return cls.create(provider, provider_config, **kwargs)
    
    @classmethod
    def list_providers(cls) -> list:
        """列出所有可用的Provider"""
        # 所有已知的provider
        all_providers = [
            "openai", "anthropic", "ollama",
            # 国产模型 (OpenAI兼容)
            "kimi", "glm", "qwen", "doubao", "deepseek",
            "yi", "baichuan", "minimax",
        ]
        # 尝试加载
        for name in all_providers:
            cls._lazy_load_provider(name)
        return list(cls._providers.keys())
    
    @classmethod
    def is_openai_compatible(cls, provider: str) -> bool:
        """检查provider是否是OpenAI兼容的"""
        return provider in cls.OPENAI_COMPATIBLE_PROVIDERS or provider == "openai"


def create_llm(
    provider: Optional[str] = None,
    config: Optional[LLMConfig] = None,
    **kwargs,
) -> BaseLLM:
    """
    便捷函数：创建LLM实例
    
    Args:
        provider: Provider名称（可选）
        config: LLM配置（可选）
        **kwargs: 额外参数
        
    Returns:
        BaseLLM实例
        
    Examples:
        # 使用默认配置创建OpenAI
        llm = create_llm("openai", model="gpt-4o", api_key="...")
        
        # 使用配置文件创建
        config = LLMConfig.from_dict(yaml_data)
        llm = create_llm(config=config)
    """
    if config:
        return LLMFactory.create_from_config(config, provider, **kwargs)
    
    provider = provider or "openai"
    return LLMFactory.create(provider, **kwargs)
