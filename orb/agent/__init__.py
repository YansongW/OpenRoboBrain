"""
Agent层 (Agent Layer)

采用三级Agent架构：
1. Super Agent（管理层）：管理所有Agent的生命周期
2. 编排Agent（调度层）：任务编排与输入输出管理
3. 技能Agent（执行层）：调用技能层执行具体技能

技能Agent通过技能层(Skill Layer)来执行高层次语义化技能，
技能内部会编排多个原子动作(位于中间件层)来完成任务。

新增（借鉴 Moltbot/Clawdbot 设计）：
- Agent Runtime: 完整的 agentic loop 执行周期
- Agent Infrastructure: 工作空间、状态目录、会话存储
- Sub-agent System: 子 Agent 派生和结果回报
- Security: 工具策略、钩子系统、权限管理
"""

from orb.agent.base import BaseAgent, AgentState, AgentInfo, AgentLevel

# Infrastructure
from orb.agent.infrastructure import (
    AgentClient,
    WorkspaceManager,
    WorkspaceConfig,
    AgentDirManager,
    AgentDirConfig,
    SessionStore,
    Session,
    SessionMessage,
    SessionState,
)

# Runtime
from orb.agent.runtime import (
    AgentRuntime,
    RuntimeConfig,
    AgentLoop,
    LoopConfig,
    ContextBuilder,
    ContextConfig,
    ToolExecutor,
    ToolRegistry,
    StreamHandler,
)

# Sub-agent
from orb.agent.subagent import (
    SubAgentManager,
    SubAgentConfig,
    SubAgentSpawner,
    SpawnRequest,
    SpawnResult,
    AnnounceHandler,
    AnnounceMessage,
)

# Security
from orb.agent.security import (
    ToolPolicy,
    ToolPolicyConfig,
    HookManager,
    HookType,
    HookContext,
    PermissionManager,
    Permission,
)

__all__ = [
    # Base
    "BaseAgent",
    "AgentState",
    "AgentInfo",
    "AgentLevel",
    # Infrastructure
    "AgentClient",
    "WorkspaceManager",
    "WorkspaceConfig",
    "AgentDirManager",
    "AgentDirConfig",
    "SessionStore",
    "Session",
    "SessionMessage",
    "SessionState",
    # Runtime
    "AgentRuntime",
    "RuntimeConfig",
    "AgentLoop",
    "LoopConfig",
    "ContextBuilder",
    "ContextConfig",
    "ToolExecutor",
    "ToolRegistry",
    "StreamHandler",
    # Sub-agent
    "SubAgentManager",
    "SubAgentConfig",
    "SubAgentSpawner",
    "SpawnRequest",
    "SpawnResult",
    "AnnounceHandler",
    "AnnounceMessage",
    # Security
    "ToolPolicy",
    "ToolPolicyConfig",
    "HookManager",
    "HookType",
    "HookContext",
    "PermissionManager",
    "Permission",
]
