"""
攀爬技能

实现攀爬相关的能力，包括爬楼梯、攀岩、爬树等。
"""

from __future__ import annotations

from enum import Enum
from typing import Any, List, Optional

from orb.skills.base import (
    BaseSkill,
    SkillCategory,
    SkillContext,
    SkillResult,
    SkillState,
)


class ClimbingType(Enum):
    """攀爬类型"""
    STAIRS = "stairs"           # 爬楼梯
    LADDER = "ladder"           # 爬梯子
    ROCK = "rock"               # 攀岩
    TREE = "tree"               # 爬树
    ROPE = "rope"               # 爬绳
    WALL = "wall"               # 攀墙


class ClimbingSkill(BaseSkill):
    """
    攀爬技能
    
    能够完成各种攀爬任务。
    """
    
    def __init__(
        self,
        action_manager: Optional[Any] = None,
        **kwargs: Any,
    ):
        super().__init__(
            name="climbing",
            name_cn="攀爬",
            category=SkillCategory.MOVEMENT,
            description="完成各种攀爬任务，包括爬楼梯、攀岩、爬树等",
            action_manager=action_manager,
        )
        
    def get_required_actions(self) -> List[str]:
        """获取攀爬技能所需的原子动作"""
        return [
            # 攀爬原子动作
            "climbing.grip",
            "climbing.pull_up",
            "climbing.step_up",
            "climbing.find_hold",
            "climbing.rest",
            # 平衡动作
            "balance.maintain",
            "balance.shift_weight",
            # 感知动作
            "perception.assess_surface",
            "perception.find_route",
        ]
        
    async def execute(self, context: SkillContext) -> SkillResult:
        """
        执行攀爬技能
        
        Args:
            context: 执行上下文，包含:
                - climbing_type: 攀爬类型
                - height: 目标高度
                - safety_level: 安全级别
        """
        params = context.parameters
        actions_executed = []
        
        try:
            climbing_type = params.get("climbing_type", ClimbingType.STAIRS)
            height = params.get("height", 3)  # 米
            safety_level = params.get("safety_level", "normal")
            
            if isinstance(climbing_type, str):
                climbing_type = ClimbingType(climbing_type)
                
            self.logger.info(
                f"开始攀爬: 类型={climbing_type.value}, "
                f"高度={height}米"
            )
            
            # 1. 评估路线
            actions_executed.append("评估攀爬路线")
            route = await self._assess_route(climbing_type, height)
            
            # 2. 准备
            actions_executed.append("攀爬准备")
            await self._prepare(climbing_type, safety_level)
            
            # 3. 执行攀爬
            height_climbed = 0.0
            for step in route:
                actions_executed.append(f"攀爬: {step}")
                height_climbed += await self._climb_step(step)
                
            return SkillResult(
                success=True,
                state=SkillState.COMPLETED,
                result_data={
                    "climbing_type": climbing_type.value,
                    "height_climbed": height_climbed,
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
            
    async def _assess_route(
        self,
        climbing_type: ClimbingType,
        height: float,
    ) -> List[str]:
        """评估攀爬路线"""
        steps_count = int(height / 0.3)  # 每步约30cm
        return [f"步骤{i+1}" for i in range(steps_count)]
        
    async def _prepare(
        self,
        climbing_type: ClimbingType,
        safety_level: str,
    ) -> None:
        """攀爬准备"""
        pass
        
    async def _climb_step(self, step: str) -> float:
        """执行一步攀爬"""
        return 0.3  # 返回攀爬高度
