"""
AgentDir 管理器

管理 Agent 的状态目录，包括认证配置、模型注册和会话存储。
借鉴 Moltbot 的设计，每个 Agent 有独立的 agentDir。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from orb.system.services.logger import LoggerMixin


@dataclass
class AuthProfile:
    """认证配置"""
    profile_id: str
    provider: str
    credentials: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "profile_id": self.profile_id,
            "provider": self.provider,
            "credentials": self.credentials,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AuthProfile:
        """从字典创建"""
        return cls(
            profile_id=data.get("profile_id", ""),
            provider=data.get("provider", ""),
            credentials=data.get("credentials", {}),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ModelConfig:
    """模型配置"""
    model_id: str
    provider: str
    model_name: str
    api_key_ref: Optional[str] = None  # 引用 auth profile
    parameters: Dict[str, Any] = field(default_factory=dict)
    cost: Optional[Dict[str, float]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "model_id": self.model_id,
            "provider": self.provider,
            "model_name": self.model_name,
            "api_key_ref": self.api_key_ref,
            "parameters": self.parameters,
            "cost": self.cost,
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ModelConfig:
        """从字典创建"""
        return cls(
            model_id=data.get("model_id", ""),
            provider=data.get("provider", ""),
            model_name=data.get("model_name", ""),
            api_key_ref=data.get("api_key_ref"),
            parameters=data.get("parameters", {}),
            cost=data.get("cost"),
        )


@dataclass
class AgentDirConfig:
    """AgentDir 配置"""
    base_path: Path  # 基础路径，如 ~/.OpenRoboBrain
    agent_id: str
    create_if_missing: bool = True


class AgentDirManager(LoggerMixin):
    """
    AgentDir 管理器
    
    管理 Agent 的状态目录，包括：
    - 认证配置 (auth-profiles.json)
    - 模型注册 (models.json)
    - Agent 配置 (agent-config.json)
    - 会话目录 (sessions/)
    
    目录结构：
    ~/.OpenRoboBrain/agents/<agentId>/
    ├── agent/
    │   ├── auth-profiles.json    # 认证配置
    │   ├── models.json           # 模型配置
    │   └── agent-config.json     # Agent 配置
    └── sessions/                 # 会话存储
        └── <sessionId>.jsonl     # 会话记录
    """
    
    def __init__(self, config: AgentDirConfig):
        """
        初始化 AgentDir 管理器
        
        Args:
            config: AgentDir 配置
        """
        self._config = config
        self._base_path = config.base_path
        self._agent_id = config.agent_id
        self._initialized = False
        
        # 计算目录路径
        self._agent_root = self._base_path / "agents" / self._agent_id
        self._agent_dir = self._agent_root / "agent"
        self._sessions_dir = self._agent_root / "sessions"
        
        # 文件路径
        self._auth_profiles_path = self._agent_dir / "auth-profiles.json"
        self._models_path = self._agent_dir / "models.json"
        self._config_path = self._agent_dir / "agent-config.json"
        
        # 缓存
        self._auth_profiles: Dict[str, AuthProfile] = {}
        self._models: Dict[str, ModelConfig] = {}
        self._agent_config: Dict[str, Any] = {}
        
    @property
    def agent_id(self) -> str:
        """Agent ID"""
        return self._agent_id
        
    @property
    def agent_root(self) -> Path:
        """Agent 根目录"""
        return self._agent_root
        
    @property
    def agent_dir(self) -> Path:
        """Agent 配置目录"""
        return self._agent_dir
        
    @property
    def sessions_dir(self) -> Path:
        """会话目录"""
        return self._sessions_dir
        
    @classmethod
    def get_default_base_path(cls) -> Path:
        """
        获取默认基础路径
        
        Returns:
            默认基础路径
        """
        env_path = os.environ.get("ORB_STATE_DIR")
        if env_path:
            return Path(env_path).expanduser()
        return Path.home() / ".OpenRoboBrain"
        
    def initialize(self) -> bool:
        """
        初始化 AgentDir
        
        Returns:
            是否成功
        """
        if self._initialized:
            return True
            
        self.logger.info(f"初始化 AgentDir: {self._agent_root}")
        
        try:
            # 创建目录结构
            if self._config.create_if_missing:
                self._agent_dir.mkdir(parents=True, exist_ok=True)
                self._sessions_dir.mkdir(parents=True, exist_ok=True)
            elif not self._agent_root.exists():
                self.logger.error(f"AgentDir 不存在: {self._agent_root}")
                return False
                
            # 加载配置
            self._load_auth_profiles()
            self._load_models()
            self._load_agent_config()
            
            self._initialized = True
            self.logger.info(f"AgentDir 初始化完成: {self._agent_root}")
            return True
            
        except Exception as e:
            self.logger.error(f"AgentDir 初始化失败: {e}")
            return False
            
    # ============== 认证配置管理 ==============
    
    def _load_auth_profiles(self) -> None:
        """加载认证配置"""
        self._auth_profiles = {}
        
        if self._auth_profiles_path.exists():
            try:
                data = json.loads(self._auth_profiles_path.read_text(encoding="utf-8"))
                for profile_data in data.get("profiles", []):
                    profile = AuthProfile.from_dict(profile_data)
                    self._auth_profiles[profile.profile_id] = profile
            except Exception as e:
                self.logger.warning(f"加载认证配置失败: {e}")
                
    def _save_auth_profiles(self) -> None:
        """保存认证配置"""
        data = {
            "profiles": [p.to_dict() for p in self._auth_profiles.values()],
            "updated_at": datetime.now().isoformat(),
        }
        self._auth_profiles_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        
    def get_auth_profile(self, profile_id: str) -> Optional[AuthProfile]:
        """
        获取认证配置
        
        Args:
            profile_id: 配置 ID
            
        Returns:
            认证配置
        """
        return self._auth_profiles.get(profile_id)
        
    def get_auth_profiles_by_provider(self, provider: str) -> List[AuthProfile]:
        """
        按提供者获取认证配置
        
        Args:
            provider: 提供者名称
            
        Returns:
            认证配置列表
        """
        return [
            p for p in self._auth_profiles.values()
            if p.provider == provider
        ]
        
    def set_auth_profile(self, profile: AuthProfile) -> None:
        """
        设置认证配置
        
        Args:
            profile: 认证配置
        """
        now = datetime.now().isoformat()
        if not profile.created_at:
            profile.created_at = now
        profile.updated_at = now
        
        self._auth_profiles[profile.profile_id] = profile
        self._save_auth_profiles()
        
    def delete_auth_profile(self, profile_id: str) -> bool:
        """
        删除认证配置
        
        Args:
            profile_id: 配置 ID
            
        Returns:
            是否成功
        """
        if profile_id in self._auth_profiles:
            del self._auth_profiles[profile_id]
            self._save_auth_profiles()
            return True
        return False
        
    def list_auth_profiles(self) -> List[AuthProfile]:
        """
        列出所有认证配置
        
        Returns:
            认证配置列表
        """
        return list(self._auth_profiles.values())
        
    # ============== 模型配置管理 ==============
    
    def _load_models(self) -> None:
        """加载模型配置"""
        self._models = {}
        
        if self._models_path.exists():
            try:
                data = json.loads(self._models_path.read_text(encoding="utf-8"))
                for model_data in data.get("models", []):
                    model = ModelConfig.from_dict(model_data)
                    self._models[model.model_id] = model
            except Exception as e:
                self.logger.warning(f"加载模型配置失败: {e}")
                
    def _save_models(self) -> None:
        """保存模型配置"""
        data = {
            "models": [m.to_dict() for m in self._models.values()],
            "updated_at": datetime.now().isoformat(),
        }
        self._models_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        
    def get_model(self, model_id: str) -> Optional[ModelConfig]:
        """
        获取模型配置
        
        Args:
            model_id: 模型 ID
            
        Returns:
            模型配置
        """
        return self._models.get(model_id)
        
    def set_model(self, model: ModelConfig) -> None:
        """
        设置模型配置
        
        Args:
            model: 模型配置
        """
        self._models[model.model_id] = model
        self._save_models()
        
    def delete_model(self, model_id: str) -> bool:
        """
        删除模型配置
        
        Args:
            model_id: 模型 ID
            
        Returns:
            是否成功
        """
        if model_id in self._models:
            del self._models[model_id]
            self._save_models()
            return True
        return False
        
    def list_models(self) -> List[ModelConfig]:
        """
        列出所有模型配置
        
        Returns:
            模型配置列表
        """
        return list(self._models.values())
        
    # ============== Agent 配置管理 ==============
    
    def _load_agent_config(self) -> None:
        """加载 Agent 配置"""
        self._agent_config = {}
        
        if self._config_path.exists():
            try:
                self._agent_config = json.loads(
                    self._config_path.read_text(encoding="utf-8")
                )
            except Exception as e:
                self.logger.warning(f"加载 Agent 配置失败: {e}")
                
    def _save_agent_config(self) -> None:
        """保存 Agent 配置"""
        self._agent_config["updated_at"] = datetime.now().isoformat()
        self._config_path.write_text(
            json.dumps(self._agent_config, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        
    def get_config(self, key: str, default: Any = None) -> Any:
        """
        获取配置值
        
        Args:
            key: 配置键
            default: 默认值
            
        Returns:
            配置值
        """
        return self._agent_config.get(key, default)
        
    def set_config(self, key: str, value: Any) -> None:
        """
        设置配置值
        
        Args:
            key: 配置键
            value: 配置值
        """
        self._agent_config[key] = value
        self._save_agent_config()
        
    def get_all_config(self) -> Dict[str, Any]:
        """
        获取所有配置
        
        Returns:
            配置字典
        """
        return self._agent_config.copy()
        
    def update_config(self, updates: Dict[str, Any]) -> None:
        """
        批量更新配置
        
        Args:
            updates: 更新字典
        """
        self._agent_config.update(updates)
        self._save_agent_config()
        
    # ============== 会话管理 ==============
    
    def get_session_path(self, session_id: str) -> Path:
        """
        获取会话文件路径
        
        Args:
            session_id: 会话 ID
            
        Returns:
            会话文件路径
        """
        return self._sessions_dir / f"{session_id}.jsonl"
        
    def list_sessions(self) -> List[str]:
        """
        列出所有会话
        
        Returns:
            会话 ID 列表
        """
        sessions = []
        if self._sessions_dir.exists():
            for file in self._sessions_dir.glob("*.jsonl"):
                sessions.append(file.stem)
        return sessions
        
    def session_exists(self, session_id: str) -> bool:
        """
        检查会话是否存在
        
        Args:
            session_id: 会话 ID
            
        Returns:
            是否存在
        """
        return self.get_session_path(session_id).exists()
        
    def delete_session(self, session_id: str) -> bool:
        """
        删除会话
        
        Args:
            session_id: 会话 ID
            
        Returns:
            是否成功
        """
        session_path = self.get_session_path(session_id)
        if session_path.exists():
            # 重命名为 .deleted.<timestamp>
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            deleted_path = session_path.with_suffix(f".deleted.{timestamp}")
            session_path.rename(deleted_path)
            return True
        return False
        
    def archive_session(self, session_id: str) -> bool:
        """
        归档会话（同 delete，保留文件但重命名）
        
        Args:
            session_id: 会话 ID
            
        Returns:
            是否成功
        """
        return self.delete_session(session_id)
        
    # ============== 信息获取 ==============
    
    def get_info(self) -> Dict[str, Any]:
        """
        获取 AgentDir 信息
        
        Returns:
            AgentDir 信息
        """
        return {
            "agent_id": self._agent_id,
            "agent_root": str(self._agent_root),
            "agent_dir": str(self._agent_dir),
            "sessions_dir": str(self._sessions_dir),
            "initialized": self._initialized,
            "auth_profiles_count": len(self._auth_profiles),
            "models_count": len(self._models),
            "sessions_count": len(self.list_sessions()),
            "directories_exist": {
                "agent_root": self._agent_root.exists(),
                "agent_dir": self._agent_dir.exists(),
                "sessions_dir": self._sessions_dir.exists(),
            },
            "files_exist": {
                "auth_profiles": self._auth_profiles_path.exists(),
                "models": self._models_path.exists(),
                "config": self._config_path.exists(),
            },
        }
        
    def cleanup(self) -> None:
        """清理临时文件"""
        # 可以在这里添加清理逻辑
        pass


# 便捷函数
def create_agent_dir_manager(
    agent_id: str,
    base_path: Optional[Path] = None,
    **kwargs,
) -> AgentDirManager:
    """
    创建 AgentDir 管理器
    
    Args:
        agent_id: Agent ID
        base_path: 基础路径
        **kwargs: 其他配置参数
        
    Returns:
        AgentDirManager 实例
    """
    if base_path is None:
        base_path = AgentDirManager.get_default_base_path()
        
    config = AgentDirConfig(
        base_path=base_path,
        agent_id=agent_id,
        **kwargs,
    )
    
    return AgentDirManager(config)
