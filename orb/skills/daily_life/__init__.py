"""
日常生活技能 (Daily Life Skills)

包含日常生活中需要的各种技能，如烹饪、清洁、整理等。
"""

from orb.skills.daily_life.cooking import CookingSkill
from orb.skills.daily_life.cleaning import CleaningSkill
from orb.skills.daily_life.organizing import OrganizingSkill

__all__ = [
    "CookingSkill",
    "CleaningSkill",
    "OrganizingSkill",
]
