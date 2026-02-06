"""
LLM 推理适配器单元测试

测试 LLMInferenceAdapter 的流式/非流式推理、tool_calls 解析、token 统计。
"""

import json
import pytest
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

from orb.agent.runtime.llm_inference import (
    LLMInferenceAdapter,
    create_inference_adapter,
)
from orb.system.llm.message import (
    LLMMessage,
    LLMResponse,
    MessageRole,
    FinishReason,
    Usage,
    StreamChunk,
    ToolCall as LLMToolCall,
)


# ============== Mock 对象 ==============

@dataclass
class MockAgentContext:
    """Mock AgentContext"""
    system_prompt: str = "You are a helpful robot assistant."
    messages: List[LLMMessage] = field(default_factory=list)
    tools: Optional[list] = None
    available_tools: Optional[list] = None


class MockLLM:
    """Mock BaseLLM"""

    def __init__(self, model: str = "mock-model"):
        self.model = model
        self._chat_response: Optional[LLMResponse] = None
        self._stream_chunks: List[StreamChunk] = []
        self.chat_call_count = 0
        self.stream_call_count = 0

    def set_chat_response(self, response: LLMResponse):
        """设置非流式响应"""
        self._chat_response = response

    def set_stream_chunks(self, chunks: List[StreamChunk]):
        """设置流式 chunks"""
        self._stream_chunks = chunks

    async def chat(self, messages, tools=None, **kwargs) -> LLMResponse:
        """非流式对话"""
        self.chat_call_count += 1
        if self._chat_response:
            return self._chat_response
        return LLMResponse(
            content="Default response",
            finish_reason=FinishReason.STOP,
        )

    async def stream_chat(self, messages, tools=None, **kwargs) -> AsyncIterator[StreamChunk]:
        """流式对话"""
        self.stream_call_count += 1
        for chunk in self._stream_chunks:
            yield chunk


# ============== 测试 ==============

class TestLLMInferenceAdapterInit:
    """初始化测试"""

    def test_default_init(self):
        """测试默认初始化"""
        llm = MockLLM()
        adapter = LLMInferenceAdapter(llm)

        assert adapter.llm is llm
        assert adapter._temperature == 0.7
        assert adapter._use_streaming is True

    def test_custom_init(self):
        """测试自定义初始化"""
        llm = MockLLM()
        adapter = LLMInferenceAdapter(
            llm,
            temperature=0.3,
            max_tokens=1000,
            use_streaming=False,
        )

        assert adapter._temperature == 0.3
        assert adapter._max_tokens == 1000
        assert adapter._use_streaming is False


