"""
运动技能 (Movement Skills)

包含各种运动相关的技能，如行进、游泳、攀爬等。
"""

from kaibrain.skills.movement.locomotion import LocomotionSkill
from kaibrain.skills.movement.swimming import SwimmingSkill
from kaibrain.skills.movement.climbing import ClimbingSkill

__all__ = [
    "LocomotionSkill",
    "SwimmingSkill",
    "ClimbingSkill",
]
