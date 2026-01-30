"""
Ollama LLM Provider

支持本地运行的Ollama模型。
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, AsyncIterator, Dict, List, Optional

from kaibrain.system.llm.base import BaseLLM, LLMCapabilities
from kaibrain.system.llm.message import (
    FinishReason,
    LLMMessage,
    LLMResponse,
    MessageRole,
    StreamChunk,
    ToolCall,
    Usage,
)

if TYPE_CHECKING:
    from kaibrain.system.tools.base import Tool


class OllamaLLM(BaseLLM):
    """
    Ollama LLM Provider
    
    支持本地运行的Ollama模型。
    注意：工具调用支持取决于具体模型。
    """
    
    def __init__(
        self,
        model: str = "llama3.2",
        base_url: str = "http://localhost:11434",
        timeout: float = 120.0,
        max_retries: int = 3,
        **kwargs,
    ):
        """
        初始化Ollama LLM
        
        Args:
            model: 模型名称
            base_url: Ollama服务地址
            timeout: 请求超时时间
            max_retries: 最大重试次数
            **kwargs: 其他参数
        """
        super().__init__(
            model=model,
            api_key=None,  # Ollama不需要API key
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            **kwargs,
        )
        self._client: Optional[Any] = None
        self._async_client: Optional[Any] = None
    
    @property
    def provider_name(self) -> str:
        return "ollama"
    
    @property
    def capabilities(self) -> LLMCapabilities:
        """获取LLM能力"""
        # Ollama的能力取决于具体模型
        return LLMCapabilities(
            supports_tools=True,  # 较新的模型支持
            supports_streaming=True,
            supports_vision="llava" in self.model or "vision" in self.model,
            supports_json_mode=True,
            max_context_length=8192,  # 默认值，实际取决于模型
            max_output_tokens=2048,
        )
    
    def _get_async_client(self):
        """获取异步客户端"""
        if self._async_client is None:
            try:
                from ollama import AsyncClient
            except ImportError:
                raise ImportError(
                    "Ollama package not installed. "
                    "Install with: pip install ollama"
                )
            
            self._async_client = AsyncClient(host=self.base_url)
        return self._async_client
    
    def _format_messages_for_provider(self, messages: List[LLMMessage]) -> List[dict]:
        """将消息格式化为Ollama格式"""
        formatted = []
        for msg in messages:
            role = msg.role.value if isinstance(msg.role, MessageRole) else msg.role
            
            message_dict = {
                "role": role,
                "content": msg.content,
            }
            
            # Ollama的工具调用格式
            if msg.tool_calls:
                message_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "function": {
                            "name": tc.name,
                            "arguments": tc.arguments,
                        }
                    }
                    for tc in msg.tool_calls
                ]
            
            formatted.append(message_dict)
        
        return formatted
    
    def _format_tools_for_provider(self, tools: List["Tool"]) -> List[dict]:
        """将工具格式化为Ollama格式"""
        # Ollama使用类似OpenAI的格式
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                }
            }
            for tool in tools
        ]
    
    def _parse_response(self, response: dict) -> LLMResponse:
        """解析Ollama响应"""
        message = response.get("message", {})
        content = message.get("content", "")
        
        # 解析工具调用
        tool_calls = None
        if message.get("tool_calls"):
            tool_calls = []
            for tc in message["tool_calls"]:
                func = tc.get("function", {})
                arguments = func.get("arguments", {})
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = {"raw": arguments}
                
                tool_calls.append(ToolCall(
                    id=tc.get("id", f"call_{len(tool_calls)}"),
                    name=func.get("name", ""),
                    arguments=arguments,
                ))
        
        # 判断finish_reason
        finish_reason = FinishReason.STOP
        if tool_calls:
            finish_reason = FinishReason.TOOL_CALLS
        elif response.get("done_reason") == "length":
            finish_reason = FinishReason.LENGTH
        
        # 解析使用量
        usage = None
        if "prompt_eval_count" in response or "eval_count" in response:
            usage = Usage(
                prompt_tokens=response.get("prompt_eval_count", 0),
                completion_tokens=response.get("eval_count", 0),
                total_tokens=response.get("prompt_eval_count", 0) + response.get("eval_count", 0),
            )
        
        return LLMResponse(
            content=content,
            finish_reason=finish_reason,
            tool_calls=tool_calls,
            usage=usage,
            model=response.get("model", self.model),
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
        options = {
            "temperature": temperature,
        }
        if max_tokens:
            options["num_predict"] = max_tokens
        if stop:
            options["stop"] = stop
        
        request_kwargs = {
            "model": self.model,
            "messages": self._format_messages_for_provider(messages),
            "options": options,
            "stream": False,
        }
        
        if tools:
            request_kwargs["tools"] = self._format_tools_for_provider(tools)
        
        # JSON模式
        if kwargs.get("response_format", {}).get("type") == "json_object":
            request_kwargs["format"] = "json"
        
        # 调用API
        response = await client.chat(**request_kwargs)
        
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
        options = {
            "temperature": temperature,
        }
        if max_tokens:
            options["num_predict"] = max_tokens
        if stop:
            options["stop"] = stop
        
        request_kwargs = {
            "model": self.model,
            "messages": self._format_messages_for_provider(messages),
            "options": options,
            "stream": True,
        }
        
        if tools:
            request_kwargs["tools"] = self._format_tools_for_provider(tools)
        
        # 流式调用
        accumulated_content = ""
        async for chunk in await client.chat(**request_kwargs):
            message = chunk.get("message", {})
            content = message.get("content", "")
            accumulated_content += content
            
            is_done = chunk.get("done", False)
            
            if is_done:
                # 解析工具调用（如果有）
                tool_calls = None
                if message.get("tool_calls"):
                    tool_calls = []
                    for tc in message["tool_calls"]:
                        func = tc.get("function", {})
                        arguments = func.get("arguments", {})
                        if isinstance(arguments, str):
                            try:
                                arguments = json.loads(arguments)
                            except json.JSONDecodeError:
                                arguments = {"raw": arguments}
                        
                        tool_calls.append(ToolCall(
                            id=tc.get("id", f"call_{len(tool_calls)}"),
                            name=func.get("name", ""),
                            arguments=arguments,
                        ))
                
                finish_reason = FinishReason.TOOL_CALLS if tool_calls else FinishReason.STOP
                
                yield StreamChunk(
                    content=content,
                    tool_calls=tool_calls,
                    finish_reason=finish_reason,
                    is_final=True,
                )
            else:
                yield StreamChunk(content=content)
    
    async def list_models(self) -> List[str]:
        """
        列出可用的本地模型
        
        Returns:
            模型名称列表
        """
        client = self._get_async_client()
        response = await client.list()
        return [model["name"] for model in response.get("models", [])]
    
    async def pull_model(self, model: str) -> None:
        """
        拉取模型
        
        Args:
            model: 模型名称
        """
        client = self._get_async_client()
        await client.pull(model)