class TestBatchInference:
    """非流式推理测试"""

    @pytest.mark.asyncio
    async def test_simple_text_response(self):
        """测试简单文本响应"""
        llm = MockLLM()
        llm.set_chat_response(LLMResponse(
            content="你好！我是机器人助手。",
            finish_reason=FinishReason.STOP,
            usage=Usage(prompt_tokens=10, completion_tokens=15, total_tokens=25),
        ))

        adapter = LLMInferenceAdapter(llm, use_streaming=False)
        context = MockAgentContext(
            messages=[LLMMessage.user("你好")],
        )

        results = []
        async for item in adapter(context):
            results.append(item)

        # 应包含: 文本 + usage + finish
        text_items = [r for r in results if isinstance(r, str)]
        assert len(text_items) == 1
        assert text_items[0] == "你好！我是机器人助手。"

        usage_items = [r for r in results if isinstance(r, dict) and r.get("type") == "usage"]
        assert len(usage_items) == 1
        assert usage_items[0]["tokens"] == 25

    @pytest.mark.asyncio
    async def test_tool_calls_response(self):
        """测试包含工具调用的响应"""
        llm = MockLLM()
        llm.set_chat_response(LLMResponse(
            content="",
            finish_reason=FinishReason.TOOL_CALLS,
            tool_calls=[
                LLMToolCall(
                    id="call_001",
                    name="navigate_to",
                    arguments={"location": "kitchen"},
                ),
            ],
        ))

        adapter = LLMInferenceAdapter(llm, use_streaming=False)
        context = MockAgentContext(
            messages=[LLMMessage.user("去厨房")],
        )

        results = []
        async for item in adapter(context):
            results.append(item)

        # 应包含 tool_call
        tool_calls = [r for r in results if isinstance(r, dict) and r.get("type") == "tool_call"]
        assert len(tool_calls) == 1
        assert tool_calls[0]["function"]["name"] == "navigate_to"

        # 解析 arguments
        args = json.loads(tool_calls[0]["function"]["arguments"])
        assert args["location"] == "kitchen"

    @pytest.mark.asyncio
    async def test_multiple_tool_calls(self):
        """测试多个工具调用"""
        llm = MockLLM()
        llm.set_chat_response(LLMResponse(
            content="我来帮你完成这个任务。",
            finish_reason=FinishReason.TOOL_CALLS,
            tool_calls=[
                LLMToolCall(id="call_001", name="detect_object", arguments={"target": "cup"}),
                LLMToolCall(id="call_002", name="grasp", arguments={"object_id": "cup_1"}),
            ],
        ))

        adapter = LLMInferenceAdapter(llm, use_streaming=False)
        context = MockAgentContext(messages=[LLMMessage.user("拿杯子")])

        results = []
        async for item in adapter(context):
            results.append(item)

        tool_calls = [r for r in results if isinstance(r, dict) and r.get("type") == "tool_call"]
        assert len(tool_calls) == 2
        assert tool_calls[0]["function"]["name"] == "detect_object"
        assert tool_calls[1]["function"]["name"] == "grasp"


class TestStreamInference:
    """流式推理测试"""

    @pytest.mark.asyncio
    async def test_streaming_text(self):
        """测试流式文本输出"""
        llm = MockLLM()
        llm.set_stream_chunks([
            StreamChunk(content="你好"),
            StreamChunk(content="！我是"),
            StreamChunk(content="机器人助手。"),
            StreamChunk(content="", is_final=True, finish_reason=FinishReason.STOP),
        ])

        adapter = LLMInferenceAdapter(llm, use_streaming=True)
        context = MockAgentContext(messages=[LLMMessage.user("你好")])

        results = []
        async for item in adapter(context):
            results.append(item)

        text_items = [r for r in results if isinstance(r, str)]
        assert "".join(text_items) == "你好！我是机器人助手。"

        assert llm.stream_call_count == 1

    @pytest.mark.asyncio
    async def test_streaming_with_tool_calls(self):
        """测试流式输出包含工具调用"""
        llm = MockLLM()
        llm.set_stream_chunks([
            StreamChunk(content="让我帮你"),
            StreamChunk(content="导航到厨房。"),
            StreamChunk(
                content="",
                is_final=True,
                finish_reason=FinishReason.TOOL_CALLS,
                tool_calls=[
                    LLMToolCall(
                        id="call_001",
                        name="navigate_to",
                        arguments={"location": "kitchen"},
                    ),
                ],
            ),
        ])

        adapter = LLMInferenceAdapter(llm, use_streaming=True)
        context = MockAgentContext(messages=[LLMMessage.user("去厨房")])

        results = []
        async for item in adapter(context):
            results.append(item)

        text_items = [r for r in results if isinstance(r, str)]
        assert "".join(text_items) == "让我帮你导航到厨房。"

        tool_calls = [r for r in results if isinstance(r, dict) and r.get("type") == "tool_call"]
        assert len(tool_calls) == 1
        assert tool_calls[0]["function"]["name"] == "navigate_to"


