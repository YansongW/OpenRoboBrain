"""
Sub-agent System

子 Agent 系统，支持：
- Spawn: 从主 Agent 派生后台 Agent
- Announce: 完成后回报结果
- Concurrency: 并发控制

借鉴 OpenClaw/Moltbot 的 Sub-agents 设计。
"""

from orb.agent.subagent.subagent_manager import (
    SubAgentManager,
    SubAgentConfig,
)
from orb.agent.subagent.spawn import (
    SubAgentSpawner,
    SpawnRequest,
    SpawnResult,
    SpawnStatus,
    create_subagent_spawner,
)
from orb.agent.subagent.announce import (
    AnnounceHandler,
    AnnounceMessage,
    AnnounceStatus,
)
from orb.agent.subagent.concurrency import (
    ConcurrencyController,
    QueueLane,
    QueuedTask,
    LaneType,
)

__all__ = [
    # Manager
    "SubAgentManager",
    "SubAgentConfig",
    # Spawn
    "SubAgentSpawner",
    "SpawnRequest",
    "SpawnResult",
    "SpawnStatus",
    "create_subagent_spawner",
    # Announce
    "AnnounceHandler",
    "AnnounceMessage",
    "AnnounceStatus",
    # Concurrency
    "ConcurrencyController",
    "QueueLane",
    "QueuedTask",
    "LaneType",
]
