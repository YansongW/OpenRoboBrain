"""
配置中心

提供集中式配置管理、热更新和多环境配置支持。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from pydantic import BaseModel

from kaibrain.system.services.logger import get_logger

logger = get_logger(__name__)


class SystemConfig(BaseModel):
    """系统配置模型"""
    name: str = "KaiBrain"
    version: str = "0.1.0"
    debug: bool = False
    log_level: str = "INFO"


class BrainPipelineConfig(BaseModel):
    """大脑管道配置"""
    message_bus_type: str = "memory"  # memory, redis, zeromq
    redis_url: Optional[str] = None
    max_queue_size: int = 10000
    message_timeout: float = 30.0


class DataConfig(BaseModel):
    """数据层配置"""
    # 显性数据
    explicit_db_url: str = "sqlite:///data/explicit.db"
    vector_db_path: str = "data/vectordb"
    graph_db_url: Optional[str] = None
    
    # 隐性数据
    implicit_policy_path: str = "data/policies"
    implicit_mech_config_path: str = "data/mech_config"


class AgentConfig(BaseModel):
    """Agent配置"""
    max_concurrent_agents: int = 100
    agent_timeout: float = 60.0
    health_check_interval: float = 10.0


class KaiBrainConfig(BaseModel):
    """KaiBrain 完整配置"""
    system: SystemConfig = SystemConfig()
    brain_pipeline: BrainPipelineConfig = BrainPipelineConfig()
    data: DataConfig = DataConfig()
    agent: AgentConfig = AgentConfig()


class ConfigCenter:
    """
    配置中心
    
    负责加载、管理和热更新配置。
    """
    
    def __init__(self, config_path: str = "configs/system.yaml"):
        """
        初始化配置中心
        
        Args:
            config_path: 配置文件路径
        """
        self.config_path = Path(config_path)
        self._config: Optional[KaiBrainConfig] = None
        self._raw_config: Dict[str, Any] = {}
        
    async def load(self) -> KaiBrainConfig:
        """
        加载配置文件
        
        Returns:
            KaiBrainConfig 实例
        """
        if self.config_path.exists():
            logger.info(f"加载配置文件: {self.config_path}")
            with open(self.config_path, "r", encoding="utf-8") as f:
                self._raw_config = yaml.safe_load(f) or {}
        else:
            logger.warning(f"配置文件不存在，使用默认配置: {self.config_path}")
            self._raw_config = {}
            
        # 解析配置
        self._config = KaiBrainConfig(**self._raw_config)
        return self._config
        
    async def reload(self) -> KaiBrainConfig:
        """热重载配置"""
        logger.info("重新加载配置...")
        return await self.load()
        
    @property
    def config(self) -> KaiBrainConfig:
        """获取当前配置"""
        if self._config is None:
            raise RuntimeError("配置尚未加载，请先调用 load()")
        return self._config
        
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值
        
        Args:
            key: 配置键，支持点号分隔的嵌套键
            default: 默认值
            
        Returns:
            配置值
        """
        keys = key.split(".")
        value = self._raw_config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
                
        return value