class TestMessageBuilding:
    """消息构建测试"""

    def test_build_messages_with_system_prompt(self):
        """测试系统提示词构建"""
        llm = MockLLM()
        adapter = LLMInferenceAdapter(llm)

        context = MockAgentContext(
            system_prompt="你是一个机器人。",
            messages=[LLMMessage.user("你好")],
        )

        messages = adapter._build_messages(context)

        assert len(messages) == 2
        assert messages[0].role == MessageRole.SYSTEM
        assert messages[0].content == "你是一个机器人。"
        assert messages[1].role == MessageRole.USER
        assert messages[1].content == "你好"

    def test_build_messages_without_system_prompt(self):
        """测试无系统提示词"""
        llm = MockLLM()
        adapter = LLMInferenceAdapter(llm)

        context = MockAgentContext(
            system_prompt="",
            messages=[LLMMessage.user("你好")],
        )

        messages = adapter._build_messages(context)
        assert len(messages) == 1
        assert messages[0].role == MessageRole.USER

    def test_build_messages_with_tool_result(self):
        """测试包含工具结果的消息"""
        llm = MockLLM()
        adapter = LLMInferenceAdapter(llm)

        context = MockAgentContext(
            system_prompt="Assistant",
            messages=[
                LLMMessage.user("去厨房"),
                LLMMessage.assistant(
                    "正在导航...",
                    tool_calls=[LLMToolCall(id="c1", name="nav", arguments={"loc": "kitchen"})],
                ),
                LLMMessage.tool("c1", '{"status": "arrived"}', name="nav"),
            ],
        )

        messages = adapter._build_messages(context)
        assert len(messages) == 4  # system + user + assistant + tool
        assert messages[3].role == MessageRole.TOOL
        assert messages[3].tool_call_id == "c1"


class TestToolExtraction:
    """工具提取测试"""

    def test_extract_tools_from_context(self):
        """测试从 context.tools 提取"""
        llm = MockLLM()
        adapter = LLMInferenceAdapter(llm)

        mock_tools = [MagicMock(), MagicMock()]
        context = MockAgentContext(tools=mock_tools)

        tools = adapter._extract_tools(context)
        assert tools is mock_tools

    def test_extract_available_tools(self):
        """测试从 context.available_tools 提取"""
        llm = MockLLM()
        adapter = LLMInferenceAdapter(llm)

        mock_tools = [MagicMock()]
        context = MockAgentContext(available_tools=mock_tools)

        tools = adapter._extract_tools(context)
        assert tools is mock_tools

    def test_no_tools(self):
        """测试无工具"""
        llm = MockLLM()
        adapter = LLMInferenceAdapter(llm)

        context = MockAgentContext()
        tools = adapter._extract_tools(context)
        assert tools is None


class TestCreateInferenceAdapter:
    """便捷函数测试"""

    def test_create_inference_adapter(self):
        """测试创建适配器"""
        llm = MockLLM()
        adapter = create_inference_adapter(
            llm,
            temperature=0.5,
            max_tokens=2000,
            use_streaming=False,
        )

        assert isinstance(adapter, LLMInferenceAdapter)
        assert adapter._temperature == 0.5
        assert adapter._max_tokens == 2000
        assert adapter._use_streaming is False


class TestErrorHandling:
    """错误处理测试"""

    @pytest.mark.asyncio
    async def test_chat_error_propagates(self):
        """测试非流式推理错误传播"""
        llm = MockLLM()
        llm.chat = AsyncMock(side_effect=Exception("API Error"))

        adapter = LLMInferenceAdapter(llm, use_streaming=False)
        context = MockAgentContext(messages=[LLMMessage.user("test")])

        with pytest.raises(Exception, match="API Error"):
            async for _ in adapter(context):
                pass

    @pytest.mark.asyncio
    async def test_stream_error_propagates(self):
        """测试流式推理错误传播"""
        llm = MockLLM()

        async def failing_stream(*args, **kwargs):
            yield StreamChunk(content="partial")
            raise Exception("Stream Error")

        llm.stream_chat = failing_stream

        adapter = LLMInferenceAdapter(llm, use_streaming=True)
        context = MockAgentContext(messages=[LLMMessage.user("test")])

        with pytest.raises(Exception, match="Stream Error"):
            results = []
            async for item in adapter(context):
                results.append(item)


# ============== 运行测试 ==============

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
