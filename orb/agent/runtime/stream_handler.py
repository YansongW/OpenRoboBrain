"""
Stream Handler

流式响应处理器，负责：
- 流式输出事件
- 响应分块
- 事件订阅和分发

借鉴 Moltbot 的流式处理设计。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator, Callable, Dict, List, Optional
from uuid import uuid4

from orb.system.services.logger import LoggerMixin


class StreamEventType(Enum):
    """流事件类型"""
    # 生命周期事件
    LIFECYCLE_START = "lifecycle:start"
    LIFECYCLE_END = "lifecycle:end"
    LIFECYCLE_ERROR = "lifecycle:error"
    
    # 助手事件
    ASSISTANT_DELTA = "assistant:delta"
    ASSISTANT_END = "assistant:end"
    
    # 工具事件
    TOOL_START = "tool:start"
    TOOL_UPDATE = "tool:update"
    TOOL_END = "tool:end"
    
    # 压缩事件
    COMPACTION_START = "compaction:start"
    COMPACTION_END = "compaction:end"
    
    # 其他事件
    STATUS = "status"
    HEARTBEAT = "heartbeat"


@dataclass
class StreamEvent:
    """流事件"""
    id: str = field(default_factory=lambda: str(uuid4()))
    type: StreamEventType = StreamEventType.STATUS
    data: Any = None
    run_id: str = ""
    session_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    sequence: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "type": self.type.value,
            "data": self.data,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "sequence": self.sequence,
            "metadata": self.metadata,
        }


# 类型定义
EventCallback = Callable[[StreamEvent], None]
AsyncEventCallback = Callable[[StreamEvent], Any]


class StreamHandler(LoggerMixin):
    """
    流处理器
    
    管理流式输出事件的发布和订阅。
    """
    
    def __init__(
        self,
        run_id: str = "",
        session_id: str = "",
        buffer_size: int = 100,
    ):
        """
        初始化流处理器
        
        Args:
            run_id: 运行 ID
            session_id: 会话 ID
            buffer_size: 缓冲区大小
        """
        self._run_id = run_id
        self._session_id = session_id
        self._buffer_size = buffer_size
        
        self._sequence = 0
        self._subscribers: List[AsyncEventCallback] = []
        self._event_queue: asyncio.Queue = asyncio.Queue(maxsize=buffer_size)
        self._buffer: List[StreamEvent] = []
        self._is_streaming = False
        
    @property
    def run_id(self) -> str:
        """运行 ID"""
        return self._run_id
        
    @property
    def session_id(self) -> str:
        """会话 ID"""
        return self._session_id
        
    @property
    def is_streaming(self) -> bool:
        """是否正在流式输出"""
        return self._is_streaming
        
    def set_run_context(self, run_id: str, session_id: str) -> None:
        """设置运行上下文"""
        self._run_id = run_id
        self._session_id = session_id
        
    def subscribe(self, callback: AsyncEventCallback) -> None:
        """
        订阅事件
        
        Args:
            callback: 事件回调
        """
        self._subscribers.append(callback)
        
    def unsubscribe(self, callback: AsyncEventCallback) -> None:
        """
        取消订阅
        
        Args:
            callback: 事件回调
        """
        if callback in self._subscribers:
            self._subscribers.remove(callback)
            
    async def emit(
        self,
        event_type: StreamEventType,
        data: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> StreamEvent:
        """
        发射事件
        
        Args:
            event_type: 事件类型
            data: 事件数据
            metadata: 元数据
            
        Returns:
            发射的事件
        """
        self._sequence += 1
        
        event = StreamEvent(
            type=event_type,
            data=data,
            run_id=self._run_id,
            session_id=self._session_id,
            sequence=self._sequence,
            metadata=metadata or {},
        )
        
        # 添加到缓冲区
        self._buffer.append(event)
        if len(self._buffer) > self._buffer_size:
            self._buffer.pop(0)
            
        # 添加到队列（满时丢弃最旧事件腾出空间，避免刷屏警告）
        if self._event_queue.full():
            try:
                self._event_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            self._event_queue.put_nowait(event)
        except asyncio.QueueFull:
            pass  # 极端并发下静默丢弃
            
        # 通知订阅者
        for callback in self._subscribers:
            try:
                result = callback(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                self.logger.warning(f"事件回调失败: {e}")
                
        return event
        
    async def emit_lifecycle_start(
        self,
        phase: str = "start",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> StreamEvent:
        """发射生命周期开始事件"""
        return await self.emit(
            StreamEventType.LIFECYCLE_START,
            {"phase": phase},
            metadata,
        )
        
    async def emit_lifecycle_end(
        self,
        status: str = "success",
        summary: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> StreamEvent:
        """发射生命周期结束事件"""
        return await self.emit(
            StreamEventType.LIFECYCLE_END,
            {"status": status, "summary": summary},
            metadata,
        )
        
    async def emit_lifecycle_error(
        self,
        error: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> StreamEvent:
        """发射生命周期错误事件"""
        return await self.emit(
            StreamEventType.LIFECYCLE_ERROR,
            {"error": error},
            metadata,
        )
        
    async def emit_assistant_delta(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> StreamEvent:
        """发射助手增量事件"""
        self._is_streaming = True
        return await self.emit(
            StreamEventType.ASSISTANT_DELTA,
            {"content": content},
            metadata,
        )
        
    async def emit_assistant_end(
        self,
        full_content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> StreamEvent:
        """发射助手结束事件"""
        self._is_streaming = False
        return await self.emit(
            StreamEventType.ASSISTANT_END,
            {"content": full_content},
            metadata,
        )
        
    async def emit_tool_start(
        self,
        tool_name: str,
        call_id: str,
        arguments: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> StreamEvent:
        """发射工具开始事件"""
        return await self.emit(
            StreamEventType.TOOL_START,
            {
                "tool_name": tool_name,
                "call_id": call_id,
                "arguments": arguments,
            },
            metadata,
        )
        
    async def emit_tool_update(
        self,
        tool_name: str,
        call_id: str,
        progress: Optional[float] = None,
        output: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> StreamEvent:
        """发射工具更新事件"""
        return await self.emit(
            StreamEventType.TOOL_UPDATE,
            {
                "tool_name": tool_name,
                "call_id": call_id,
                "progress": progress,
                "output": output,
            },
            metadata,
        )
        
    async def emit_tool_end(
        self,
        tool_name: str,
        call_id: str,
        result: Any,
        status: str = "success",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> StreamEvent:
        """发射工具结束事件"""
        return await self.emit(
            StreamEventType.TOOL_END,
            {
                "tool_name": tool_name,
                "call_id": call_id,
                "result": result,
                "status": status,
            },
            metadata,
        )
        
    async def events(self) -> AsyncIterator[StreamEvent]:
        """
        异步迭代事件
        
        Yields:
            流事件
        """
        while True:
            try:
                event = await asyncio.wait_for(
                    self._event_queue.get(),
                    timeout=1.0,
                )
                yield event
                
                # 检查是否为结束事件
                if event.type in [
                    StreamEventType.LIFECYCLE_END,
                    StreamEventType.LIFECYCLE_ERROR,
                ]:
                    break
                    
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
                
    def get_buffer(self) -> List[StreamEvent]:
        """获取缓冲区中的事件"""
        return self._buffer.copy()
        
    def clear_buffer(self) -> None:
        """清空缓冲区"""
        self._buffer.clear()
        
    def reset(self) -> None:
        """重置流处理器"""
        self._sequence = 0
        self._buffer.clear()
        self._is_streaming = False
        
        # 清空队列
        while not self._event_queue.empty():
            try:
                self._event_queue.get_nowait()
            except asyncio.QueueEmpty:
                break


class ChunkingConfig:
    """分块配置"""
    
    def __init__(
        self,
        min_chunk_size: int = 800,
        max_chunk_size: int = 1200,
        prefer_paragraph_breaks: bool = True,
        prefer_newline_breaks: bool = True,
        prefer_sentence_breaks: bool = True,
    ):
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
        self.prefer_paragraph_breaks = prefer_paragraph_breaks
        self.prefer_newline_breaks = prefer_newline_breaks
        self.prefer_sentence_breaks = prefer_sentence_breaks


class BlockStreamHandler(StreamHandler):
    """
    分块流处理器
    
    支持将长响应分块发送。
    """
    
    def __init__(
        self,
        chunking_config: Optional[ChunkingConfig] = None,
        **kwargs,
    ):
        """
        初始化分块流处理器
        
        Args:
            chunking_config: 分块配置
            **kwargs: 其他参数
        """
        super().__init__(**kwargs)
        self._chunking_config = chunking_config or ChunkingConfig()
        self._current_block = ""
        
    def _find_break_point(self, text: str, max_length: int) -> int:
        """
        查找合适的断点
        
        Args:
            text: 文本
            max_length: 最大长度
            
        Returns:
            断点位置
        """
        config = self._chunking_config
        
        if len(text) <= max_length:
            return len(text)
            
        search_text = text[:max_length]
        
        # 优先在段落处断开
        if config.prefer_paragraph_breaks:
            para_pos = search_text.rfind("\n\n")
            if para_pos >= config.min_chunk_size:
                return para_pos + 2
                
        # 其次在换行处断开
        if config.prefer_newline_breaks:
            newline_pos = search_text.rfind("\n")
            if newline_pos >= config.min_chunk_size:
                return newline_pos + 1
                
        # 再次在句子处断开
        if config.prefer_sentence_breaks:
            for ending in ["。", "！", "？", ". ", "! ", "? "]:
                sent_pos = search_text.rfind(ending)
                if sent_pos >= config.min_chunk_size:
                    return sent_pos + len(ending)
                    
        # 最后强制在最大长度处断开
        return max_length
        
    async def emit_chunked_content(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[StreamEvent]:
        """
        分块发射内容
        
        Args:
            content: 内容
            metadata: 元数据
            
        Returns:
            发射的事件列表
        """
        events = []
        remaining = content
        
        while remaining:
            break_point = self._find_break_point(
                remaining,
                self._chunking_config.max_chunk_size,
            )
            
            chunk = remaining[:break_point]
            remaining = remaining[break_point:]
            
            event = await self.emit_assistant_delta(chunk, metadata)
            events.append(event)
            
        return events


# 便捷函数
def create_stream_handler(
    run_id: str = "",
    session_id: str = "",
    use_chunking: bool = False,
    **kwargs,
) -> StreamHandler:
    """
    创建流处理器
    
    Args:
        run_id: 运行 ID
        session_id: 会话 ID
        use_chunking: 是否使用分块
        **kwargs: 其他参数
        
    Returns:
        StreamHandler 实例
    """
    if use_chunking:
        return BlockStreamHandler(run_id=run_id, session_id=session_id, **kwargs)
    return StreamHandler(run_id=run_id, session_id=session_id, **kwargs)
