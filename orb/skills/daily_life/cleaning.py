"""
清洁技能

实现清洁相关的技能，包括打扫、擦拭、吸尘等。
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from orb.skills.base import (
    BaseSkill,
    SkillCategory,
    SkillContext,
    SkillResult,
    SkillState,
)


class CleaningType(Enum):
    """清洁类型"""
    SWEEP = "sweep"             # 扫地
    MOP = "mop"                 # 拖地
    VACUUM = "vacuum"           # 吸尘
    WIPE = "wipe"               # 擦拭
    DUST = "dust"               # 除尘
    WASH = "wash"               # 清洗
    ORGANIZE = "organize"       # 整理


class CleaningSkill(BaseSkill):
    """
    清洁技能
    
    能够完成各种清洁任务。
    """
    
    def __init__(
        self,
        action_manager: Optional[Any] = None,
        **kwargs: Any,
    ):
        super().__init__(
            name="cleaning",
            name_cn="清洁",
            category=SkillCategory.DAILY_LIFE,
            description="完成各种清洁任务，包括打扫、擦拭、吸尘等",
            action_manager=action_manager,
        )
        
    def get_required_actions(self) -> List[str]:
        """获取清洁技能所需的原子动作"""
        return [
            # 移动动作
            "locomotion.upright_walk",
            "locomotion.crouch",
            # 操作动作
            "manipulation.grasp",
            "manipulation.release",
            "manipulation.push",
            "manipulation.pull",
            "manipulation.wipe",
            "manipulation.spray",
            # 感知动作
            "perception.observe",
            "perception.scan_area",
        ]
        
    async def execute(self, context: SkillContext) -> SkillResult:
        """
        执行清洁技能
        
        Args:
            context: 执行上下文，包含:
                - cleaning_type: 清洁类型
                - target_area: 目标区域
                - thoroughness: 彻底程度 (1-5)
        """
        params = context.parameters
        actions_executed = []
        
        try:
            cleaning_type = params.get("cleaning_type", CleaningType.WIPE)
            target_area = params.get("target_area", "房间")
            thoroughness = params.get("thoroughness", 3)
            
            if isinstance(cleaning_type, str):
                cleaning_type = CleaningType(cleaning_type)
                
            self.logger.info(
                f"开始清洁: {target_area}, "
                f"类型: {cleaning_type.value}, "
                f"彻底程度: {thoroughness}"
            )
            
            # 1. 扫描区域
            actions_executed.append("扫描目标区域")
            dirty_spots = await self._scan_area(target_area)
            
            # 2. 准备清洁工具
            actions_executed.append("准备清洁工具")
            await self._prepare_tools(cleaning_type)
            
            # 3. 执行清洁
            cleaned_spots = 0
            for spot in dirty_spots:
                actions_executed.append(f"清洁: {spot}")
                await self._clean_spot(spot, cleaning_type)
                cleaned_spots += 1
                
            # 4. 收尾
            actions_executed.append("收纳工具")
            await self._cleanup()
            
            return SkillResult(
                success=True,
                state=SkillState.COMPLETED,
                result_data={
                    "area_cleaned": target_area,
                    "cleaning_type": cleaning_type.value,
                    "spots_cleaned": cleaned_spots,
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
            
    async def _scan_area(self, area: str) -> List[str]:
        """扫描区域识别需要清洁的地方"""
        # 模拟返回需要清洁的点位
        return [f"{area}-区域1", f"{area}-区域2", f"{area}-区域3"]
        
    async def _prepare_tools(self, cleaning_type: CleaningType) -> None:
        """准备清洁工具"""
        tool_map = {
            CleaningType.SWEEP: "扫把",
            CleaningType.MOP: "拖把",
            CleaningType.VACUUM: "吸尘器",
            CleaningType.WIPE: "抹布",
            CleaningType.DUST: "掸子",
            CleaningType.WASH: "清洁剂",
        }
        tool = tool_map.get(cleaning_type, "清洁工具")
        self.logger.debug(f"准备工具: {tool}")
        
    async def _clean_spot(self, spot: str, cleaning_type: CleaningType) -> None:
        """清洁指定位置"""
        self.logger.debug(f"清洁 {spot}，方式: {cleaning_type.value}")
        
    async def _cleanup(self) -> None:
        """收尾工作"""
        self.logger.debug("收纳清洁工具")
