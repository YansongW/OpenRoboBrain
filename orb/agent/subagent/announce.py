"""
Announce Handler

子 Agent 结果回报机制。
借鉴 Moltbot 的 announce 设计。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from orb.system.services.logger import LoggerMixin

if TYPE_CHECKING:
    from orb.agent.subagent.spawn import SpawnResult, SpawnStatus


class AnnounceStatus(Enum):
    """Announce 状态"""
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"


@dataclass
class AnnounceMessage:
    """Announce 消息"""
    spawn_id: str
    status: AnnounceStatus
    summary: str = ""
    result: Optional[str] = None
    error: Optional[str] = None
    notes: Optional[str] = None
    
    # 统计信息
    runtime_seconds: float = 0
    tokens_used: int = 0
    
    # 会话信息
    session_key: str = ""
    session_id: str = ""
    transcript_path: Optional[str] = None
    
    # 元数据
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def format(self) -> str:
        """
        格式化为可读消息
        
        Returns:
            格式化的消息
        """
        lines = []
        
        # 状态
        lines.append(f"Status: {self.status.value}")
        
        # 结果
        if self.result:
            lines.append(f"Result: {self.result}")
        else:
            lines.append("Result: (not available)")
            
        # 错误信息
        if self.error:
            lines.append(f"Notes: {self.error}")
        elif self.notes:
            lines.append(f"Notes: {self.notes}")
            
        # 统计
        stats_parts = []
        if self.runtime_seconds > 0:
            if self.runtime_seconds >= 60:
                minutes = int(self.runtime_seconds // 60)
                seconds = int(self.runtime_seconds % 60)
                stats_parts.append(f"runtime {minutes}m{seconds}s")
            else:
                stats_parts.append(f"runtime {self.runtime_seconds:.1f}s")
                
        if self.tokens_used > 0:
            stats_parts.append(f"tokens {self.tokens_used}")
            
        if stats_parts:
            lines.append(" | ".join(stats_parts))
            
        # 会话信息
        if self.session_key:
            lines.append(f"sessionKey: {self.session_key}")
        if self.session_id:
            lines.append(f"sessionId: {self.session_id}")
            
        return "\n".join(lines)
        
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "spawn_id": self.spawn_id,
            "status": self.status.value,
            "summary": self.summary,
            "result": self.result,
            "error": self.error,
            "notes": self.notes,
            "runtime_seconds": self.runtime_seconds,
            "tokens_used": self.tokens_used,
            "session_key": self.session_key,
            "session_id": self.session_id,
            "transcript_path": self.transcript_path,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


# 类型定义
AnnounceCallback = Callable[[AnnounceMessage], Any]


class AnnounceHandler(LoggerMixin):
    """
    Announce 处理器
    
    负责处理子 Agent 的结果回报。
    """
    
    # 跳过 announce 的特殊标记
    SKIP_TOKEN = "ANNOUNCE_SKIP"
    
    def __init__(self):
        """初始化 Announce 处理器"""
        self._callbacks: List[AnnounceCallback] = []
        self._pending_announces: Dict[str, AnnounceMessage] = {}
        self._history: List[AnnounceMessage] = []
        self._max_history = 100
        
    def register_callback(self, callback: AnnounceCallback) -> None:
        """
        注册回调
        
        Args:
            callback: 回调函数
        """
        self._callbacks.append(callback)
        
    def unregister_callback(self, callback: AnnounceCallback) -> None:
        """
        注销回调
        
        Args:
            callback: 回调函数
        """
        if callback in self._callbacks:
            self._callbacks.remove(callback)
            
    async def announce(
        self,
        spawn_result: SpawnResult,
        summary: Optional[str] = None,
    ) -> AnnounceMessage:
        """
        发送 announce
        
        Args:
            spawn_result: 派生结果
            summary: 摘要（如果为 None，使用响应）
            
        Returns:
            Announce 消息
        """
        from orb.agent.subagent.spawn import SpawnStatus
        
        # 确定状态
        if spawn_result.status == SpawnStatus.COMPLETED:
            status = AnnounceStatus.SUCCESS
        elif spawn_result.status == SpawnStatus.TIMEOUT:
            status = AnnounceStatus.TIMEOUT
        elif spawn_result.status == SpawnStatus.ERROR:
            status = AnnounceStatus.ERROR
        else:
            status = AnnounceStatus.ERROR
            
        # 提取结果
        result = spawn_result.response
        
        # 检查是否跳过
        if result and result.strip() == self.SKIP_TOKEN:
            status = AnnounceStatus.SKIPPED
            result = None
            
        # 创建 announce 消息
        message = AnnounceMessage(
            spawn_id=spawn_result.spawn_id,
            status=status,
            summary=summary or "",
            result=result,
            error=spawn_result.error,
            runtime_seconds=spawn_result.runtime_seconds,
            tokens_used=spawn_result.tokens_used,
            session_key=spawn_result.child_session_key,
            session_id=spawn_result.child_session_id,
            metadata=spawn_result.metadata,
        )
        
        # 跳过的 announce 不发送
        if status == AnnounceStatus.SKIPPED:
            self.logger.debug(f"Announce 跳过: {message.spawn_id}")
            return message
            
        # 发送到回调
        await self._dispatch(message)
        
        # 保存历史
        self._add_to_history(message)
        
        self.logger.info(f"Announce 发送: {message.spawn_id} ({status.value})")
        return message
        
    async def _dispatch(self, message: AnnounceMessage) -> None:
        """分发 announce 消息"""
        for callback in self._callbacks:
            try:
                result = callback(message)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                self.logger.warning(f"Announce 回调失败: {e}")
                
    def _add_to_history(self, message: AnnounceMessage) -> None:
        """添加到历史"""
        self._history.append(message)
        if len(self._history) > self._max_history:
            self._history.pop(0)
            
    def get_history(
        self,
        limit: int = 10,
        spawn_id: Optional[str] = None,
    ) -> List[AnnounceMessage]:
        """
        获取历史
        
        Args:
            limit: 限制数量
            spawn_id: 过滤 spawn ID
            
        Returns:
            Announce 消息列表
        """
        history = self._history
        
        if spawn_id:
            history = [m for m in history if m.spawn_id == spawn_id]
            
        return history[-limit:]
        
    def create_announce_from_spawn(
        self,
        spawn_result: SpawnResult,
    ) -> AnnounceMessage:
        """
        从派生结果创建 announce 消息（不发送）
        
        Args:
            spawn_result: 派生结果
            
        Returns:
            Announce 消息
        """
        from orb.agent.subagent.spawn import SpawnStatus
        
        status_map = {
            SpawnStatus.COMPLETED: AnnounceStatus.SUCCESS,
            SpawnStatus.ERROR: AnnounceStatus.ERROR,
            SpawnStatus.TIMEOUT: AnnounceStatus.TIMEOUT,
        }
        
        status = status_map.get(spawn_result.status, AnnounceStatus.ERROR)
        
        return AnnounceMessage(
            spawn_id=spawn_result.spawn_id,
            status=status,
            result=spawn_result.response,
            error=spawn_result.error,
            runtime_seconds=spawn_result.runtime_seconds,
            tokens_used=spawn_result.tokens_used,
            session_key=spawn_result.child_session_key,
            session_id=spawn_result.child_session_id,
            metadata=spawn_result.metadata,
        )
        
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        status_counts = {}
        for status in AnnounceStatus:
            status_counts[status.value] = sum(
                1 for m in self._history if m.status == status
            )
            
        return {
            "total_history": len(self._history),
            "status_counts": status_counts,
            "callbacks_count": len(self._callbacks),
        }
