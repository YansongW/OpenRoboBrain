"""
Agent基础设施

提供Agent与大脑管道交互的客户端接口，以及 Agent 隔离所需的基础设施：
- AgentClient: Agent 与消息总线的交互接口
- WorkspaceManager: Agent 工作空间管理
- AgentDirManager: Agent 状态目录管理
- SessionStore: Agent 会话存储管理 (JSONL 持久化, Reset 策略)
"""

from kaibrain.agent.infrastructure.agent_client import AgentClient
from kaibrain.agent.infrastructure.workspace import (
    WorkspaceManager,
    WorkspaceConfig,
    BootstrapFile,
    create_workspace_manager,
    get_default_workspace_root,
)
from kaibrain.agent.infrastructure.agent_dir import (
    AgentDirManager,
    AgentDirConfig,
    AuthProfile,
    ModelConfig,
    create_agent_dir_manager,
)
from kaibrain.agent.infrastructure.session_store import (
    SessionStore,
    Session,
    SessionMessage,
    SessionMetadata,
    SessionState,
    MessageRole,
    ResetPolicy,
    ResetMode,
    create_session_store,
    create_reset_policy,
)

__all__ = [
    # Agent Client
    "AgentClient",
    # Workspace
    "WorkspaceManager",
    "WorkspaceConfig",
    "BootstrapFile",
    "create_workspace_manager",
    "get_default_workspace_root",
    # AgentDir
    "AgentDirManager",
    "AgentDirConfig",
    "AuthProfile",
    "ModelConfig",
    "create_agent_dir_manager",
    # Session Store
    "SessionStore",
    "Session",
    "SessionMessage",
    "SessionMetadata",
    "SessionState",
    "MessageRole",
    "ResetPolicy",
    "ResetMode",
    "create_session_store",
    "create_reset_policy",
]
