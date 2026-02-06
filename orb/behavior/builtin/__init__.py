"""
内置行为

提供一些常用的预定义行为。
"""

from orb.behavior.builtin.cooking import CookingBehavior
from orb.behavior.builtin.cleaning import CleaningBehavior
from orb.behavior.builtin.general import GeneralBehavior

__all__ = [
    "CookingBehavior",
    "CleaningBehavior",
    "GeneralBehavior",
]
