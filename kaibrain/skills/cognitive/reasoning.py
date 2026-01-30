"""
推理技能

实现推理相关的能力，包括逻辑推理、因果推理、类比推理等。
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


class ReasoningType(Enum):
    """推理类型"""
    DEDUCTIVE = "deductive"     # 演绎推理
    INDUCTIVE = "inductive"     # 归纳推理
    ABDUCTIVE = "abductive"     # 溯因推理
    ANALOGICAL = "analogical"   # 类比推理
    CAUSAL = "causal"           # 因果推理
    SPATIAL = "spatial"         # 空间推理


class ReasoningSkill(BaseSkill):
    """
    推理技能
    
    能够进行各种类型的推理。
    """
    
    def __init__(
        self,
        action_manager: Optional[Any] = None,
        **kwargs: Any,
    ):
        super().__init__(
            name="reasoning",
            name_cn="推理",
            category=SkillCategory.COGNITIVE,
            description="进行各种类型的推理，包括逻辑推理、因果推理等",
            action_manager=action_manager,
        )
        
    def get_required_actions(self) -> List[str]:
        """获取推理技能所需的原子动作"""
        return [
            # 认知原子动作
            "cognitive.analyze",
            "cognitive.compare",
            "cognitive.infer",
            "cognitive.evaluate",
            "cognitive.synthesize",
        ]
        
    async def execute(self, context: SkillContext) -> SkillResult:
        """
        执行推理技能
        
        Args:
            context: 执行上下文，包含:
                - problem: 问题描述
                - reasoning_type: 推理类型
                - premises: 前提条件
                - constraints: 约束条件
        """
        params = context.parameters
        actions_executed = []
        
        try:
            problem = params.get("problem", "")
            reasoning_type = params.get("reasoning_type", ReasoningType.DEDUCTIVE)
            premises = params.get("premises", [])
            constraints = params.get("constraints", [])
            
            if isinstance(reasoning_type, str):
                reasoning_type = ReasoningType(reasoning_type)
                
            self.logger.info(
                f"开始推理: 类型={reasoning_type.value}, "
                f"问题={problem[:50]}..."
            )
            
            # 1. 分析问题
            actions_executed.append("分析问题")
            analysis = await self._analyze_problem(problem, premises)
            
            # 2. 执行推理
            actions_executed.append(f"执行{reasoning_type.value}推理")
            conclusion = await self._reason(
                analysis,
                reasoning_type,
                constraints,
            )
            
            # 3. 验证结论
            actions_executed.append("验证结论")
            is_valid = await self._validate_conclusion(conclusion, premises)
            
            return SkillResult(
                success=True,
                state=SkillState.COMPLETED,
                result_data={
                    "conclusion": conclusion,
                    "reasoning_type": reasoning_type.value,
                    "is_valid": is_valid,
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
            
    async def _analyze_problem(
        self,
        problem: str,
        premises: List[str],
    ) -> Dict[str, Any]:
        """分析问题"""
        return {
            "problem": problem,
            "premises": premises,
            "key_elements": [],
        }
        
    async def _reason(
        self,
        analysis: Dict[str, Any],
        reasoning_type: ReasoningType,
        constraints: List[str],
    ) -> str:
        """执行推理"""
        return "推理结论"
        
    async def _validate_conclusion(
        self,
        conclusion: str,
        premises: List[str],
    ) -> bool:
        """验证结论"""
        return True
