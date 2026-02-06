"""
社交技能 (Social Skills)

包含各种社交相关的技能，如对话、情感识别等。
"""

from orb.skills.social.conversation import ConversationSkill
from orb.skills.social.emotion import EmotionRecognitionSkill

__all__ = [
    "ConversationSkill",
    "EmotionRecognitionSkill",
]
