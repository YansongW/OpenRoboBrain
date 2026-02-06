"""
OpenAI LLM Provider

支持OpenAI API及兼容API（如DeepSeek、Azure OpenAI等）。
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


class OpenAILLM(BaseLLM):
    """
    OpenAI LLM Provider
    
    支持OpenAI API和兼容API（如Kimi、GLM、Qwen、Doubao、DeepSeek等）。
    """
    
    # 已知的OpenAI兼容端点映射
    KNOWN_ENDPOINTS = {
        "api.moonshot.cn": "kimi",
        "open.bigmodel.cn": "glm",
        "dashscope.aliyuncs.com": "qwen",
        "ark.cn-beijing.volces.com": "doubao",
        "api.deepseek.com": "deepseek",
        "api.lingyiwanwu.com": "yi",
        "api.baichuan-ai.com": "baichuan",
        "api.minimax.chat": "minimax",
    }
    
    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        organization: Optional[str] = None,
        timeout: float = 60.0,
        max_retries: int = 3,
        **kwargs,
    ):
        """
        初始化OpenAI LLM
        
        Args:
            model: 模型名称
            api_key: API密钥
            base_url: API基础URL（用于兼容API）
            organization: 组织ID
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
        self.organization = organization
        self._client: Optional[Any] = None
        self._async_client: Optional[Any] = None
        self._detected_provider: Optional[str] = None
    
    @property
    def provider_name(self) -> str:
        """
        获取provider名称
        
        会根据base_url自动检测实际使用的服务商。
        """
        if self._detected_provider:
            return self._detected_provider
        
        if self.base_url:
            for endpoint, name in self.KNOWN_ENDPOINTS.items():
                if endpoint in self.base_url:
                    self._detected_provider = name
                    return name
        
        return "openai"
    
    @property
    def capabilities(self) -> LLMCapabilities:
        """获取LLM能力"""
        # 根据模型判断能力
        supports_vision = "vision" in self.model or "gpt-4" in self.model
        
        return LLMCapabilities(
            supports_tools=True,
            supports_streaming=True,
            supports_vision=supports_vision,
            supports_json_mode=True,
            max_context_length=128000 if "gpt-4" in self.model else 16384,
            max_output_tokens=16384 if "gpt-4o" in self.model else 4096,
        )
    
    def _get_client(self):
        """获取同步客户端"""
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError:
                raise ImportError(
                    "OpenAI package not installed. "
                    "Install with: pip install openai"
                )
            
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                organization=self.organization,
                timeout=self.timeout,
                max_retries=self.max_retries,
            )
        return self._client
    
    def _get_async_client(self):
        """获取异步客户端"""
        if self._async_client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError:
                raise ImportError(
                    "OpenAI package not installed. "
                    "Install with: pip install openai"
                )
            
            self._async_client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                organization=self.organization,
                timeout=self.timeout,
                max_retries=self.max_retries,
            )
        return self._async_client
    
    def _format_messages_for_provider(self, messages: List[LLMMessage]) -> List[dict]:
        """将消息格式化为OpenAI格式"""
        formatted = []
        for msg in messages:
            message_dict = {
                "role": msg.role.value if isinstance(msg.role, MessageRole) else msg.role,
                "content": msg.content,
            }
            
            # 处理工具调用
            if msg.tool_calls:
                message_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments) if isinstance(tc.arguments, dict) else tc.arguments,
                        }
                    }
                    for tc in msg.tool_calls
                ]
            
            # 处理工具结果
            if msg.tool_call_id:
                message_dict["tool_call_id"] = msg.tool_call_id
            
            if msg.name:
                message_dict["name"] = msg.name
            
            formatted.append(message_dict)
        
        return formatted
    
    def _format_tools_for_provider(self, tools: List["Tool"]) -> List[dict]:
        """将工具格式化为OpenAI格式"""
        return [tool.to_openai_format() for tool in tools]
    
    def _parse_response(self, response) -> LLMResponse:
        """解析OpenAI响应"""
        choice = response.choices[0]
        message = choice.message
        
        # 解析finish_reason
        finish_reason_map = {
            "stop": FinishReason.STOP,
            "tool_calls": FinishReason.TOOL_CALLS,
            "length": FinishReason.LENGTH,
            "content_filter": FinishReason.CONTENT_FILTER,
        }
        finish_reason = finish_reason_map.get(choice.finish_reason, FinishReason.STOP)
        
        # 解析工具调用
        tool_calls = None
        if message.tool_calls:
            tool_calls = []
            for tc in message.tool_calls:
                arguments = tc.function.arguments
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = {"raw": arguments}
                
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=arguments,
                ))
        
        # 解析使用量
        usage = None
        if response.usage:
            usage = Usage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
            )
        
        return LLMResponse(
            content=message.content or "",
            finish_reason=finish_reason,
            tool_calls=tool_calls,
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
        
        # 构建请求参数
        request_kwargs = {
            "model": self.model,
            "messages": self._format_messages_for_provider(messages),
            "temperature": temperature,
        }
        
        if max_tokens:
            request_kwargs["max_tokens"] = max_tokens
        
        if stop:
            request_kwargs["stop"] = stop
        
        if tools:
            request_kwargs["tools"] = self._format_tools_for_provider(tools)
            request_kwargs["tool_choice"] = kwargs.get("tool_choice", "auto")
        
        # 合并额外参数
        for key in ["response_format", "seed", "top_p", "frequency_penalty", "presence_penalty"]:
            if key in kwargs:
                request_kwargs[key] = kwargs[key]
        
        # 调用API
        response = await client.chat.completions.create(**request_kwargs)
        
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
        
        # 构建请求参数
        request_kwargs = {
            "model": self.model,
            "messages": self._format_messages_for_provider(messages),
            "temperature": temperature,
            "stream": True,
        }
        
        if max_tokens:
            request_kwargs["max_tokens"] = max_tokens
        
        if stop:
            request_kwargs["stop"] = stop
        
        if tools:
            request_kwargs["tools"] = self._format_tools_for_provider(tools)
            request_kwargs["tool_choice"] = kwargs.get("tool_choice", "auto")
        
        # 调用API
        stream = await client.chat.completions.create(**request_kwargs)
        
        # 用于累积工具调用
        tool_calls_accumulator: Dict[int, Dict] = {}
        
        async for chunk in stream:
            if not chunk.choices:
                continue
            
            choice = chunk.choices[0]
            delta = choice.delta
            
            # 处理内容
            content = delta.content or ""
            
            # 处理工具调用增量
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_calls_accumulator:
                        tool_calls_accumulator[idx] = {
                            "id": tc_delta.id or "",
                            "name": "",
                            "arguments": "",
                        }
                    
                    if tc_delta.id:
                        tool_calls_accumulator[idx]["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            tool_calls_accumulator[idx]["name"] = tc_delta.function.name
                        if tc_delta.function.arguments:
                            tool_calls_accumulator[idx]["arguments"] += tc_delta.function.arguments
            
            # 解析finish_reason
            finish_reason = None
            is_final = False
            if choice.finish_reason:
                is_final = True
                finish_reason_map = {
                    "stop": FinishReason.STOP,
                    "tool_calls": FinishReason.TOOL_CALLS,
                    "length": FinishReason.LENGTH,
                }
                finish_reason = finish_reason_map.get(choice.finish_reason, FinishReason.STOP)
            
            # 构建工具调用列表
            tool_calls = None
            if is_final and tool_calls_accumulator:
                tool_calls = []
                for idx in sorted(tool_calls_accumulator.keys()):
                    tc_data = tool_calls_accumulator[idx]
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
            
            yield StreamChunk(
                content=content,
                tool_calls=tool_calls,
                finish_reason=finish_reason,
                is_final=is_final,
            )
    
    async def count_tokens(self, text: str) -> int:
        """
        使用tiktoken计算token数
        
        Args:
            text: 文本
            
        Returns:
            token数
        """
        try:
            import tiktoken
            
            # 获取对应模型的编码器
            try:
                encoding = tiktoken.encoding_for_model(self.model)
            except KeyError:
                # 使用默认编码器
                encoding = tiktoken.get_encoding("cl100k_base")
            
            return len(encoding.encode(text))
        except ImportError:
            # tiktoken未安装，使用简单估算
            return len(text) // 4
