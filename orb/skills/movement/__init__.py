"""
运动技能 (Movement Skills)

包含各种运动相关的技能，如行进、游泳、攀爬等。
"""

from orb.skills.movement.locomotion import LocomotionSkill
from orb.skills.movement.swimming import SwimmingSkill
from orb.skills.movement.climbing import ClimbingSkill

__all__ = [
    "LocomotionSkill",
    "SwimmingSkill",
    "ClimbingSkill",
]
