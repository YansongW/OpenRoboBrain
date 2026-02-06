"""
第二阶段集成测试

验证 Phase 1-3 所有新模块的协同工作：
- LLMInferenceAdapter + AgentLoop ReAct 循环
- MemoryStream + MemoryRanker 类人记忆排序
- SessionCompactor 自动压缩

所有测试使用 Mock LLM，不需要真实 API Key。
"""

import time
import math
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional

from orb.system.llm.message import (
    LLMMessage,
    LLMResponse,
    MessageRole as LLMMessageRole,
    FinishReason,
    Usage,
    StreamChunk,
    ToolCall as LLMToolCall,
)
from orb.agent.runtime.llm_inference import LLMInferenceAdapter
from orb.data.memory.memory_stream import MemoryObject, MemoryType, MemoryStream
from orb.data.memory.memory_ranker import MemoryRanker, RankingWeights
from orb.agent.infrastructure.session_compactor import (
    SessionCompactor,
    CompactionConfig,
)
from orb.agent.infrastructure.session_store import (
    SessionMessage,
    MessageRole,
)


# ============== Mock 对象 ==============

@dataclass
class MockAgentContext:
    system_prompt: str = "你是一个服务机器人。"
    messages: List[LLMMessage] = field(default_factory=list)
    tools: Optional[list] = None


class MockLLM:
    def __init__(self):
        self.model = "mock-gpt-4o"
        self._responses = []
        self._call_idx = 0

    def add_response(self, content: str = "", tool_calls=None, finish="stop"):
        finish_map = {"stop": FinishReason.STOP, "tool_calls": FinishReason.TOOL_CALLS}
        self._responses.append(LLMResponse(
            content=content,
            finish_reason=finish_map.get(finish, FinishReason.STOP),
            tool_calls=tool_calls,
            usage=Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        ))

    async def chat(self, messages, tools=None, **kwargs):
        if self._call_idx < len(self._responses):
            resp = self._responses[self._call_idx]
            self._call_idx += 1
            return resp
        return LLMResponse(content="默认回复", finish_reason=FinishReason.STOP)

    async def stream_chat(self, messages, tools=None, **kwargs):
        resp = await self.chat(messages, tools, **kwargs)
        yield StreamChunk(content=resp.content, is_final=True,
                          finish_reason=resp.finish_reason,
                          tool_calls=resp.tool_calls)


# ============== 集成测试 ==============

class TestLLMInferenceIntegration:
    """LLM 推理适配器集成测试"""

    @pytest.mark.asyncio
    async def test_inference_with_tool_calls_react_cycle(self):
        """验证 ReAct 循环: 推理→工具调用→再推理"""
        llm = MockLLM()

        # 第一次推理: 返回工具调用
        llm.add_response(
            content="我需要导航到厨房。",
            tool_calls=[LLMToolCall(id="c1", name="navigate_to", arguments={"location": "kitchen"})],
            finish="tool_calls",
        )
        # 第二次推理 (工具结果后): 返回最终回复
        llm.add_response(content="已经到达厨房了！", finish="stop")

        adapter = LLMInferenceAdapter(llm, use_streaming=False)

        # 第一次推理
        context1 = MockAgentContext(messages=[LLMMessage.user("去厨房")])
        results1 = []
        async for item in adapter(context1):
            results1.append(item)

        tool_calls = [r for r in results1 if isinstance(r, dict) and r.get("type") == "tool_call"]
        assert len(tool_calls) == 1
        assert tool_calls[0]["function"]["name"] == "navigate_to"

        # 第二次推理 (带工具结果)
        context2 = MockAgentContext(messages=[
            LLMMessage.user("去厨房"),
            LLMMessage.assistant("我需要导航到厨房。",
                                 tool_calls=[LLMToolCall(id="c1", name="navigate_to", arguments={"location": "kitchen"})]),
            LLMMessage.tool("c1", '{"status": "arrived"}', name="navigate_to"),
        ])
        results2 = []
        async for item in adapter(context2):
            results2.append(item)

        texts = [r for r in results2 if isinstance(r, str)]
        assert "到达" in "".join(texts) or "厨房" in "".join(texts)

    @pytest.mark.asyncio
    async def test_streaming_inference(self):
        """流式推理集成"""
        llm = MockLLM()
        llm.add_response(content="你好！我是服务机器人凯。")

        adapter = LLMInferenceAdapter(llm, use_streaming=True)
        context = MockAgentContext(messages=[LLMMessage.user("你好")])

        texts = []
        async for item in adapter(context):
            if isinstance(item, str):
                texts.append(item)

        assert "机器人" in "".join(texts)


