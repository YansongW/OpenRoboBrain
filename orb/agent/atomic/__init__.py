"""
第三级：子能力Agent（执行层）

原子能力执行单元，每个Agent专注于单一能力。

分类：
- vision: 视觉类Agent
- audio: 音频类Agent
- cognitive: 认知类Agent
- action: 动作类Agent
"""

from orb.agent.atomic.base_atomic import AtomicAgent

__all__ = ["AtomicAgent"]
