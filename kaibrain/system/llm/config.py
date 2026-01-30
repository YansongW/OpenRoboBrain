"""
LLM配置管理

管理LLM Provider的配置，支持环境变量替换。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from kaibrain.system.services.logger import LoggerMixin


def resolve_env_vars(value: Any) -> Any:
    """
    解析环境变量
    
    支持 ${VAR_NAME} 或 $VAR_NAME 格式
    """
    if isinstance(value, str):
        # 匹配 ${VAR_NAME} 或 $VAR_NAME
        pattern = r'\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)'
        
        def replace(match):
            var_name = match.group(1) or match.group(2)
            return os.environ.get(var_name, match.group(0))
        
        return re.sub(pattern, replace, value)
    elif isinstance(value, dict):
        return {k: resolve_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [resolve_env_vars(item) for item in value]
    return value


@dataclass
class ProviderConfig:
    """单个Provider的配置"""
    api_key: Optional[str] = None
    model: str = ""
    base_url: Optional[str] = None
    timeout: float = 60.0
    max_retries: int = 3
    extra: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """解析环境变量"""
        self.api_key = resolve_env_vars(self.api_key)
        self.base_url = resolve_env_vars(self.base_url)
        self.extra = resolve_env_vars(self.extra)
    
    @classmethod
    def from_dict(cls, data: dict) -> "ProviderConfig":
        """从字典创建"""
        known_keys = {"api_key", "model", "base_url", "timeout", "max_retries"}
        extra = {k: v for k, v in data.items() if k not in known_keys}
        
        return cls(
            api_key=data.get("api_key"),
            model=data.get("model", ""),
            base_url=data.get("base_url"),
            timeout=data.get("timeout", 60.0),
            max_retries=data.get("max_retries", 3),
            extra=extra,
        )
    
    def to_dict(self) -> dict:
        """转换为字典"""
        result = {
            "model": self.model,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
        }
        if self.api_key:
            result["api_key"] = self.api_key
        if self.base_url:
            result["base_url"] = self.base_url
        if self.extra:
            result.update(self.extra)
        return result


@dataclass
class LLMConfig(LoggerMixin):
    """LLM总体配置"""
    default_provider: str = "openai"
    providers: Dict[str, ProviderConfig] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: dict) -> "LLMConfig":
        """从字典创建"""
        providers = {}
        providers_data = data.get("providers", {})
        
        for name, config in providers_data.items():
            if isinstance(config, dict):
                providers[name] = ProviderConfig.from_dict(config)
            elif isinstance(config, ProviderConfig):
                providers[name] = config
        
        return cls(
            default_provider=data.get("default_provider", "openai"),
            providers=providers,
        )
    
    def get_provider_config(self, provider: Optional[str] = None) -> ProviderConfig:
        """
        获取Provider配置
        
        Args:
            provider: Provider名称，为None时使用默认Provider
            
        Returns:
            ProviderConfig
            
        Raises:
            ValueError: Provider不存在
        """
        provider = provider or self.default_provider
        
        if provider not in self.providers:
            raise ValueError(f"Unknown provider: {provider}. Available: {list(self.providers.keys())}")
        
        return self.providers[provider]
    
    def add_provider(self, name: str, config: ProviderConfig) -> None:
        """添加Provider配置"""
        self.providers[name] = config
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "default_provider": self.default_provider,
            "providers": {
                name: config.to_dict() 
                for name, config in self.providers.items()
            },
        }


# 默认配置
DEFAULT_LLM_CONFIG = LLMConfig(
    default_provider="openai",
    providers={
        "openai": ProviderConfig(
            api_key="${OPENAI_API_KEY}",
            model="gpt-4o",
        ),
        "anthropic": ProviderConfig(
            api_key="${ANTHROPIC_API_KEY}",
            model="claude-sonnet-4-20250514",
        ),
        "ollama": ProviderConfig(
            model="llama3.2",
            base_url="http://localhost:11434",
        ),
    },
)