class TestMemoryRankerIntegration:
    """MemoryRanker 端到端集成测试"""

    def test_robot_scenario_kitchen_memory(self):
        """机器人场景: 厨房相关记忆检索"""
        stream = MemoryStream(agent_id="kai")
        ranker = MemoryRanker()

        # 添加不同类型的记忆
        # 空间记忆
        stream.create_and_add(
            "杯子放在厨房的第二个抽屉里",
            memory_type=MemoryType.SPATIAL,
            importance=6.0,
            embedding=[0.9, 0.1, 0.0, 0.0],
            tags=["kitchen", "cup"],
        )
        # 用户偏好
        stream.create_and_add(
            "用户喜欢喝温水",
            memory_type=MemoryType.PREFERENCE,
            importance=7.0,
            embedding=[0.7, 0.3, 0.0, 0.0],
            tags=["preference", "water"],
        )
        # 安全记忆
        stream.create_and_add(
            "昨天在厨房地板滑了一下",
            memory_type=MemoryType.SAFETY,
            importance=9.0,
            embedding=[0.6, 0.2, 0.2, 0.0],
            tags=["safety", "kitchen"],
        )
        # 无关记忆
        stream.create_and_add(
            "今天天气很好",
            memory_type=MemoryType.OBSERVATION,
            importance=2.0,
            embedding=[0.0, 0.0, 0.0, 1.0],
            tags=["weather"],
        )

        # 查询: "去厨房倒水"
        query_embedding = [0.8, 0.2, 0.0, 0.0]
        candidates = stream.get_all()

        results = ranker.rank(
            "去厨房倒水",
            candidates,
            query_embedding=query_embedding,
            top_k=4,
        )

        # 验证: 安全记忆和空间记忆应该排在前面（高重要性 + 高相关性）
        top_descriptions = [r.memory.description for r in results[:2]]
        assert any("杯子" in d or "安全" in d or "滑" in d for d in top_descriptions)

        # 天气记忆应该排在最后（低重要性 + 低相关性）
        assert results[-1].memory.description == "今天天气很好"

    def test_spreading_activation_primes_related(self):
        """扩散激活: 想起一件事连带激活相关记忆"""
        stream = MemoryStream(agent_id="kai")
        ranker = MemoryRanker(weights=RankingWeights(
            recency=0.0, importance=0.0, relevance=0.2,
            frequency=0.0, context_affinity=3.0,  # 高权重扩散激活
        ))

        # 记忆网络
        cooking = stream.create_and_add(
            "上次做了番茄炒蛋",
            embedding=[0.8, 0.2, 0.0, 0.0],
        )
        eggs = stream.create_and_add(
            "鸡蛋放在冰箱第一层",
            embedding=[0.7, 0.3, 0.0, 0.0],
        )
        tomato = stream.create_and_add(
            "番茄在厨房台面上",
            embedding=[0.6, 0.3, 0.1, 0.0],
        )
        music = stream.create_and_add(
            "用户喜欢听古典音乐",
            embedding=[0.0, 0.0, 0.1, 0.9],
        )

        # 模拟: 刚想起了"做饭" → 激活 cooking
        stream.retrieve(cooking.memory_id)

        # 查询: "准备食材" (中等相关性)
        query_emb = [0.5, 0.4, 0.1, 0.0]
        results = ranker.rank(
            "准备食材",
            stream.get_all(),
            recently_activated=stream.recently_activated,
            query_embedding=query_emb,
        )

        # 鸡蛋和番茄应该因为扩散激活而排名提升
        top_2 = {r.memory.description for r in results[:3]}
        assert "鸡蛋放在冰箱第一层" in top_2 or "番茄在厨房台面上" in top_2

        # 音乐应该排最后
        assert results[-1].memory.description == "用户喜欢听古典音乐"

    def test_spaced_repetition_strengthens_memory(self):
        """间隔重复: 多次检索增强记忆"""
        stream = MemoryStream(agent_id="kai")
        ranker = MemoryRanker(weights=RankingWeights(
            recency=5.0, importance=0.0, relevance=0.0,
            frequency=0.0, context_affinity=0.0,
        ))

        # 两条同时创建的记忆
        freq = stream.create_and_add("经常被想起的记忆", importance=5.0)
        rare = stream.create_and_add("很少被想起的记忆", importance=5.0)

        # 模拟: freq 被多次检索 → 记忆强度增加 → 衰减变慢
        for _ in range(5):
            stream.retrieve(freq.memory_id)
            time.sleep(0.01)

        assert freq.memory_strength > rare.memory_strength
        assert freq.access_count == 5
        assert rare.access_count == 0

    def test_signal_breakdown_explainability(self):
        """可解释性: 每条记忆的信号分解"""
        ranker = MemoryRanker()
        stream = MemoryStream(agent_id="kai")

        stream.create_and_add("测试记忆", importance=7.0, embedding=[1.0, 0.0])

        results = ranker.rank(
            "测试",
            stream.get_all(),
            query_embedding=[1.0, 0.0],
        )

        # 信号分解应该可读
        assert len(results) == 1
        breakdown = results[0].signals.to_dict()
        assert all(k in breakdown for k in ["recency", "importance", "relevance", "frequency", "context_affinity"])
        # 所有值在 [0, 1] 范围
        for v in breakdown.values():
            assert 0.0 <= v <= 1.0


