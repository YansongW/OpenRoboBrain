"""
第三阶段集成测试: 完整管线端到端

验证:
1. core.py 双模式分支 (LLM/规则)
2. AgentLoop + LLMInferenceAdapter 完整 ReAct 管线
3. Memory 工具注册和调用
4. MemoryRanker 在 process() 流程中的检索
5. SessionCompactor 集成
6. ProcessResult.mode 字段正确

所有测试使用 Mock LLM，不需要真实 API Key。
"""

import json
import os
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional

from orb import OpenRoboBrain, ProcessResult
from orb.system.llm.message import (
    LLMResponse,
    FinishReason,
    Usage,
    StreamChunk,
    ToolCall as LLMToolCall,
)
from orb.data.memory.memory_stream import MemoryStream, MemoryType
from orb.data.memory.memory_ranker import MemoryRanker
from orb.system.tools.builtin.memory import MemoryTools, create_memory_tools


# ============== Test: 规则模式 (无 LLM) ==============

class TestRuleModeProcess:
    """规则模式处理测试 (无 LLM API Key)"""

    @pytest_asyncio.fixture
    async def brain(self):
        brain = OpenRoboBrain(mock_ros2=True)
        await brain.initialize()
        await brain.start()
        yield brain
        await brain.stop()

    @pytest.mark.asyncio
    async def test_rule_mode_active_without_llm(self, brain: OpenRoboBrain):
        """无 LLM 时使用规则模式"""
        assert brain.llm_available is False

        result = await brain.process("你好")

        assert result.mode == "rule"
        assert result.success is True
        assert "你好" in result.chat_response or "机器人" in result.chat_response

    @pytest.mark.asyncio
    async def test_memory_initialized_in_rule_mode(self, brain: OpenRoboBrain):
        """规则模式下记忆系统也会初始化"""
        assert brain.memory_stream is not None
        assert brain.memory_ranker is not None

    @pytest.mark.asyncio
    async def test_rule_mode_stores_memory(self, brain: OpenRoboBrain):
        """规则模式也存储记忆"""
        initial_size = brain.memory_stream.size

        await brain.process("去厨房")

        assert brain.memory_stream.size > initial_size

    @pytest.mark.asyncio
    async def test_process_result_has_mode_field(self, brain: OpenRoboBrain):
        """ProcessResult 包含 mode 字段"""
        result = await brain.process("你好")

        d = result.to_dict()
        assert "mode" in d
        assert d["mode"] == "rule"


# ============== Test: Memory 工具 ==============

class TestMemoryTools:
    """Memory 工具测试"""

    def test_memory_write_tool(self):
        """测试 memory_write 工具"""
        stream = MemoryStream(agent_id="test")
        ranker = MemoryRanker()
        tools = create_memory_tools(stream, ranker)

        result_json = tools._handle_memory_write(
            description="用户喜欢喝温水",
            importance=8,
            memory_type="preference",
            tags=["user", "water"],
        )

        result = json.loads(result_json)
        assert result["status"] == "success"
        assert result["importance"] == 8
        assert stream.size == 1

    def test_memory_search_tool(self):
        """测试 memory_search 工具"""
        stream = MemoryStream(agent_id="test")
        ranker = MemoryRanker()
        tools = create_memory_tools(stream, ranker)

        # 添加记忆
        stream.create_and_add("杯子在厨房柜子里", importance=7.0)
        stream.create_and_add("今天天气不错", importance=2.0)
        stream.create_and_add("用户喜欢咖啡", importance=6.0)

        result_json = tools._handle_memory_search(query="厨房", top_k=3)
        result = json.loads(result_json)

        assert result["total"] > 0
        assert result["query"] == "厨房"
        assert len(result["results"]) <= 3

    def test_memory_get_tool(self):
        """测试 memory_get 工具"""
        stream = MemoryStream(agent_id="test")
        tools = create_memory_tools(stream, None)

        mem = stream.create_and_add("测试记忆", importance=5.0)

        result_json = tools._handle_memory_get(memory_id=mem.memory_id)
        result = json.loads(result_json)

        assert result["memory_id"] == mem.memory_id
        assert result["description"] == "测试记忆"

    def test_memory_get_nonexistent(self):
        """获取不存在的记忆"""
        stream = MemoryStream(agent_id="test")
        tools = create_memory_tools(stream, None)

        result_json = tools._handle_memory_get(memory_id="nonexistent")
        result = json.loads(result_json)

        assert "error" in result

    def test_memory_search_with_type_filter(self):
        """按类型过滤搜索"""
        stream = MemoryStream(agent_id="test")
        ranker = MemoryRanker()
        tools = create_memory_tools(stream, ranker)

        stream.create_and_add("安全事件", memory_type=MemoryType.SAFETY, importance=9.0)
        stream.create_and_add("普通观察", memory_type=MemoryType.OBSERVATION, importance=3.0)

        result_json = tools._handle_memory_search(
            query="事件", memory_type="safety", top_k=5,
        )
        result = json.loads(result_json)

        # 只返回 safety 类型
        for r in result["results"]:
            assert r["memory_type"] == "safety"

    def test_get_tools_returns_three(self):
        """get_tools 返回 3 个工具"""
        tools = create_memory_tools()
        tool_list = tools.get_tools()

        assert len(tool_list) == 3
        names = {t.name for t in tool_list}
        assert names == {"memory_write", "memory_search", "memory_get"}

    def test_tools_have_openai_format(self):
        """工具可以转换为 OpenAI 格式"""
        tools = create_memory_tools()

        for tool in tools.get_tools():
            openai_fmt = tool.to_openai_format()
            assert openai_fmt["type"] == "function"
            assert "name" in openai_fmt["function"]
            assert "description" in openai_fmt["function"]
            assert "parameters" in openai_fmt["function"]


