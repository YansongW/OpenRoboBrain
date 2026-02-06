"""
LLM 推理适配器

将 BaseLLM 适配为 AgentLoop 的 InferenceFunc 接口。
支持流式输出、tool_calls 解析、token 统计。

使用方式:
    from orb.system.llm import create_llm
    from orb.agent.runtime.llm_inference import LLMInferenceAdapter

    llm = create_llm("openai", model="gpt-4o", api_key="...")
    adapter = LLMInferenceAdapter(llm)
    agent_loop.set_inference_func(adapter.inference_func)
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Dict, List, Optional, TYPE_CHECKING, Union

from orb.system.services.logger import LoggerMixin

if TYPE_CHECKING:
    from orb.system.llm.base import BaseLLM
    from orb.agent.runtime.context_builder import AgentContext


class LLMInferenceAdapter(LoggerMixin):
    """
    LLM 推理适配器

    将 BaseLLM 的 chat/stream_chat 接口适配为 AgentLoop 所需的
    InferenceFunc: Callable[[AgentContext], AsyncIterator[Union[str, dict]]]

    支持:
    - 流式文本输出 (yield str)
    - 工具调用解析 (yield {"type": "tool_call", ...})
    - Token 使用统计 (yield {"type": "usage", ...})
    - 非流式 fallback (当 LLM 不支持流式时)
    """

    def __init__(
        self,
        llm: "BaseLLM",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        use_streaming: bool = True,
        extra_params: Optional[Dict[str, Any]] = None,
    ):
        """
        初始化推理适配器

        Args:
            llm: BaseLLM 实例
            temperature: 温度参数
            max_tokens: 最大输出 token 数
            use_streaming: 是否使用流式输出
            extra_params: 传递给 LLM 的额外参数
        """
        self._llm = llm
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._use_streaming = use_streaming
        self._extra_params = extra_params or {}

    @property
    def llm(self) -> "BaseLLM":
        """LLM 实例"""
        return self._llm

    @llm.setter
    def llm(self, value: "BaseLLM") -> None:
        """设置 LLM 实例"""
        self._llm = value

    async def __call__(self, context: "AgentContext") -> AsyncIterator[Union[str, dict]]:
        """
        执行推理 (实现 InferenceFunc 接口)

        Args:
            context: Agent 上下文 (包含 messages, tools 等)

        Yields:
            str: 文本 chunk
            dict: 结构化数据 (tool_call, usage 等)
        """
        async for item in self._run_inference(context):
            yield item

    async def inference_func(self, context: "AgentContext") -> AsyncIterator[Union[str, dict]]:
        """
        推理函数 (可直接传递给 AgentLoop.set_inference_func)

        用法:
            adapter = LLMInferenceAdapter(llm)
            agent_loop.set_inference_func(adapter.inference_func)
        """
        async for item in self._run_inference(context):
            yield item

    async def _run_inference(self, context: "AgentContext") -> AsyncIterator[Union[str, dict]]:
        """
        执行推理的核心逻辑

        Args:
            context: Agent 上下文

        Yields:
            文本 chunk 或结构化数据
        """
        from orb.system.llm.message import LLMMessage, MessageRole, FinishReason

        # 1. 从 AgentContext 提取 LLM messages
        messages = self._build_messages(context)

        # 2. 提取工具定义 (如果有)
        tools = self._extract_tools(context)

        # 3. 构建调用参数
        call_kwargs = {
            "temperature": self._temperature,
            **self._extra_params,
        }
        if self._max_tokens:
            call_kwargs["max_tokens"] = self._max_tokens

        # 4. 选择流式/非流式
        if self._use_streaming and hasattr(self._llm, 'stream_chat'):
            async for item in self._stream_inference(messages, tools, call_kwargs):
                yield item
        else:
            async for item in self._batch_inference(messages, tools, call_kwargs):
                yield item

    async def _stream_inference(
        self,
        messages: list,
        tools: Optional[list],
        call_kwargs: dict,
    ) -> AsyncIterator[Union[str, dict]]:
        """
        流式推理

        Yields:
            str: 文本 delta
            dict: tool_call 或 usage 数据
        """
        from orb.system.llm.message import FinishReason

        self.logger.debug(
            f"流式推理: model={self._llm.model}, "
            f"messages={len(messages)}, tools={len(tools) if tools else 0}"
        )

        try:
            stream = self._llm.stream_chat(
                messages=messages,
                tools=tools,
                **call_kwargs,
            )

            async for chunk in stream:
                # 输出文本 content
                if chunk.content:
                    yield chunk.content

                # 最终 chunk: 处理 tool_calls 和 finish_reason
                if chunk.is_final:
                    # 输出工具调用
                    if chunk.tool_calls:
                        for tc in chunk.tool_calls:
                            yield {
                                "type": "tool_call",
                                "id": tc.id,
                                "function": {
                                    "name": tc.name,
                                    "arguments": json.dumps(
                                        tc.arguments, ensure_ascii=False
                                    ) if isinstance(tc.arguments, dict) else tc.arguments,
                                },
                            }

                    # 输出 finish reason
                    if chunk.finish_reason:
                        yield {
                            "type": "finish",
                            "reason": chunk.finish_reason.value,
                        }

        except Exception as e:
            self.logger.error(f"流式推理失败: {e}")
            raise

    async def _batch_inference(
        self,
        messages: list,
        tools: Optional[list],
        call_kwargs: dict,
    ) -> AsyncIterator[Union[str, dict]]:
        """
        非流式推理 (fallback)

        Yields:
            str: 完整的文本响应
            dict: tool_call 或 usage 数据
        """
        self.logger.debug(
            f"非流式推理: model={self._llm.model}, "
            f"messages={len(messages)}, tools={len(tools) if tools else 0}"
        )

        try:
            response = await self._llm.chat(
                messages=messages,
                tools=tools,
                **call_kwargs,
            )

            # 输出文本
            if response.content:
                yield response.content

            # 输出工具调用
            if response.tool_calls:
                for tc in response.tool_calls:
                    yield {
                        "type": "tool_call",
                        "id": tc.id,
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(
                                tc.arguments, ensure_ascii=False
                            ) if isinstance(tc.arguments, dict) else tc.arguments,
                        },
                    }

            # 输出 usage
            if response.usage:
                yield {
                    "type": "usage",
                    "tokens": response.usage.total_tokens,
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                }

            # 输出 finish reason
            yield {
                "type": "finish",
                "reason": response.finish_reason.value,
            }

        except Exception as e:
            self.logger.error(f"非流式推理失败: {e}")
            raise

    def _build_messages(self, context: "AgentContext") -> list:
        """
        从 AgentContext 构建 LLM messages

        AgentContext 包含:
        - system_prompt: 系统提示词
        - messages: 历史消息列表
        - tool_results: 本轮工具执行结果 (如果在 ReAct 循环中)

        Returns:
            LLMMessage 列表
        """
        from orb.system.llm.message import LLMMessage, MessageRole

        llm_messages = []

        # 系统消息
        if hasattr(context, 'system_prompt') and context.system_prompt:
            llm_messages.append(LLMMessage.system(context.system_prompt))

        # 历史消息
        if hasattr(context, 'messages') and context.messages:
            for msg in context.messages:
                if hasattr(msg, 'role') and hasattr(msg, 'content'):
                    # 如果是 LLMMessage，直接使用
                    if isinstance(msg, LLMMessage):
                        llm_messages.append(msg)
                    else:
                        # 将 SessionMessage 等转换为 LLMMessage
                        role_str = msg.role.value if hasattr(msg.role, 'value') else str(msg.role)
                        try:
                            role = MessageRole(role_str)
                        except ValueError:
                            role = MessageRole.USER

                        llm_msg = LLMMessage(
                            role=role,
                            content=msg.content or "",
                            tool_call_id=getattr(msg, 'tool_call_id', None),
                            name=getattr(msg, 'tool_name', None) or getattr(msg, 'name', None),
                        )

                        # 如果 assistant 消息包含 tool_calls
                        if role == MessageRole.ASSISTANT and hasattr(msg, 'tool_calls') and msg.tool_calls:
                            from orb.system.llm.message import ToolCall as LLMToolCall
                            llm_msg.tool_calls = [
                                LLMToolCall(
                                    id=tc.get('id', ''),
                                    name=tc.get('name', ''),
                                    arguments=tc.get('arguments', {}),
                                ) if isinstance(tc, dict) else tc
                                for tc in msg.tool_calls
                            ]

                        llm_messages.append(llm_msg)

        return llm_messages

    def _extract_tools(self, context: "AgentContext") -> Optional[list]:
        """
        从 AgentContext 提取工具定义

        Returns:
            工具列表 (Tool 对象) 或 None
        """
        if hasattr(context, 'tools') and context.tools:
            return context.tools
        if hasattr(context, 'available_tools') and context.available_tools:
            return context.available_tools
        return None


# ============== 便捷函数 ==============

def create_inference_adapter(
    llm: "BaseLLM",
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
    use_streaming: bool = True,
    **kwargs,
) -> LLMInferenceAdapter:
    """
    创建 LLM 推理适配器

    Args:
        llm: BaseLLM 实例
        temperature: 温度
        max_tokens: 最大 token 数
        use_streaming: 是否流式
        **kwargs: 额外参数

    Returns:
        LLMInferenceAdapter 实例
    """
    return LLMInferenceAdapter(
        llm=llm,
        temperature=temperature,
        max_tokens=max_tokens,
        use_streaming=use_streaming,
        extra_params=kwargs if kwargs else None,
    )
