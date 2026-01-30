"""
第一级：Super Agent（管理层）

负责管理所有Agent的生命周期：
- Agent注册
- Agent删除
- Agent修改
- Agent监控
- 资源分配
"""

from kaibrain.agent.super.super_agent import SuperAgent
from kaibrain.agent.super.registry import AgentRegistry
from kaibrain.agent.super.lifecycle import LifecycleManager

__all__ = ["SuperAgent", "AgentRegistry", "LifecycleManager"]
