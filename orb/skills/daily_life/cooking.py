"""
烹饪技能

实现烹饪相关的技能，包括准备食材、烹调、摆盘等。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from orb.skills.base import (
    BaseSkill,
    SkillCategory,
    SkillContext,
    SkillResult,
    SkillState,
)


class CookingMethod(Enum):
    """烹饪方式"""
    STIR_FRY = "stir_fry"       # 炒
    STEAM = "steam"             # 蒸
    BOIL = "boil"               # 煮
    BRAISE = "braise"           # 炖/焖
    DEEP_FRY = "deep_fry"       # 炸
    ROAST = "roast"             # 烤
    GRILL = "grill"             # 烧烤
    RAW = "raw"                 # 生食/凉拌


@dataclass
class Recipe:
    """菜谱"""
    name: str
    name_cn: str
    ingredients: List[str]
    cooking_method: CookingMethod
    steps: List[str]
    duration_minutes: int
    difficulty: int  # 1-5


class CookingSkill(BaseSkill):
    """
    烹饪技能
    
    能够根据菜谱或指令完成烹饪任务。
    """
    
    def __init__(
        self,
        action_manager: Optional[Any] = None,
        **kwargs: Any,
    ):
        super().__init__(
            name="cooking",
            name_cn="烹饪",
            category=SkillCategory.DAILY_LIFE,
            description="根据菜谱或指令完成烹饪任务，包括食材准备、烹调和摆盘",
            action_manager=action_manager,
        )
        self._current_recipe: Optional[Recipe] = None
        self._current_step: int = 0
        
    def get_required_actions(self) -> List[str]:
        """获取烹饪技能所需的原子动作"""
        return [
            # 移动动作
            "locomotion.upright_walk",
            # 操作动作
            "manipulation.grasp",
            "manipulation.release",
            "manipulation.push",
            "manipulation.pull",
            "manipulation.pour",
            "manipulation.stir",
            "manipulation.cut",
            "manipulation.flip",
            # 感知动作
            "perception.observe",
            "perception.smell",
        ]
        
    async def execute(self, context: SkillContext) -> SkillResult:
        """
        执行烹饪技能
        
        Args:
            context: 执行上下文，包含:
                - recipe: 菜谱信息（可选）
                - dish_name: 菜品名称（如果没有菜谱）
                - ingredients: 可用食材列表
        """
        params = context.parameters
        actions_executed = []
        
        try:
            # 1. 准备阶段 - 获取菜谱
            recipe = params.get("recipe")
            if not recipe and params.get("dish_name"):
                recipe = self._get_default_recipe(params["dish_name"])
                
            if not recipe:
                return SkillResult(
                    success=False,
                    state=SkillState.FAILED,
                    error_message="未提供菜谱或菜品名称",
                    started_at=context.started_at,
                )
                
            self._current_recipe = recipe
            self.logger.info(f"开始烹饪: {recipe.name_cn}")
            
            # 2. 准备食材
            actions_executed.append("准备食材")
            await self._prepare_ingredients(recipe.ingredients)
            
            # 3. 执行烹饪步骤
            for i, step in enumerate(recipe.steps):
                self._current_step = i + 1
                self.logger.info(f"步骤 {i+1}/{len(recipe.steps)}: {step}")
                actions_executed.append(f"步骤{i+1}: {step}")
                await self._execute_step(step, recipe.cooking_method)
                
            # 4. 摆盘
            actions_executed.append("摆盘完成")
            await self._plate_dish()
            
            return SkillResult(
                success=True,
                state=SkillState.COMPLETED,
                result_data={
                    "dish_name": recipe.name_cn,
                    "cooking_method": recipe.cooking_method.value,
                    "steps_completed": len(recipe.steps),
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
            
    async def _prepare_ingredients(self, ingredients: List[str]) -> None:
        """准备食材"""
        for ingredient in ingredients:
            self.logger.debug(f"准备食材: {ingredient}")
            # 这里会调用原子动作：移动、抓取、放置等
            
    async def _execute_step(self, step: str, method: CookingMethod) -> None:
        """执行烹饪步骤"""
        # 根据烹饪方式和步骤描述，调用相应的原子动作
        self.logger.debug(f"执行: {step}")
        
    async def _plate_dish(self) -> None:
        """摆盘"""
        self.logger.debug("摆盘中...")
        
    def _get_default_recipe(self, dish_name: str) -> Optional[Recipe]:
        """获取默认菜谱"""
        # 预定义的简单菜谱
        recipes = {
            "炒蛋": Recipe(
                name="scrambled_eggs",
                name_cn="炒蛋",
                ingredients=["鸡蛋", "油", "盐"],
                cooking_method=CookingMethod.STIR_FRY,
                steps=["打蛋", "热锅加油", "倒入蛋液", "翻炒至凝固", "加盐调味"],
                duration_minutes=5,
                difficulty=1,
            ),
            "番茄炒蛋": Recipe(
                name="tomato_eggs",
                name_cn="番茄炒蛋",
                ingredients=["鸡蛋", "番茄", "油", "盐", "糖"],
                cooking_method=CookingMethod.STIR_FRY,
                steps=[
                    "番茄切块",
                    "打蛋",
                    "热锅加油炒蛋",
                    "盛出备用",
                    "炒番茄出汁",
                    "加入炒好的蛋",
                    "加盐糖调味",
                ],
                duration_minutes=10,
                difficulty=2,
            ),
        }
        return recipes.get(dish_name)
