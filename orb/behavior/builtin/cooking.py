"""
烹饪行为

组合感知、知识管理、任务编排等能力完成烹饪任务。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from orb.behavior.base import (
    Behavior,
    BehaviorConfig,
    BehaviorContext,
)


class CookingBehavior(Behavior):
    """
    烹饪行为
    
    能力组合：
    - 感知理解：识别食材
    - 知识管理：检索菜谱
    - 认知推理：规划烹饪步骤
    - 任务编排：协调执行
    - 通过 Bridge 发送指令给小脑控制执行器
    """
    
    # 烹饪相关关键词
    KEYWORDS = [
        "做菜", "烹饪", "炒", "煮", "蒸", "烤", "煎",
        "cook", "cooking", "make food", "prepare meal",
        "番茄", "鸡蛋", "肉", "蔬菜", "米饭", "面条",
    ]
    
    def __init__(self):
        config = BehaviorConfig(
            name="cooking",
            description="烹饪行为 - 完成烹饪任务的复合行为",
            version="1.0.0",
            required_capabilities=[
                "perception",      # 感知理解
                "knowledge",       # 知识管理
                "reasoning",       # 认知推理
                "orchestration",   # 任务编排
            ],
            tags=["daily_life", "cooking", "food"],
            timeout_seconds=600.0,  # 烹饪可能需要较长时间
        )
        super().__init__(config)
    
    def can_handle(self, user_input: str) -> float:
        """评估是否可以处理"""
        input_lower = user_input.lower()
        
        # 计算匹配的关键词数量
        matches = sum(1 for kw in self.KEYWORDS if kw in input_lower)
        
        if matches == 0:
            return 0.0
        elif matches == 1:
            return 0.5
        elif matches == 2:
            return 0.7
        else:
            return 0.9
    
    async def execute(self, context: BehaviorContext) -> Dict[str, Any]:
        """
        执行烹饪行为
        
        步骤：
        1. 解析用户需求（想做什么菜）
        2. 识别可用食材（感知）
        3. 检索菜谱（知识）
        4. 规划烹饪步骤（推理）
        5. 执行烹饪（编排 + 小脑控制）
        """
        user_input = context.user_input
        
        # 如果匹配到工作流，可以复用已有经验
        if context.workflow_matched:
            self.logger.info("复用已有烹饪工作流")
            return await self._execute_from_workflow(context)
        
        # 否则执行完整流程
        result = {
            "task": "cooking",
            "steps": [],
            "status": "completed",
        }
        
        # 步骤1: 解析需求
        dish_name = self._extract_dish_name(user_input)
        result["dish"] = dish_name
        result["steps"].append({
            "step": 1,
            "action": "parse_request",
            "result": f"识别到目标菜品: {dish_name}",
        })
        
        # 步骤2: 识别食材（模拟）
        ingredients = self._identify_ingredients(dish_name)
        result["ingredients"] = ingredients
        result["steps"].append({
            "step": 2,
            "action": "identify_ingredients",
            "capability": "perception",
            "result": f"识别到食材: {', '.join(ingredients)}",
        })
        
        # 步骤3: 检索菜谱（模拟）
        recipe = self._get_recipe(dish_name)
        result["recipe"] = recipe
        result["steps"].append({
            "step": 3,
            "action": "retrieve_recipe",
            "capability": "knowledge",
            "result": f"获取菜谱: {len(recipe)} 步",
        })
        
        # 步骤4: 规划执行
        plan = self._plan_execution(recipe, context.parameters)
        result["plan"] = plan
        result["steps"].append({
            "step": 4,
            "action": "plan_execution",
            "capability": "reasoning",
            "result": f"规划完成: {len(plan)} 个动作",
        })
        
        # 步骤5: 执行（这里应该通过 Bridge 发送给小脑）
        # 在实际实现中，会调用 BrainCerebellumBridge
        result["steps"].append({
            "step": 5,
            "action": "execute_cooking",
            "capability": "orchestration",
            "result": "烹饪完成（模拟）",
            "note": "实际执行需要通过 Bridge 发送指令给小脑",
        })
        
        return result
    
    async def _execute_from_workflow(
        self,
        context: BehaviorContext,
    ) -> Dict[str, Any]:
        """从工作流记忆执行"""
        # 复用已有的成功经验
        return {
            "task": "cooking",
            "workflow_reused": True,
            "workflow_id": context.workflow_id,
            "status": "completed",
            "message": "使用已验证的工作流执行",
        }
    
    def _extract_dish_name(self, user_input: str) -> str:
        """提取菜品名称"""
        # 简单实现：提取"做"后面的词
        patterns = [
            r"做[一个]?(.+?)(?:吧|呢|$)",
            r"烹饪(.+?)(?:吧|呢|$)",
            r"make\s+(.+?)(?:\s|$)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, user_input)
            if match:
                return match.group(1).strip()
        
        return "未知菜品"
    
    def _identify_ingredients(self, dish_name: str) -> List[str]:
        """识别食材（模拟）"""
        # 简单的映射
        ingredient_map = {
            "番茄炒蛋": ["番茄", "鸡蛋", "葱", "盐", "油"],
            "红烧肉": ["五花肉", "酱油", "糖", "姜", "八角"],
            "炒青菜": ["青菜", "蒜", "盐", "油"],
        }
        
        for dish, ingredients in ingredient_map.items():
            if dish in dish_name:
                return ingredients
        
        return ["未知食材"]
    
    def _get_recipe(self, dish_name: str) -> List[str]:
        """获取菜谱（模拟）"""
        recipes = {
            "番茄炒蛋": [
                "番茄切块",
                "鸡蛋打散",
                "热锅倒油",
                "炒鸡蛋至凝固",
                "加入番茄翻炒",
                "加盐调味",
                "出锅",
            ],
        }
        
        for dish, steps in recipes.items():
            if dish in dish_name:
                return steps
        
        return ["准备食材", "加工", "烹饪", "出锅"]
    
    def _plan_execution(
        self,
        recipe: List[str],
        parameters: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """规划执行"""
        return [
            {
                "action": step,
                "estimated_time_seconds": 30,
                "requires_cerebellum": True,
            }
            for step in recipe
        ]
