"""
学习技能

实现学习相关的能力，包括模仿学习、强化学习、知识获取等。
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


class LearningMethod(Enum):
    """学习方式"""
    IMITATION = "imitation"             # 模仿学习
    REINFORCEMENT = "reinforcement"     # 强化学习
    OBSERVATION = "observation"         # 观察学习
    INSTRUCTION = "instruction"         # 指导学习
    TRIAL_ERROR = "trial_error"         # 试错学习
    KNOWLEDGE = "knowledge"             # 知识学习


class LearningSkill(BaseSkill):
    """
    学习技能
    
    能够通过多种方式学习新知识和技能。
    """
    
    def __init__(
        self,
        action_manager: Optional[Any] = None,
        **kwargs: Any,
    ):
        super().__init__(
            name="learning",
            name_cn="学习",
            category=SkillCategory.COGNITIVE,
            description="通过多种方式学习新知识和技能",
            action_manager=action_manager,
        )
        self._learned_items: Dict[str, Any] = {}
        
    def get_required_actions(self) -> List[str]:
        """获取学习技能所需的原子动作"""
        return [
            # 认知原子动作
            "cognitive.observe",
            "cognitive.memorize",
            "cognitive.recall",
            "cognitive.associate",
            "cognitive.generalize",
            # 感知动作
            "perception.focus",
            "perception.track",
        ]
        
    async def execute(self, context: SkillContext) -> SkillResult:
        """
        执行学习技能
        
        Args:
            context: 执行上下文，包含:
                - subject: 学习主题
                - method: 学习方式
                - source: 学习来源（示范者、教材等）
        """
        params = context.parameters
        actions_executed = []
        
        try:
            subject = params.get("subject", "新技能")
            method = params.get("method", LearningMethod.OBSERVATION)
            source = params.get("source")
            
            if isinstance(method, str):
                method = LearningMethod(method)
                
            self.logger.info(
                f"开始学习: 主题={subject}, "
                f"方式={method.value}"
            )
            
            # 1. 准备学习
            actions_executed.append("准备学习环境")
            await self._prepare_learning(method, source)
            
            # 2. 执行学习
            actions_executed.append(f"执行{method.value}学习")
            knowledge = await self._learn(subject, method, source)
            
            # 3. 巩固
            actions_executed.append("知识巩固")
            await self._consolidate(subject, knowledge)
            
            # 4. 存储
            self._learned_items[subject] = knowledge
            actions_executed.append("存储学习成果")
            
            return SkillResult(
                success=True,
                state=SkillState.COMPLETED,
                result_data={
                    "subject": subject,
                    "method": method.value,
                    "knowledge_acquired": bool(knowledge),
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
            
    async def _prepare_learning(
        self,
        method: LearningMethod,
        source: Any,
    ) -> None:
        """准备学习"""
        pass
        
    async def _learn(
        self,
        subject: str,
        method: LearningMethod,
        source: Any,
    ) -> Dict[str, Any]:
        """执行学习过程"""
        return {"subject": subject, "learned": True}
        
    async def _consolidate(
        self,
        subject: str,
        knowledge: Dict[str, Any],
    ) -> None:
        """巩固知识"""
        pass
