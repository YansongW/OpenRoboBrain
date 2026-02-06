"""
行为层 (Behavior Layer)

行为层是能力层之上的复合行为模式层，实现经验复用和避免重复推理。

核心概念：
- 行为 (Behavior): 多个原子能力的组合，代表可复用的复杂行为模式
- 行为注册表 (BehaviorRegistry): 管理所有可用行为
- 行为执行器 (BehaviorExecutor): 执行行为，关联工作流记忆

设计原则：
1. 经验复用：行为关联到显性数据中的工作流记忆，成功经验可直接复用
2. 避免长程推理：复杂任务直接调用已学会的行为，不需要每次从零推理
3. 减少出错：已验证的行为比实时推理更可靠
4. 降低延迟：跳过规划过程，直接执行已有的能力组合
"""

from orb.behavior.base import (
    Behavior,
    BehaviorStatus,
    BehaviorResult,
    BehaviorConfig,
    BehaviorContext,
)
from orb.behavior.registry import (
    BehaviorRegistry,
    get_registry,
)
from orb.behavior.executor import (
    BehaviorExecutor,
    create_behavior_executor,
)

__all__ = [
    # 基础
    "Behavior",
    "BehaviorStatus",
    "BehaviorResult",
    "BehaviorConfig",
    "BehaviorContext",
    
    # 注册表
    "BehaviorRegistry",
    "get_registry",
    
    # 执行器
    "BehaviorExecutor",
    "create_behavior_executor",
]