# ============== Test: 管线贯通（Mock LLM）==============

class TestLLMPipelineIntegration:
    """LLM 管线集成测试 (使用 Mock)"""

    @pytest.mark.asyncio
    async def test_process_with_mock_llm(self):
        """使用 Mock LLM 测试完整 process() 管线"""
        brain = OpenRoboBrain(mock_ros2=True)
        await brain.initialize()
        await brain.start()

        # 注入 Mock LLM
        mock_llm = MagicMock()
        mock_response = LLMResponse(
            content=json.dumps({
                "chat_response": "好的，我来帮你去厨房。",
                "ros2_commands": [
                    {"command_type": "navigate", "parameters": {"target": "kitchen"}}
                ],
            }, ensure_ascii=False),
            finish_reason=FinishReason.STOP,
            usage=Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        )
        mock_llm.chat = AsyncMock(return_value=mock_response)
        mock_llm.model = "mock-gpt-4o"

        async def mock_stream(*args, **kwargs):
            yield StreamChunk(
                content=mock_response.content,
                is_final=True,
                finish_reason=FinishReason.STOP,
            )

        mock_llm.stream_chat = mock_stream

        # 手动设置 LLM 管线
        from orb.agent.runtime.llm_inference import LLMInferenceAdapter
        from orb.agent.runtime.agent_loop import AgentLoop, LoopConfig
        from orb.agent.runtime.context_builder import ContextBuilder, ContextConfig
        from orb.agent.runtime.tool_executor import ToolExecutor
        from orb.agent.infrastructure.session_store import SessionStore
        from pathlib import Path
        import tempfile

        session_store = SessionStore(
            sessions_dir=Path(tempfile.mkdtemp()) / "sessions",
            agent_id="test",
        )
        session = await session_store.create_session(session_key="agent:test:main")

        tool_executor = ToolExecutor()
        context_builder = ContextBuilder(
            config=ContextConfig(base_system_prompt="你是测试机器人。"),
        )
        adapter = LLMInferenceAdapter(mock_llm, use_streaming=True)

        agent_loop = AgentLoop(
            config=LoopConfig(max_iterations=5, timeout_seconds=30.0),
            context_builder=context_builder,
            tool_executor=tool_executor,
            session_store=session_store,
            inference_func=adapter.inference_func,
        )

        brain._llm = mock_llm
        brain._llm_available = True
        brain._agent_loop = agent_loop
        brain._session_store = session_store
        brain._main_session_id = session.session_id
        brain._context_builder = context_builder
        brain._tool_executor = tool_executor
        brain._inference_adapter = adapter

        # 执行
        result = await brain.process("去厨房")

        assert result.mode == "llm"
        assert result.success is True
        assert "厨房" in result.chat_response
        assert len(result.ros2_commands) > 0
        assert result.ros2_commands[0].command_type == "navigate"

        # 验证记忆被存储
        assert brain.memory_stream.size > 0

        await brain.stop()

    @pytest.mark.asyncio
    async def test_memory_retrieval_in_process(self):
        """验证 process() 中的记忆检索"""
        brain = OpenRoboBrain(mock_ros2=True)
        await brain.initialize()
        await brain.start()

        # 预置记忆
        brain.memory_stream.create_and_add(
            "杯子在厨房第二个柜子里",
            memory_type=MemoryType.SPATIAL,
            importance=8.0,
        )
        brain.memory_stream.create_and_add(
            "用户不喜欢冷水",
            memory_type=MemoryType.PREFERENCE,
            importance=7.0,
        )

        # 规则模式下处理
        result = await brain.process("帮我倒杯水")

        assert result.success is True
        # 记忆应该增长（添加了新的观察记忆）
        assert brain.memory_stream.size > 2

        await brain.stop()


# ============== Test: ProcessResult 序列化 ==============

class TestProcessResultSerialization:
    """ProcessResult 序列化测试"""

    def test_to_dict_includes_mode(self):
        """to_dict 包含 mode 字段"""
        result = ProcessResult(
            trace_id="test-123",
            chat_response="你好",
            mode="llm",
        )
        d = result.to_dict()

        assert d["mode"] == "llm"
        assert d["trace_id"] == "test-123"

    def test_to_dict_with_metadata(self):
        """to_dict 包含 metadata"""
        result = ProcessResult(
            trace_id="test-456",
            chat_response="OK",
            mode="rule",
            metadata={"tokens_used": 150, "iterations": 2},
        )
        d = result.to_dict()

        assert d["metadata"]["tokens_used"] == 150


# ============== 运行 ==============

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
