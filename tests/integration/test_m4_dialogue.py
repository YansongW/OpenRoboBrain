"""
M4 自然对话系统集成测试

测试场景:
1. 纯闲聊 → 自然回复，无 ROS2 命令
2. 直接指令 → 自然回复 + ROS2 命令 (OA 编排)
3. 隐含意图 → 推理出行动
4. 情感表达 → 无命令
5. DialogueManager 思维链完整性
6. Understanding 数据结构正确性
"""

import asyncio
import pytest
import sys
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass

# 确保项目根目录在 path 中
sys.path.insert(0, ".")


class TestDialogueManager:
    """DialogueManager 单元测试"""

    def _create_mock_llm(self, response_content: str):
        """创建 mock LLM"""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = response_content
        mock_llm.chat = AsyncMock(return_value=mock_response)
        return mock_llm

    @pytest.mark.asyncio
    async def test_understand_chat(self):
        """闲聊: 不需要行动"""
        from orb.capability.interaction.dialogue import DialogueManager

        llm = self._create_mock_llm(
            '我来分析一下用户说的话。\n'
            '用户在打招呼，这是一个友好的闲聊。不需要任何物理动作。\n'
            '```json\n'
            '{"summary": "用户在打招呼", "requires_action": false, '
            '"action_description": "", '
            '"suggested_response": "你好！今天有什么我可以帮你的吗？"}\n'
            '```'
        )
        dm = DialogueManager(llm=llm)

        understanding = await dm.understand("你好啊", trace_id="test-001")

        assert understanding.raw_input == "你好啊"
        assert understanding.requires_action is False
        assert understanding.suggested_response != ""
        assert understanding.reasoning != ""
        assert understanding.trace_id == "test-001"
        assert understanding.summary != ""

    @pytest.mark.asyncio
    async def test_understand_command(self):
        """直接指令: 需要行动"""
        from orb.capability.interaction.dialogue import DialogueManager

        llm = self._create_mock_llm(
            '用户说"向前走"，这是一个明确的移动指令。\n'
            '需要机器人执行向前行走的物理动作。\n'
            '```json\n'
            '{"summary": "用户要求向前走", "requires_action": true, '
            '"action_description": "向前行走", '
            '"suggested_response": "好的，我现在开始向前走。"}\n'
            '```'
        )
        dm = DialogueManager(llm=llm)

        understanding = await dm.understand("向前走", trace_id="test-002")

        assert understanding.requires_action is True
        assert understanding.action_description == "向前行走"
        assert understanding.suggested_response != ""

    @pytest.mark.asyncio
    async def test_understand_implicit_intent(self):
        """隐含意图: 推理出行动"""
        from orb.capability.interaction.dialogue import DialogueManager

        llm = self._create_mock_llm(
            '用户说"这里好暗"。分析：用户感到环境光线不足，暗示需要改善照明。\n'
            '作为机器人，我应该帮他开灯。这需要物理动作。\n'
            '```json\n'
            '{"summary": "用户觉得暗，需要开灯", "requires_action": true, '
            '"action_description": "开灯改善照明", '
            '"suggested_response": "我注意到这里光线不太好，我来帮你开灯。"}\n'
            '```'
        )
        dm = DialogueManager(llm=llm)

        understanding = await dm.understand("这里好暗", trace_id="test-003")

        assert understanding.requires_action is True
        assert "灯" in understanding.action_description or "照明" in understanding.action_description

    @pytest.mark.asyncio
    async def test_understand_emotion(self):
        """情感表达: 不需要行动"""
        from orb.capability.interaction.dialogue import DialogueManager

        llm = self._create_mock_llm(
            '用户在表达不满情绪。我应该表示歉意，不需要物理动作。\n'
            '```json\n'
            '{"summary": "用户表达不满", "requires_action": false, '
            '"action_description": "", '
            '"suggested_response": "非常抱歉给你带来了不好的体验，请告诉我怎样才能做得更好。"}\n'
            '```'
        )
        dm = DialogueManager(llm=llm)

        understanding = await dm.understand("你真笨", trace_id="test-004")

        assert understanding.requires_action is False

    @pytest.mark.asyncio
    async def test_understanding_log_dict(self):
        """Understanding.to_log_dict() 完整性"""
        from orb.capability.interaction.dialogue import Understanding

        u = Understanding(
            raw_input="测试输入",
            reasoning="这是完整的推理过程...",
            summary="测试摘要",
            requires_action=True,
            action_description="测试动作",
            suggested_response="测试回复",
            trace_id="trace-test",
            llm_time_ms=123.4,
        )

        log_dict = u.to_log_dict()

        assert log_dict["trace_id"] == "trace-test"
        assert log_dict["requires_action"] is True
        assert log_dict["llm_time_ms"] == 123.4
        assert "reasoning_length" in log_dict

    @pytest.mark.asyncio
    async def test_context_history_maintained(self):
        """对话上下文历史维护"""
        from orb.capability.interaction.dialogue import DialogueManager

        llm = self._create_mock_llm(
            '```json\n'
            '{"summary": "test", "requires_action": false, '
            '"action_description": "", "suggested_response": "ok"}\n'
            '```'
        )
        dm = DialogueManager(llm=llm)

        await dm.understand("第一句话", trace_id="t1")
        await dm.understand("第二句话", trace_id="t2")

        assert len(dm.context.history) == 2
        assert dm.context.history[0].content == "第一句话"
        assert dm.context.history[1].content == "第二句话"

    @pytest.mark.asyncio
    async def test_llm_failure_graceful(self):
        """LLM 调用失败时的优雅降级"""
        from orb.capability.interaction.dialogue import DialogueManager

        llm = MagicMock()
        llm.chat = AsyncMock(side_effect=Exception("LLM 不可用"))
        dm = DialogueManager(llm=llm)

        understanding = await dm.understand("你好", trace_id="test-err")

        assert understanding.requires_action is False
        assert "抱歉" in understanding.suggested_response
        assert "LLM" in understanding.reasoning

    @pytest.mark.asyncio
    async def test_json_extraction_mixed_format(self):
        """混合格式输出的 JSON 提取"""
        from orb.capability.interaction.dialogue import DialogueManager

        llm = self._create_mock_llm(
            '让我想想用户说了什么。\n\n'
            '用户想让我去厨房，这是一个导航指令。\n\n'
            '{"summary": "去厨房", "requires_action": true, '
            '"action_description": "导航到厨房", '
            '"suggested_response": "好的，我这就去厨房。"}'
        )
        dm = DialogueManager(llm=llm)

        understanding = await dm.understand("去厨房", trace_id="test-mix")

        assert understanding.requires_action is True
        assert understanding.summary == "去厨房"


class TestOrchestratorIntegration:
    """OrchestratorAgent 集成测试"""

    @pytest.mark.asyncio
    async def test_execute_understanding(self):
        """OA 接收 Understanding 并编排执行"""
        from orb.capability.interaction.dialogue import Understanding
        from orb.agent.orchestrator.orchestrator import OrchestratorAgent

        understanding = Understanding(
            raw_input="向前走",
            reasoning="用户要求机器人向前移动",
            summary="向前行走",
            requires_action=True,
            action_description="向前行走",
            suggested_response="好的",
            trace_id="test-oa-001",
        )

        oa = OrchestratorAgent(name="TestOA")
        result = await oa.execute_understanding(understanding, trace_id="test-oa-001")

        # OA 应该成功执行（即使是规则分解 fallback）
        assert result is not None
        assert isinstance(result.ros2_commands, list)
