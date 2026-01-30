"""
LLM抽象基类

定义所有LLM Provider必须实现的接口。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, AsyncIterator, Dict, List, Optional

from kaibrain.system.llm.message import (
    LLMMessage,
    LLMResponse,
    StreamChunk,
    ToolCall,
)
from kaibrain.system.services.logger import LoggerMixin

if TYPE_CHECKING:
    from kaibrain.system.tools.base import Tool


@dataclass
class LLMCapabilities:
    """LLM能力描述"""
    supports_tools: bool = True           # 支持工具调用
    supports_streaming: bool = True       # 支持流式输出
    supports_vision: bool = False         # 支持图像输入
    supports_json_mode: bool = False      # 支持JSON模式输出
    max_context_length: int = 128000      # 最大上下文长度
    max_output_tokens: int = 4096         # 最大输出token数


class BaseLLM(ABC, LoggerMixin):
    """
    LLM抽象基类
    
    所有LLM Provider都需要继承此类并实现抽象方法。
    """
    
    def __init__(
        self,
        model: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 60.0,
        max_retries: int = 3,
        **kwargs,
    ):
        """
        初始化LLM
        
        Args:
            model: 模型名称
            api_key: API密钥
            base_url: API基础URL（用于兼容API）
            timeout: 请求超时时间
            max_retries: 最大重试次数
            **kwargs: 其他参数
        """
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self._extra_config = kwargs
        
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider名称"""
        pass
    
    @property
    def capabilities(self) -> LLMCapabilities:
        """获取LLM能力"""
        return LLMCapabilities()
    
    @abstractmethod
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
        pass
    
    @abstractmethod
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
        pass
    
    async def chat_with_tools(
        self,
        messages: List[LLMMessage],
        tools: List["Tool"],
        tool_executor: "ToolExecutor",
        max_iterations: int = 10,
        **kwargs,
    ) -> LLMResponse:
        """
        带工具调用的对话（自动执行工具）
        
        这是一个便捷方法，会自动处理工具调用循环。
        
        Args:
            messages: 消息列表
            tools: 可用工具列表
            tool_executor: 工具执行器
            max_iterations: 最大迭代次数
            **kwargs: 其他参数
            
        Returns:
            最终的LLMResponse
        """
        current_messages = list(messages)
        
        for _ in range(max_iterations):
            response = await self.chat(
                messages=current_messages,
                tools=tools,
                **kwargs,
            )
            
            # 如果没有工具调用，直接返回
            if not response.has_tool_calls:
                return response
            
            # 添加助手消息
            current_messages.append(LLMMessage.assistant(
                content=response.content or "",
                tool_calls=response.tool_calls,
            ))
            
            # 执行工具调用
            for tool_call in response.tool_calls:
                result = await tool_executor.execute(tool_call)
                current_messages.append(LLMMessage.tool(
                    tool_call_id=tool_call.id,
                    content=str(result.content),
                    name=tool_call.name,
                ))
        
        # 达到最大迭代次数
        return await self.chat(messages=current_messages, **kwargs)
    
    def _format_tools_for_provider(self, tools: List["Tool"]) -> List[dict]:
        """
        将工具格式化为Provider特定格式
        
        子类可以重写此方法以适应不同Provider的格式要求。
        
        Args:
            tools: 工具列表
            
        Returns:
            格式化后的工具定义列表
        """
        return [tool.to_openai_format() for tool in tools]
    
    def _format_messages_for_provider(self, messages: List[LLMMessage]) -> List[dict]:
        """
        将消息格式化为Provider特定格式
        
        子类可以重写此方法以适应不同Provider的格式要求。
        
        Args:
            messages: 消息列表
            
        Returns:
            格式化后的消息列表
        """
        return [msg.to_dict() for msg in messages]
    
    async def count_tokens(self, text: str) -> int:
        """
        估算文本的token数
        
        Args:
            text: 文本
            
        Returns:
            token数
        """
        # 默认实现：简单估算
        return len(text) // 4
    
    async def count_messages_tokens(self, messages: List[LLMMessage]) -> int:
        """
        估算消息列表的token数
        
        Args:
            messages: 消息列表
            
        Returns:
            token数
        """
        total = 0
        for msg in messages:
            total += await self.count_tokens(msg.content)
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    total += await self.count_tokens(str(tc.arguments))
        return total
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(model={self.model!r}, provider={self.provider_name!r})"


# 类型别名，用于类型检查
if TYPE_CHECKING:
    from kaibrain.system.tools.executor import ToolExecutor
