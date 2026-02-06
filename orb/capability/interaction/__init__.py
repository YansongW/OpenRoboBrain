"""
交互能力

包含：
- 对话管理（DialogueManager）: 自由推理式意图理解
- 语音交互
- 手势交互
- 表情表达
等
"""

from orb.capability.interaction.dialogue import (
    DialogueManager,
    Understanding,
    DialogueContext,
    Turn,
)

__all__ = ["DialogueManager", "Understanding", "DialogueContext", "Turn"]
