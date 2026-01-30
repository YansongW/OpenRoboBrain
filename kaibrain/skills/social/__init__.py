"""
社交技能 (Social Skills)

包含各种社交相关的技能，如对话、情感识别等。
"""

from kaibrain.skills.social.conversation import ConversationSkill
from kaibrain.skills.social.emotion import EmotionRecognitionSkill

__all__ = [
    "ConversationSkill",
    "EmotionRecognitionSkill",
]
