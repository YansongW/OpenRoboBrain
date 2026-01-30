"""
整理技能

实现物品整理相关的技能，包括收纳、归类、摆放等。
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from kaibrain.skills.base import (
    BaseSkill,
    SkillCategory,
    SkillContext,
    SkillResult,
    SkillState,
)


class OrganizingType(Enum):
    """整理类型"""
    SORT = "sort"               # 分类
    STORE = "store"             # 收纳
    ARRANGE = "arrange"         # 排列
    FOLD = "fold"               # 折叠
    STACK = "stack"             # 堆叠
    HANG = "hang"               # 悬挂


class OrganizingSkill(BaseSkill):
    """
    整理技能
    
    能够完成物品的整理、收纳和归类。
    """
    
    def __init__(
        self,
        action_manager: Optional[Any] = None,
        **kwargs: Any,
    ):
        super().__init__(
            name="organizing",
            name_cn="整理",
            category=SkillCategory.DAILY_LIFE,
            description="完成物品的整理、收纳和归类工作",
            action_manager=action_manager,
        )
        
    def get_required_actions(self) -> List[str]:
        """获取整理技能所需的原子动作"""
        return [
            # 移动动作
            "locomotion.upright_walk",
            "locomotion.crouch",
            "locomotion.reach_high",
            # 操作动作
            "manipulation.grasp",
            "manipulation.release",
            "manipulation.place",
            "manipulation.fold",
            "manipulation.push",
            # 感知动作
            "perception.observe",
            "perception.identify_object",
        ]
        
    async def execute(self, context: SkillContext) -> SkillResult:
        """
        执行整理技能
        
        Args:
            context: 执行上下文，包含:
                - organizing_type: 整理类型
                - target_items: 目标物品列表
                - destination: 目标位置
        """
        params = context.parameters
        actions_executed = []
        
        try:
            organizing_type = params.get("organizing_type", OrganizingType.ARRANGE)
            target_items = params.get("target_items", [])
            destination = params.get("destination", "指定位置")
            
            if isinstance(organizing_type, str):
                organizing_type = OrganizingType(organizing_type)
                
            self.logger.info(
                f"开始整理: {organizing_type.value}, "
                f"物品数量: {len(target_items)}"
            )
            
            # 1. 识别物品
            actions_executed.append("识别物品")
            items = await self._identify_items(target_items)
            
            # 2. 分类
            actions_executed.append("物品分类")
            categories = await self._categorize_items(items)
            
            # 3. 执行整理
            organized_count = 0
            for category, category_items in categories.items():
                for item in category_items:
                    actions_executed.append(f"整理: {item}")
                    await self._organize_item(item, organizing_type, destination)
                    organized_count += 1
                    
            return SkillResult(
                success=True,
                state=SkillState.COMPLETED,
                result_data={
                    "organizing_type": organizing_type.value,
                    "items_organized": organized_count,
                    "destination": destination,
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
            
    async def _identify_items(self, items: List[str]) -> List[str]:
        """识别物品"""
        if items:
            return items
        # 如果没有指定，模拟扫描发现物品
        return ["书籍", "衣物", "杂物"]
        
    async def _categorize_items(self, items: List[str]) -> Dict[str, List[str]]:
        """物品分类"""
        # 简单的分类逻辑
        categories: Dict[str, List[str]] = {}
        for item in items:
            category = self._get_item_category(item)
            if category not in categories:
                categories[category] = []
            categories[category].append(item)
        return categories
        
    def _get_item_category(self, item: str) -> str:
        """获取物品分类"""
        category_map = {
            "书籍": "阅读类",
            "衣物": "穿戴类",
            "杂物": "其他",
        }
        for keyword, category in category_map.items():
            if keyword in item:
                return category
        return "其他"
        
    async def _organize_item(
        self,
        item: str,
        organizing_type: OrganizingType,
        destination: str,
    ) -> None:
        """整理单个物品"""
        self.logger.debug(
            f"整理 {item} -> {destination}, "
            f"方式: {organizing_type.value}"
        )
