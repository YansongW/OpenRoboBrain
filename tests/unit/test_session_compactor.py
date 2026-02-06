"""
会话压缩器单元测试

覆盖:
- Token 估算
- 自动触发检测
- Session Pruning
- LLM 摘要压缩 (Mock)
- 规则摘要 fallback
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

from orb.agent.infrastructure.session_compactor import (
    SessionCompactor,
    CompactionConfig,
    CompactionResult,
    create_session_compactor,
)
from orb.agent.infrastructure.session_store import (
    SessionMessage,
    MessageRole,
)


# ============== 辅助函数 ==============

def make_msg(role: str, content: str, **kwargs) -> SessionMessage:
    """快速创建测试消息"""
    return SessionMessage(
        role=MessageRole(role),
        content=content,
        **kwargs,
    )


def make_conversation(num_turns: int, content_length: int = 100) -> List[SessionMessage]:
    """创建多轮对话"""
    messages = []
    for i in range(num_turns):
        messages.append(make_msg("user", f"用户消息 {i}: {'测试' * (content_length // 2)}"))
        messages.append(make_msg("assistant", f"助手回复 {i}: {'回复内容' * (content_length // 4)}"))
    return messages


# ============== Token 估算 ==============

class TestTokenEstimation:
    """Token 估算测试"""

    def test_empty_text(self):
        """空文本 = 0 tokens"""
        compactor = SessionCompactor()
        assert compactor.estimate_tokens("") == 0

    def test_english_text(self):
        """英文文本约 4 字符/token"""
        compactor = SessionCompactor()
        text = "Hello world, this is a test."  # 28 chars
        tokens = compactor.estimate_tokens(text)
        assert 5 <= tokens <= 10  # 约 7 tokens

    def test_chinese_text(self):
        """中文文本约 1.5 字符/token"""
        compactor = SessionCompactor()
        text = "你好世界这是测试"  # 8 中文字符
        tokens = compactor.estimate_tokens(text)
        assert 4 <= tokens <= 8  # 约 5 tokens

    def test_messages_tokens(self):
        """消息列表 token 估算"""
        compactor = SessionCompactor()
        messages = [
            make_msg("user", "你好"),
            make_msg("assistant", "你好！有什么可以帮你的？"),
        ]
        tokens = compactor.estimate_messages_tokens(messages)
        assert tokens > 0


# ============== 自动触发检测 ==============

class TestAutoTrigger:
    """自动触发检测测试"""

    def test_should_not_compact_small_session(self):
        """小会话不需要压缩"""
        compactor = SessionCompactor(CompactionConfig(context_window=128000))
        messages = make_conversation(5)  # 10 条消息

        assert compactor.should_compact(messages) is False

    def test_should_compact_large_session(self):
        """大会话需要压缩"""
        compactor = SessionCompactor(CompactionConfig(
            context_window=100,  # 极小的 window
            reserve_tokens_floor=20,
        ))
        messages = make_conversation(20, content_length=200)

        assert compactor.should_compact(messages) is True

    def test_memory_flush_before_compaction(self):
        """memory flush 在 compaction 之前触发"""
        compactor = SessionCompactor(CompactionConfig(
            context_window=200,
            reserve_tokens_floor=50,
            soft_threshold_tokens=30,
        ))
        messages = make_conversation(10, content_length=100)
        tokens = compactor.estimate_messages_tokens(messages)

        # 当 tokens > context_window - reserve - soft_threshold
        # 即 tokens > 200 - 50 - 30 = 120
        if tokens > 120:
            assert compactor.should_memory_flush(messages) is True


# ============== Session Pruning ==============

class TestSessionPruning:
    """Session Pruning 测试"""

    def test_prune_old_tool_results(self):
        """修剪旧的 tool results"""
        compactor = SessionCompactor(CompactionConfig(
            tool_result_max_age_turns=2,
            tool_result_max_chars=50,
        ))

        messages = [
            make_msg("user", "第一轮请求"),
            make_msg("assistant", "调用工具"),
            make_msg("tool", "A" * 200, tool_call_id="c1", tool_name="tool1"),
            make_msg("user", "第二轮请求"),
            make_msg("assistant", "调用工具"),
            make_msg("tool", "B" * 200, tool_call_id="c2", tool_name="tool2"),
            make_msg("user", "第三轮请求"),
            make_msg("assistant", "调用工具"),
            make_msg("tool", "C" * 200, tool_call_id="c3", tool_name="tool3"),
            make_msg("user", "第四轮请求"),
            make_msg("assistant", "回复"),
        ]

        pruned, count = compactor.prune_messages(messages)

        assert len(pruned) == len(messages)  # 不删除，只截断
        # 旧的 tool result 应该被截断
        old_tool = [m for m in pruned if m.role == MessageRole.TOOL and "截断" in m.content]
        assert len(old_tool) > 0

    def test_prune_disabled(self):
        """禁用 pruning"""
        compactor = SessionCompactor(CompactionConfig(prune_old_tool_results=False))
        messages = make_conversation(5)

        pruned, count = compactor.prune_messages(messages)
        assert count == 0

    def test_recent_tool_results_preserved(self):
        """最近的 tool results 不被截断"""
        compactor = SessionCompactor(CompactionConfig(
            tool_result_max_age_turns=2,
            tool_result_max_chars=50,
        ))

        messages = [
            make_msg("user", "请求"),
            make_msg("assistant", "调用工具"),
            make_msg("tool", "X" * 200, tool_call_id="c1"),
            make_msg("user", "最新请求"),
            make_msg("assistant", "回复"),
        ]

        pruned, count = compactor.prune_messages(messages)

        # 只有1轮用户消息在 tool 之后，tool_result_max_age_turns=2，所以不应被截断
        tool_msgs = [m for m in pruned if m.role == MessageRole.TOOL]
        for tm in tool_msgs:
            assert "截断" not in tm.content


# ============== LLM 摘要压缩 ==============

class TestCompaction:
    """LLM 摘要压缩测试"""

    @pytest.mark.asyncio
    async def test_compact_with_mock_llm(self):
        """使用 Mock LLM 进行压缩"""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "## 对话摘要\n- 用户请求了导航到厨房\n- 系统成功执行"
        mock_llm.chat = AsyncMock(return_value=mock_response)

        compactor = SessionCompactor(llm=mock_llm)
        messages = make_conversation(10)

        result = await compactor.compact(messages)

        assert result.success is True
        assert result.compacted_messages < result.original_messages
        assert result.summary != ""
        assert "对话摘要" in result.summary

    @pytest.mark.asyncio
    async def test_compact_without_llm_uses_rule_based(self):
        """无 LLM 时使用规则摘要"""
        compactor = SessionCompactor(llm=None)
        messages = make_conversation(10)

        result = await compactor.compact(messages)

        assert result.success is True
        assert result.summary != ""
        assert "对话摘要" in result.summary

    @pytest.mark.asyncio
    async def test_compact_preserves_recent_messages(self):
        """压缩保留最近的消息"""
        compactor = SessionCompactor(
            config=CompactionConfig(compaction_ratio=0.5),
            llm=None,
        )

        messages = []
        for i in range(10):
            messages.append(make_msg("user", f"消息{i}"))
            messages.append(make_msg("assistant", f"回复{i}"))

        result = await compactor.compact(messages)

        # 压缩后消息数应该 < 原始 (摘要 + 最近50%)
        assert result.compacted_messages < result.original_messages
        assert result.compacted_tokens < result.original_tokens

    @pytest.mark.asyncio
    async def test_compact_tiny_session_noop(self):
        """极小会话不压缩"""
        compactor = SessionCompactor(llm=None)
        messages = [make_msg("user", "hi"), make_msg("assistant", "hello")]

        result = await compactor.compact(messages)

        assert result.success is True
        assert result.compacted_messages == result.original_messages

    @pytest.mark.asyncio
    async def test_compact_llm_failure_fallback(self):
        """LLM 失败时 fallback 到规则摘要"""
        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(side_effect=Exception("API Error"))

        compactor = SessionCompactor(llm=mock_llm)
        messages = make_conversation(10)

        result = await compactor.compact(messages)

        assert result.success is True
        assert result.summary != ""  # 使用规则摘要


# ============== 规则摘要 ==============

class TestRuleBasedSummary:
    """规则摘要测试"""

    def test_rule_summary_includes_user_messages(self):
        """规则摘要包含用户消息"""
        compactor = SessionCompactor()
        messages = [
            make_msg("user", "帮我导航到厨房"),
            make_msg("assistant", "好的，正在导航..."),
            make_msg("user", "拿起桌上的杯子"),
            make_msg("assistant", "正在抓取杯子..."),
        ]

        summary = compactor._rule_based_summary(messages)

        assert "导航" in summary or "厨房" in summary
        assert "杯子" in summary


# ============== 便捷函数 ==============

class TestCreateSessionCompactor:
    """便捷函数测试"""

    def test_create_with_defaults(self):
        """默认创建"""
        compactor = create_session_compactor()
        assert isinstance(compactor, SessionCompactor)
        assert compactor.config.context_window == 128000

    def test_create_with_custom_config(self):
        """自定义配置创建"""
        compactor = create_session_compactor(
            context_window=32000,
            reserve_tokens=5000,
        )
        assert compactor.config.context_window == 32000
        assert compactor.config.reserve_tokens_floor == 5000


# ============== 统计 ==============

class TestCompactorStats:
    """统计测试"""

    @pytest.mark.asyncio
    async def test_stats_updated_after_compaction(self):
        """压缩后统计更新"""
        compactor = SessionCompactor(llm=None)

        messages = make_conversation(10)
        await compactor.compact(messages)

        stats = compactor.get_stats()
        assert stats["total_compactions"] == 1
        assert stats["total_tokens_saved"] > 0


# ============== 运行 ==============

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
