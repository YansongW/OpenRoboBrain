"""
游泳技能

实现游泳相关的能力，包括不同泳姿和水中操作。
"""

from __future__ import annotations

from enum import Enum
from typing import Any, List, Optional

from kaibrain.skills.base import (
    BaseSkill,
    SkillCategory,
    SkillContext,
    SkillResult,
    SkillState,
)


class SwimmingStyle(Enum):
    """游泳姿势"""
    FREESTYLE = "freestyle"         # 自由泳
    BREASTSTROKE = "breaststroke"   # 蛙泳
    BACKSTROKE = "backstroke"       # 仰泳
    BUTTERFLY = "butterfly"         # 蝶泳
    FLOATING = "floating"           # 漂浮
    TREADING = "treading"           # 踩水


class SwimmingSkill(BaseSkill):
    """
    游泳技能
    
    能够在水中移动和操作。
    """
    
    def __init__(
        self,
        action_manager: Optional[Any] = None,
        **kwargs: Any,
    ):
        super().__init__(
            name="swimming",
            name_cn="游泳",
            category=SkillCategory.MOVEMENT,
            description="在水中进行各种泳姿的游泳和水中操作",
            action_manager=action_manager,
        )
        
    def get_required_actions(self) -> List[str]:
        """获取游泳技能所需的原子动作"""
        return [
            # 游泳原子动作
            "swimming.arm_stroke",
            "swimming.leg_kick",
            "swimming.breathing",
            "swimming.turn",
            "swimming.dive",
            "swimming.surface",
            # 平衡动作
            "balance.float",
            "balance.tread",
            # 感知动作
            "perception.underwater_vision",
            "perception.depth_sense",
        ]
        
    async def execute(self, context: SkillContext) -> SkillResult:
        """
        执行游泳技能
        
        Args:
            context: 执行上下文，包含:
                - style: 泳姿
                - distance: 游泳距离
                - speed: 速度
        """
        params = context.parameters
        actions_executed = []
        
        try:
            style = params.get("style", SwimmingStyle.BREASTSTROKE)
            distance = params.get("distance", 25)  # 米
            speed = params.get("speed", 0.5)
            
            if isinstance(style, str):
                style = SwimmingStyle(style)
                
            self.logger.info(
                f"开始游泳: 泳姿={style.value}, "
                f"距离={distance}米"
            )
            
            # 1. 入水准备
            actions_executed.append("入水准备")
            await self._prepare_entry()
            
            # 2. 执行游泳
            actions_executed.append(f"开始{style.value}")
            distance_swam = await self._swim(style, distance, speed)
            
            # 3. 完成
            actions_executed.append("游泳完成")
            
            return SkillResult(
                success=True,
                state=SkillState.COMPLETED,
                result_data={
                    "style": style.value,
                    "distance_swam": distance_swam,
                },
                started_at=context.started_at,
                actions_executed=actions_executed,
            )
            
        except Exception as e:
            return SkillResult(
                success=False,
                state=SkillState.FAILED,
                error_message=str(e),
                started_at=context.started_at,
                actions_executed=actions_executed,
            )
            
    async def _prepare_entry(self) -> None:
        """入水准备"""
        pass
        
    async def _swim(
        self,
        style: SwimmingStyle,
        distance: float,
        speed: float,
    ) -> float:
        """执行游泳"""
        return distance
