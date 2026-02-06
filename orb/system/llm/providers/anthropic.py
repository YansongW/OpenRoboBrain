"""
Anthropic Claude LLM Provider

支持Claude系列模型和tool use能力。
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, AsyncIterator, Dict, List, Optional

from orb.system.llm.base import BaseLLM, LLMCapabilities
from orb.system.llm.message import (
    FinishReason,
    LLMMessage,
    LLMResponse,
    MessageRole,
    StreamChunk,
    ToolCall,
    Usage,
)

if TYPE_CHECKING:
    from orb.system.tools.base import Tool


class AnthropicLLM(BaseLLM):
    """
    Anthropic Claude LLM Provider
    
    支持Claude系列模型，包括tool use能力。
    """
    
    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 60.0,
        max_retries: int = 3,
        **kwargs,
    ):
        """
        初始化Anthropic LLM
        
        Args:
            model: 模型名称
            api_key: API密钥
            base_url: API基础URL
            timeout: 请求超时时间
            max_retries: 最大重试次数
            **kwargs: 其他参数
        """
        super().__init__(
            model=model,
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            **kwargs,
        )
        self._client: Optional[Any] = None
        self._async_client: Optional[Any] = None
    
    @property
    def provider_name(self) -> str:
        return "anthropic"
    
    @property
    def capabilities(self) -> LLMCapabilities:
        """获取LLM能力"""
        return LLMCapabilities(
            supports_tools=True,
            supports_streaming=True,
            supports_vision=True,  # Claude 3+ 支持视觉
            supports_json_mode=False,  # Anthropic没有原生JSON模式
            max_context_length=200000,  # Claude 3 支持200K上下文
            max_output_tokens=8192,
        )
    
    def _get_async_client(self):
        """获取异步客户端"""
        if self._async_client is None:
            try:
                from anthropic import AsyncAnthropic
            except ImportError:
                raise ImportError(
                    "Anthropic package not installed. "
                    "Install with: pip install anthropic"
                )
            
            kwargs = {
                "api_key": self.api_key,
                "timeout": self.timeout,
                "max_retries": self.max_retries,
            }
            if self.base_url:
                kwargs["base_url"] = self.base_url
            
            self._async_client = AsyncAnthropic(**kwargs)
        return self._async_client
    
    def _format_messages_for_provider(self, messages: List[LLMMessage]) -> tuple:
        """
        将消息格式化为Anthropic格式
        
        Anthropic要求system消息单独传递，其他消息以列表形式传递。
        
        Returns:
            (system_prompt, messages_list)
        """
        system_prompt = ""
        formatted_messages = []
        
        for msg in messages:
            role = msg.role.value if isinstance(msg.role, MessageRole) else msg.role
            
            if role == "system":
                system_prompt = msg.content
                continue
            
            # Anthropic只支持user和assistant角色
            if role == "tool":
                # 工具结果作为user消息的tool_result内容块
                formatted_messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.tool_call_id,
                            "content": msg.content,
                        }
                    ],
                })
            elif role == "assistant" and msg.tool_calls:
                # 助手消息带工具调用
                content = []
                if msg.content:
                    content.append({"type": "text", "text": msg.content})
                
                for tc in msg.tool_calls:
                    content.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.arguments,
                    })
                
                formatted_messages.append({
                    "role": "assistant",
                    "content": content,
                })
            else:
                # 普通消息
                formatted_messages.append({
                    "role": role,
                    "content": msg.content,
                })
        
        return system_prompt, formatted_messages
    
    def _format_tools_for_provider(self, tools: List["Tool"]) -> List[dict]:
        """将工具格式化为Anthropic格式"""
        return [tool.to_anthropic_format() for tool in tools]
    
    def _parse_response(self, response) -> LLMResponse:
        """解析Anthropic响应"""
        # 解析内容
        content = ""
        tool_calls = []
        
        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.input if isinstance(block.input, dict) else {},
                ))
        
        # 解析finish_reason
        finish_reason_map = {
            "end_turn": FinishReason.STOP,
            "tool_use": FinishReason.TOOL_CALLS,
            "max_tokens": FinishReason.LENGTH,
            "stop_sequence": FinishReason.STOP,
        }
        finish_reason = finish_reason_map.get(response.stop_reason, FinishReason.STOP)
        
        # 解析使用量
        usage = None
        if response.usage:
            usage = Usage(
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                total_tokens=response.usage.input_tokens + response.usage.output_tokens,
            )
        
        return LLMResponse(
            content=content,
            finish_reason=finish_reason,
            tool_calls=tool_calls if tool_calls else None,
            usage=usage,
            model=response.model,
            raw_response=response,
        )
    
    async def chat(
        self,
        messages: List[LLMMessage],
        tools: Optional[List["Tool"]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
        **kwargs,
    ) -> LLMResponse:
        """
        对话接口
        
        Args:
            messages: 消息列表
            tools: 可用工具列表
            temperature: 温度参数
            max_tokens: 最大输出token数
            stop: 停止序列
            **kwargs: 其他参数
            
        Returns:
            LLMResponse
        """
        client = self._get_async_client()
        
        # 格式化消息
        system_prompt, formatted_messages = self._format_messages_for_provider(messages)
        
        # 构建请求参数
        request_kwargs = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": temperature,
            "max_tokens": max_tokens or 4096,  # Anthropic要求必须指定
        }
        
        if system_prompt:
            request_kwargs["system"] = system_prompt
        
        if stop:
            request_kwargs["stop_sequences"] = stop
        
        if tools:
            request_kwargs["tools"] = self._format_tools_for_provider(tools)
            # tool_choice可以是auto, any, 或指定工具名
            tool_choice = kwargs.get("tool_choice", "auto")
            if tool_choice != "auto":
                request_kwargs["tool_choice"] = {"type": tool_choice}
        
        # 合并额外参数
        for key in ["top_p", "top_k"]:
            if key in kwargs:
                request_kwargs[key] = kwargs[key]
        
        # 调用API
        response = await client.messages.create(**request_kwargs)
        
        return self._parse_response(response)
    
    async def stream_chat(
        self,
        messages: List[LLMMessage],
        tools: Optional[List["Tool"]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
        **kwargs,
    ) -> AsyncIterator[StreamChunk]:
        """
        流式对话接口
        
        Args:
            messages: 消息列表
            tools: 可用工具列表
            temperature: 温度参数
            max_tokens: 最大输出token数
            stop: 停止序列
            **kwargs: 其他参数
            
        Yields:
            StreamChunk
        """
        client = self._get_async_client()
        
        # 格式化消息
        system_prompt, formatted_messages = self._format_messages_for_provider(messages)
        
        # 构建请求参数
        request_kwargs = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": temperature,
            "max_tokens": max_tokens or 4096,
        }
        
        if system_prompt:
            request_kwargs["system"] = system_prompt
        
        if stop:
            request_kwargs["stop_sequences"] = stop
        
        if tools:
            request_kwargs["tools"] = self._format_tools_for_provider(tools)
        
        # 用于累积工具调用
        tool_calls_accumulator: Dict[str, Dict] = {}
        current_tool_id = None
        
        # 流式调用
        async with client.messages.stream(**request_kwargs) as stream:
            async for event in stream:
                if event.type == "content_block_start":
                    block = event.content_block
                    if block.type == "tool_use":
                        current_tool_id = block.id
                        tool_calls_accumulator[current_tool_id] = {
                            "id": block.id,
                            "name": block.name,
                            "arguments": "",
                        }
                        
                elif event.type == "content_block_delta":
                    delta = event.delta
                    if delta.type == "text_delta":
                        yield StreamChunk(content=delta.text)
                    elif delta.type == "input_json_delta":
                        if current_tool_id:
                            tool_calls_accumulator[current_tool_id]["arguments"] += delta.partial_json
                            
                elif event.type == "message_stop":
                    # 构建最终的工具调用列表
                    tool_calls = None
                    if tool_calls_accumulator:
                        tool_calls = []
                        for tc_data in tool_calls_accumulator.values():
                            arguments = tc_data["arguments"]
                            try:
                                arguments = json.loads(arguments) if arguments else {}
                            except json.JSONDecodeError:
                                arguments = {"raw": arguments}
                            
                            tool_calls.append(ToolCall(
                                id=tc_data["id"],
                                name=tc_data["name"],
                                arguments=arguments,
                            ))
                    
                    # 获取最终响应以确定finish_reason
                    final_response = await stream.get_final_message()
                    finish_reason_map = {
                        "end_turn": FinishReason.STOP,
                        "tool_use": FinishReason.TOOL_CALLS,
                        "max_tokens": FinishReason.LENGTH,
                    }
                    finish_reason = finish_reason_map.get(
                        final_response.stop_reason, 
                        FinishReason.STOP
                    )
                    
                    yield StreamChunk(
                        content="",
                        tool_calls=tool_calls,
                        finish_reason=finish_reason,
                        is_final=True,
                    )
    
    async def count_tokens(self, text: str) -> int:
        """
        估算token数
        
        Anthropic没有公开的tokenizer，使用简单估算。
        
        Args:
            text: 文本
            
        Returns:
            token数
        """
        # Claude的token大约是每4个字符一个token（对于英文）
        # 中文字符大约每个1-2个token
        return len(text) // 3
