"""
对话技能

实现对话相关的能力，包括日常对话、问答、指令理解等。
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


class ConversationType(Enum):
    """对话类型"""
    CASUAL = "casual"               # 日常闲聊
    TASK_ORIENTED = "task_oriented" # 任务导向
    QUESTION_ANSWER = "qa"          # 问答
    INSTRUCTION = "instruction"     # 指令理解
    EMOTIONAL = "emotional"         # 情感交流


class ConversationSkill(BaseSkill):
    """
    对话技能
    
    能够进行各种类型的对话交流。
    """
    
    def __init__(
        self,
        action_manager: Optional[Any] = None,
        **kwargs: Any,
    ):
        super().__init__(
            name="conversation",
            name_cn="对话",
            category=SkillCategory.SOCIAL,
            description="进行各种类型的对话交流，包括日常对话、问答、指令理解等",
            action_manager=action_manager,
        )
        self._conversation_history: List[Dict[str, str]] = []
        
    def get_required_actions(self) -> List[str]:
        """获取对话技能所需的原子动作"""
        return [
            # 语言原子动作
            "language.listen",
            "language.speak",
            "language.understand",
            "language.generate",
            # 感知动作
            "perception.observe_person",
            "perception.track_gaze",
            # 表达动作
            "expression.gesture",
            "expression.nod",
        ]
        
    async def execute(self, context: SkillContext) -> SkillResult:
        """
        执行对话技能
        
        Args:
            context: 执行上下文，包含:
                - input_text: 输入文本
                - conversation_type: 对话类型
                - context_info: 上下文信息
        """
        params = context.parameters
        actions_executed = []
        
        try:
            input_text = params.get("input_text", "")
            conv_type = params.get("conversation_type", ConversationType.CASUAL)
            context_info = params.get("context_info", {})
            
            if isinstance(conv_type, str):
                conv_type = ConversationType(conv_type)
                
            self.logger.info(
                f"对话交流: 类型={conv_type.value}, "
                f"输入={input_text[:30]}..."
            )
            
            # 1. 理解输入
            actions_executed.append("理解输入")
            understanding = await self._understand_input(input_text, conv_type)
            
            # 2. 生成回复
            actions_executed.append("生成回复")
            response = await self._generate_response(
                understanding,
                conv_type,
                context_info,
            )
            
            # 3. 记录对话历史
            self._conversation_history.append({
                "role": "user",
                "content": input_text,
            })
            self._conversation_history.append({
                "role": "assistant",
                "content": response,
            })
            
            return SkillResult(
                success=True,
                state=SkillState.COMPLETED,
                result_data={
                    "response": response,
                    "conversation_type": conv_type.value,
                    "understanding": understanding,
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
            
    async def _understand_input(
        self,
        input_text: str,
        conv_type: ConversationType,
    ) -> Dict[str, Any]:
        """理解输入"""
        return {
            "text": input_text,
            "intent": "general",
            "entities": [],
            "sentiment": "neutral",
        }
        
    async def _generate_response(
        self,
        understanding: Dict[str, Any],
        conv_type: ConversationType,
        context_info: Dict[str, Any],
    ) -> str:
        """生成回复"""
        # 简化实现，实际需要接入LLM
        return "我理解了，让我来帮助你。"
        
    def clear_history(self) -> None:
        """清空对话历史"""
        self._conversation_history.clear()
        
    def get_history(self) -> List[Dict[str, str]]:
        """获取对话历史"""
        return self._conversation_history.copy()