class TestSessionCompactorIntegration:
    """SessionCompactor 端到端集成测试"""

    @pytest.mark.asyncio
    async def test_prune_then_compact(self):
        """先 pruning 再 compaction 的完整流程"""
        mock_llm = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content = "## 摘要\n- 用户请求倒水\n- 机器人执行了导航和抓取"
        mock_llm.chat = AsyncMock(return_value=mock_resp)

        compactor = SessionCompactor(
            config=CompactionConfig(
                context_window=500,
                reserve_tokens_floor=100,
                tool_result_max_age_turns=2,
                tool_result_max_chars=50,
            ),
            llm=mock_llm,
        )

        # 创建大量消息
        messages = []
        for i in range(20):
            messages.append(SessionMessage(role=MessageRole.USER, content=f"请求 {i}: {'内容' * 50}"))
            messages.append(SessionMessage(role=MessageRole.ASSISTANT, content=f"回复 {i}: {'结果' * 50}"))
            if i % 3 == 0:
                messages.append(SessionMessage(
                    role=MessageRole.TOOL,
                    content="A" * 500,
                    tool_call_id=f"c{i}",
                    tool_name="navigate",
                ))

        # 应该触发压缩
        assert compactor.should_compact(messages) is True

        # 先 pruning
        pruned, prune_count = compactor.prune_messages(messages)
        assert prune_count > 0

        # 再压缩
        result = await compactor.compact(pruned)

        assert result.success is True
        assert result.compacted_messages < result.original_messages
        assert result.summary != ""

    @pytest.mark.asyncio
    async def test_compact_with_rule_fallback(self):
        """LLM 不可用时的规则摘要 fallback"""
        compactor = SessionCompactor(
            config=CompactionConfig(context_window=200, reserve_tokens_floor=50),
            llm=None,
        )

        messages = []
        for i in range(15):
            messages.append(SessionMessage(role=MessageRole.USER, content=f"用户消息{i}"))
            messages.append(SessionMessage(role=MessageRole.ASSISTANT, content=f"助手回复{i}"))

        result = await compactor.compact(messages)

        assert result.success is True
        assert "对话摘要" in result.summary


class TestFullPipelineIntegration:
    """完整管线集成测试: LLM + Memory + Compaction"""

    @pytest.mark.asyncio
    async def test_process_with_memory_and_compaction(self):
        """完整处理流程: 用户输入 → 记忆检索 → LLM 推理 → 记忆存储"""
        # 1. 设置记忆系统
        stream = MemoryStream(agent_id="kai")
        ranker = MemoryRanker()

        # 预置记忆
        stream.create_and_add(
            "用户之前要求过去厨房拿杯子",
            memory_type=MemoryType.OBSERVATION,
            importance=6.0,
            embedding=[0.8, 0.2, 0.0, 0.0],
        )
        stream.create_and_add(
            "杯子在厨房第二个柜子里",
            memory_type=MemoryType.SPATIAL,
            importance=7.0,
            embedding=[0.7, 0.3, 0.0, 0.0],
        )

        # 2. 记忆检索
        query = "帮我倒杯水"
        query_emb = [0.75, 0.25, 0.0, 0.0]

        results = ranker.rank(
            query,
            stream.get_all(),
            recently_activated=stream.recently_activated,
            query_embedding=query_emb,
            top_k=3,
        )

        assert len(results) >= 1
        # 最相关的记忆应该与杯子/厨房相关
        top_memory = results[0].memory.description
        assert "杯子" in top_memory or "厨房" in top_memory

        # 3. 使用记忆构建 context 并推理
        memory_context = "\n".join([
            f"- {r.memory.description} (score: {r.final_score:.2f})"
            for r in results
        ])

        llm = MockLLM()
        llm.add_response(content=f"好的，我记得{top_memory}。我来帮你倒水。")

        adapter = LLMInferenceAdapter(llm, use_streaming=False)
        context = MockAgentContext(
            system_prompt=f"你是服务机器人。\n\n相关记忆:\n{memory_context}",
            messages=[LLMMessage.user(query)],
        )

        response_texts = []
        async for item in adapter(context):
            if isinstance(item, str):
                response_texts.append(item)

        full_response = "".join(response_texts)
        assert len(full_response) > 0

        # 4. 将新的观察存入记忆
        new_memory = stream.create_and_add(
            f"用户请求倒水，助手回复: {full_response[:100]}",
            memory_type=MemoryType.OBSERVATION,
            importance=5.0,
        )

        assert stream.size >= 3  # 至少有 2 条预置 + 1 条新增

        # 5. 验证压缩器可以处理
        compactor = SessionCompactor(
            config=CompactionConfig(context_window=128000),
        )
        session_messages = [
            SessionMessage(role=MessageRole.USER, content=query),
            SessionMessage(role=MessageRole.ASSISTANT, content=full_response),
        ]

        # 小会话不触发压缩
        assert compactor.should_compact(session_messages) is False

        # 但估算 token 能工作
        tokens = compactor.estimate_messages_tokens(session_messages)
        assert tokens > 0


# ============== 运行 ==============

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
