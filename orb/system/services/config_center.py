"""
配置中心

提供集中式配置管理、热更新和多环境配置支持。
支持从.env文件加载环境变量。
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from pydantic import BaseModel

from orb.system.services.logger import get_logger

logger = get_logger(__name__)


def load_dotenv(env_path: Optional[Path] = None) -> bool:
    """
    加载.env文件中的环境变量
    
    Args:
        env_path: .env文件路径，默认为项目根目录下的.env
        
    Returns:
        是否成功加载
    """
    if env_path is None:
        # 尝试找到项目根目录的.env文件
        current = Path.cwd()
        env_path = current / ".env"
        
        # 如果当前目录没有，向上查找
        if not env_path.exists():
            for parent in current.parents:
                candidate = parent / ".env"
                if candidate.exists():
                    env_path = candidate
                    break
    
    if not env_path or not env_path.exists():
        logger.debug(f".env文件不存在: {env_path}")
        return False
    
    logger.info(f"加载环境变量文件: {env_path}")
    
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                
                # 跳过空行和注释
                if not line or line.startswith("#"):
                    continue
                
                # 解析 KEY=VALUE 格式
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip()
                    
                    # 移除引号
                    if (value.startswith('"') and value.endswith('"')) or \
                       (value.startswith("'") and value.endswith("'")):
                        value = value[1:-1]
                    
                    # 只设置未定义的环境变量（不覆盖已有值）
                    if key and key not in os.environ:
                        os.environ[key] = value
                        logger.debug(f"设置环境变量: {key}")
        
        return True
    except Exception as e:
        logger.warning(f"加载.env文件失败: {e}")
        return False


def expand_env_vars(value: Any) -> Any:
    """
    展开字符串中的环境变量引用
    
    支持格式:
    - ${VAR_NAME}
    - $VAR_NAME
    
    Args:
        value: 要处理的值
        
    Returns:
        展开后的值
    """
    if isinstance(value, str):
        # 匹配 ${VAR_NAME} 或 $VAR_NAME
        pattern = r'\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)'
        
        def replace(match):
            var_name = match.group(1) or match.group(2)
            return os.environ.get(var_name, match.group(0))
        
        return re.sub(pattern, replace, value)
    elif isinstance(value, dict):
        return {k: expand_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [expand_env_vars(item) for item in value]
    else:
        return value


class SystemConfig(BaseModel):
    """系统配置模型"""
    name: str = "OpenRoboBrain"
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


class ORBConfig(BaseModel):
    """OpenRoboBrain 完整配置"""
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
        self._config: Optional[ORBConfig] = None
        self._raw_config: Dict[str, Any] = {}
        
    async def load(self) -> ORBConfig:
        """
        加载配置文件
        
        流程:
        1. 加载.env文件中的环境变量
        2. 加载YAML配置文件
        3. 展开配置中的环境变量引用
        4. 解析为配置对象
        
        Returns:
            ORBConfig 实例
        """
        # 1. 加载.env文件
        env_path = self.config_path.parent.parent / ".env"
        load_dotenv(env_path)
        
        # 2. 加载YAML配置
        if self.config_path.exists():
            logger.info(f"加载配置文件: {self.config_path}")
            with open(self.config_path, "r", encoding="utf-8") as f:
                self._raw_config = yaml.safe_load(f) or {}
        else:
            logger.warning(f"配置文件不存在，使用默认配置: {self.config_path}")
            self._raw_config = {}
        
        # 3. 展开环境变量引用
        self._raw_config = expand_env_vars(self._raw_config)
            
        # 4. 解析配置
        self._config = ORBConfig(**self._raw_config)
        return self._config
        
    async def reload(self) -> ORBConfig:
        """热重载配置"""
        logger.info("重新加载配置...")
        return await self.load()
        
    @property
    def config(self) -> ORBConfig:
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
