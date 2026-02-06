"""
Session Store

管理 Agent 的会话历史和路由状态。
借鉴 OpenClaw/Moltbot 的设计，使用 JSONL 格式存储会话记录。

特性:
- JSONL 格式会话转录
- 会话元数据管理
- Reset 策略 (daily, idle, manual)
- 会话压缩 (compaction)
- 写锁控制
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, AsyncIterator, Union
from uuid import uuid4

from orb.system.services.logger import LoggerMixin


class SessionState(Enum):
    """会话状态"""
    CREATED = "created"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPACTING = "compacting"
    CLOSED = "closed"
    ARCHIVED = "archived"


class MessageRole(Enum):
    """消息角色"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ResetMode(Enum):
    """重置模式"""
    DAILY = "daily"     # 每日重置
    IDLE = "idle"       # 空闲超时重置
    MANUAL = "manual"   # 仅手动重置
    NEVER = "never"     # 不自动重置


@dataclass
class ResetPolicy:
    """重置策略"""
    mode: ResetMode = ResetMode.DAILY
    at_hour: int = 4            # 每日重置时间（小时，0-23）
    idle_minutes: int = 120     # 空闲超时分钟数
    triggers: List[str] = field(default_factory=lambda: ["/new", "/reset"])
    
    def should_reset(
        self,
        last_activity: Optional[datetime],
        now: Optional[datetime] = None,
    ) -> bool:
        """
        检查是否需要重置
        
        Args:
            last_activity: 最后活动时间
            now: 当前时间（默认 now()）
            
        Returns:
            是否需要重置
        """
        if not last_activity:
            return False
            
        now = now or datetime.now()
        
        if self.mode == ResetMode.NEVER:
            return False
            
        if self.mode == ResetMode.MANUAL:
            return False
            
        if self.mode == ResetMode.DAILY:
            # 检查是否过了每日重置时间
            reset_time_today = now.replace(
                hour=self.at_hour, minute=0, second=0, microsecond=0
            )
            if now.hour < self.at_hour:
                # 还没到今天的重置时间，检查昨天的
                reset_time_today -= timedelta(days=1)
            return last_activity < reset_time_today
            
        if self.mode == ResetMode.IDLE:
            # 检查空闲时间
            idle_threshold = timedelta(minutes=self.idle_minutes)
            return (now - last_activity) > idle_threshold
            
        return False
        
    def is_reset_trigger(self, message: str) -> bool:
        """
        检查消息是否为重置触发器
        
        Args:
            message: 消息内容
            
        Returns:
            是否为重置触发器
        """
        message_lower = message.strip().lower()
        for trigger in self.triggers:
            if message_lower.startswith(trigger.lower()):
                return True
        return False


@dataclass
class SessionMessage:
    """会话消息"""
    id: str = field(default_factory=lambda: str(uuid4()))
    role: MessageRole = MessageRole.USER
    content: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    tool_result: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp,
            "tool_call_id": self.tool_call_id,
            "tool_name": self.tool_name,
            "tool_result": self.tool_result,
            "metadata": self.metadata,
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SessionMessage:
        """从字典创建"""
        return cls(
            id=data.get("id", str(uuid4())),
            role=MessageRole(data.get("role", "user")),
            content=data.get("content", ""),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            tool_call_id=data.get("tool_call_id"),
            tool_name=data.get("tool_name"),
            tool_result=data.get("tool_result"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class SessionMetadata:
    """会话元数据"""
    session_id: str
    session_key: str  # 格式: agent:<agentId>:<mainKey> 或 agent:<agentId>:subagent:<uuid>
    agent_id: str
    state: SessionState = SessionState.CREATED
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    last_activity_at: Optional[str] = None  # 最后活动时间
    message_count: int = 0
    token_count: int = 0
    input_tokens: int = 0   # 输入 token 数
    output_tokens: int = 0  # 输出 token 数
    model: Optional[str] = None
    channel: Optional[str] = None
    peer_id: Optional[str] = None
    parent_session_id: Optional[str] = None  # 对于 sub-agent
    routing_info: Dict[str, Any] = field(default_factory=dict)
    origin: Dict[str, Any] = field(default_factory=dict)  # 会话来源信息
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def last_activity(self) -> Optional[datetime]:
        """获取最后活动时间"""
        if self.last_activity_at:
            return datetime.fromisoformat(self.last_activity_at)
        if self.updated_at:
            return datetime.fromisoformat(self.updated_at)
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "session_id": self.session_id,
            "session_key": self.session_key,
            "agent_id": self.agent_id,
            "state": self.state.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "last_activity_at": self.last_activity_at,
            "message_count": self.message_count,
            "token_count": self.token_count,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "model": self.model,
            "channel": self.channel,
            "peer_id": self.peer_id,
            "parent_session_id": self.parent_session_id,
            "routing_info": self.routing_info,
            "origin": self.origin,
            "metadata": self.metadata,
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SessionMetadata:
        """从字典创建"""
        return cls(
            session_id=data.get("session_id", ""),
            session_key=data.get("session_key", ""),
            agent_id=data.get("agent_id", ""),
            state=SessionState(data.get("state", "created")),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            started_at=data.get("started_at"),
            ended_at=data.get("ended_at"),
            last_activity_at=data.get("last_activity_at"),
            message_count=data.get("message_count", 0),
            token_count=data.get("token_count", 0),
            input_tokens=data.get("input_tokens", 0),
            output_tokens=data.get("output_tokens", 0),
            model=data.get("model"),
            channel=data.get("channel"),
            peer_id=data.get("peer_id"),
            parent_session_id=data.get("parent_session_id"),
            routing_info=data.get("routing_info", {}),
            origin=data.get("origin", {}),
            metadata=data.get("metadata", {}),
        )


@dataclass
class Session:
    """会话对象"""
    metadata: SessionMetadata
    messages: List[SessionMessage] = field(default_factory=list)
    
    @property
    def session_id(self) -> str:
        return self.metadata.session_id
        
    @property
    def is_active(self) -> bool:
        return self.metadata.state == SessionState.ACTIVE


class SessionStore(LoggerMixin):
    """
    会话存储
    
    管理单个 Agent 的所有会话，支持：
    - JSONL 格式存储
    - 会话元数据管理
    - 消息追加和查询
    - 会话压缩 (compaction)
    - 写锁控制
    - Reset 策略
    """
    
    def __init__(
        self,
        sessions_dir: Path,
        agent_id: str,
        reset_policy: Optional[ResetPolicy] = None,
        main_key: str = "main",
    ):
        """
        初始化会话存储
        
        Args:
            sessions_dir: 会话存储目录
            agent_id: Agent ID
            reset_policy: 重置策略
            main_key: 主会话键
        """
        self._sessions_dir = sessions_dir
        self._agent_id = agent_id
        self._reset_policy = reset_policy or ResetPolicy()
        self._main_key = main_key
        
        # 缓存
        self._sessions: Dict[str, Session] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._metadata_cache: Dict[str, SessionMetadata] = {}
        
        # 会话键到ID的映射
        self._key_to_id: Dict[str, str] = {}
        
        # 确保目录存在
        self._sessions_dir.mkdir(parents=True, exist_ok=True)
        
        # 加载现有会话索引
        self._load_session_index()
        
    @property
    def sessions_dir(self) -> Path:
        """会话目录"""
        return self._sessions_dir
        
    @property
    def agent_id(self) -> str:
        """Agent ID"""
        return self._agent_id
        
    @property
    def reset_policy(self) -> ResetPolicy:
        """重置策略"""
        return self._reset_policy
        
    @reset_policy.setter
    def reset_policy(self, policy: ResetPolicy) -> None:
        """设置重置策略"""
        self._reset_policy = policy
        
    @property
    def main_key(self) -> str:
        """主会话键"""
        return self._main_key
        
    def _load_session_index(self) -> None:
        """加载会话索引"""
        if not self._sessions_dir.exists():
            return
            
        for meta_file in self._sessions_dir.glob("*.meta.json"):
            try:
                meta_data = json.loads(meta_file.read_text(encoding="utf-8"))
                session_key = meta_data.get("session_key", "")
                session_id = meta_data.get("session_id", "")
                if session_key and session_id:
                    self._key_to_id[session_key] = session_id
            except Exception as e:
                self.logger.warning(f"加载会话索引失败 {meta_file}: {e}")
        
    def _get_session_path(self, session_id: str) -> Path:
        """获取会话文件路径"""
        return self._sessions_dir / f"{session_id}.jsonl"
        
    def _get_metadata_path(self, session_id: str) -> Path:
        """获取元数据文件路径"""
        return self._sessions_dir / f"{session_id}.meta.json"
        
    def _get_index_path(self) -> Path:
        """获取索引文件路径"""
        return self._sessions_dir / "sessions.json"
        
    def _get_lock(self, session_id: str) -> asyncio.Lock:
        """获取会话锁"""
        if session_id not in self._locks:
            self._locks[session_id] = asyncio.Lock()
        return self._locks[session_id]
        
    async def _save_index(self) -> None:
        """保存会话索引"""
        index_path = self._get_index_path()
        index_data = {
            "agent_id": self._agent_id,
            "updated_at": datetime.now().isoformat(),
            "sessions": self._key_to_id,
        }
        index_path.write_text(
            json.dumps(index_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        
    @staticmethod
    def generate_session_key(
        agent_id: str,
        main_key: str = "main",
        is_subagent: bool = False,
        subagent_id: Optional[str] = None,
    ) -> str:
        """
        生成会话键
        
        Args:
            agent_id: Agent ID
            main_key: 主键
            is_subagent: 是否为子 Agent
            subagent_id: 子 Agent ID
            
        Returns:
            会话键
        """
        if is_subagent:
            sub_id = subagent_id or str(uuid4())
            return f"agent:{agent_id}:subagent:{sub_id}"
        return f"agent:{agent_id}:{main_key}"
        
    async def create_session(
        self,
        session_key: Optional[str] = None,
        channel: Optional[str] = None,
        peer_id: Optional[str] = None,
        model: Optional[str] = None,
        parent_session_id: Optional[str] = None,
        origin: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Session:
        """
        创建新会话
        
        Args:
            session_key: 会话键
            channel: 通道
            peer_id: 对端 ID
            model: 模型
            parent_session_id: 父会话 ID
            origin: 会话来源信息
            metadata: 额外元数据
            
        Returns:
            新会话
        """
        session_id = str(uuid4())
        now = datetime.now().isoformat()
        
        if session_key is None:
            session_key = self.generate_session_key(self._agent_id)
            
        session_meta = SessionMetadata(
            session_id=session_id,
            session_key=session_key,
            agent_id=self._agent_id,
            state=SessionState.CREATED,
            last_activity_at=now,
            channel=channel,
            peer_id=peer_id,
            model=model,
            parent_session_id=parent_session_id,
            origin=origin or {},
            metadata=metadata or {},
        )
        
        session = Session(metadata=session_meta)
        self._sessions[session_id] = session
        self._metadata_cache[session_id] = session_meta
        self._key_to_id[session_key] = session_id
        
        # 保存元数据和索引
        await self._save_metadata(session_id)
        await self._save_index()
        
        self.logger.info(f"创建会话: {session_id} (key: {session_key})")
        return session
        
    async def get_session(self, session_id: str) -> Optional[Session]:
        """
        获取会话
        
        Args:
            session_id: 会话 ID
            
        Returns:
            会话对象
        """
        # 先检查缓存
        if session_id in self._sessions:
            return self._sessions[session_id]
            
        # 从文件加载
        return await self.load_session(session_id)
        
    async def load_session(self, session_id: str) -> Optional[Session]:
        """
        从文件加载会话
        
        Args:
            session_id: 会话 ID
            
        Returns:
            会话对象
        """
        session_path = self._get_session_path(session_id)
        metadata_path = self._get_metadata_path(session_id)
        
        if not metadata_path.exists():
            return None
            
        try:
            # 加载元数据
            meta_data = json.loads(metadata_path.read_text(encoding="utf-8"))
            session_meta = SessionMetadata.from_dict(meta_data)
            
            # 加载消息
            messages = []
            if session_path.exists():
                with open(session_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            msg_data = json.loads(line)
                            messages.append(SessionMessage.from_dict(msg_data))
                            
            session = Session(metadata=session_meta, messages=messages)
            self._sessions[session_id] = session
            self._metadata_cache[session_id] = session_meta
            
            return session
            
        except Exception as e:
            self.logger.error(f"加载会话失败 {session_id}: {e}")
            return None
            
    async def _save_metadata(self, session_id: str) -> None:
        """保存会话元数据"""
        if session_id not in self._metadata_cache:
            return
            
        metadata = self._metadata_cache[session_id]
        metadata.updated_at = datetime.now().isoformat()
        
        metadata_path = self._get_metadata_path(session_id)
        metadata_path.write_text(
            json.dumps(metadata.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        
    async def append_message(
        self,
        session_id: str,
        message: SessionMessage,
    ) -> bool:
        """
        追加消息到会话
        
        Args:
            session_id: 会话 ID
            message: 消息
            
        Returns:
            是否成功
        """
        async with self._get_lock(session_id):
            session = await self.get_session(session_id)
            if not session:
                self.logger.warning(f"会话不存在: {session_id}")
                return False
                
            now = datetime.now().isoformat()
            
            # 追加到内存
            session.messages.append(message)
            session.metadata.message_count += 1
            session.metadata.updated_at = now
            session.metadata.last_activity_at = now
            
            # 如果是用户消息，标记为活跃
            if message.role == MessageRole.USER:
                if session.metadata.state == SessionState.CREATED:
                    session.metadata.state = SessionState.ACTIVE
                    session.metadata.started_at = now
            
            # 追加到文件
            session_path = self._get_session_path(session_id)
            with open(session_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(message.to_dict(), ensure_ascii=False) + "\n")
                
            # 更新元数据
            await self._save_metadata(session_id)
            
            return True
            
    async def append_messages(
        self,
        session_id: str,
        messages: List[SessionMessage],
    ) -> bool:
        """
        批量追加消息
        
        Args:
            session_id: 会话 ID
            messages: 消息列表
            
        Returns:
            是否成功
        """
        async with self._get_lock(session_id):
            session = await self.get_session(session_id)
            if not session:
                return False
                
            # 追加到内存
            session.messages.extend(messages)
            session.metadata.message_count += len(messages)
            session.metadata.updated_at = datetime.now().isoformat()
            
            # 追加到文件
            session_path = self._get_session_path(session_id)
            with open(session_path, "a", encoding="utf-8") as f:
                for msg in messages:
                    f.write(json.dumps(msg.to_dict(), ensure_ascii=False) + "\n")
                    
            await self._save_metadata(session_id)
            
            return True
            
    async def get_messages(
        self,
        session_id: str,
        limit: Optional[int] = None,
        offset: int = 0,
        roles: Optional[List[MessageRole]] = None,
    ) -> List[SessionMessage]:
        """
        获取会话消息
        
        Args:
            session_id: 会话 ID
            limit: 限制数量
            offset: 偏移量
            roles: 过滤角色
            
        Returns:
            消息列表
        """
        session = await self.get_session(session_id)
        if not session:
            return []
            
        messages = session.messages
        
        # 角色过滤
        if roles:
            messages = [m for m in messages if m.role in roles]
            
        # 分页
        if offset:
            messages = messages[offset:]
        if limit:
            messages = messages[:limit]
            
        return messages
        
    async def get_recent_messages(
        self,
        session_id: str,
        count: int = 10,
    ) -> List[SessionMessage]:
        """
        获取最近的消息
        
        Args:
            session_id: 会话 ID
            count: 数量
            
        Returns:
            消息列表
        """
        session = await self.get_session(session_id)
        if not session:
            return []
            
        return session.messages[-count:]
        
    async def update_session_state(
        self,
        session_id: str,
        state: SessionState,
    ) -> bool:
        """
        更新会话状态
        
        Args:
            session_id: 会话 ID
            state: 新状态
            
        Returns:
            是否成功
        """
        async with self._get_lock(session_id):
            if session_id not in self._metadata_cache:
                return False
                
            metadata = self._metadata_cache[session_id]
            old_state = metadata.state
            metadata.state = state
            metadata.updated_at = datetime.now().isoformat()
            
            # 记录状态变更时间
            if state == SessionState.ACTIVE and not metadata.started_at:
                metadata.started_at = datetime.now().isoformat()
            elif state == SessionState.CLOSED:
                metadata.ended_at = datetime.now().isoformat()
                
            await self._save_metadata(session_id)
            
            self.logger.debug(f"会话状态更新: {session_id} {old_state} -> {state}")
            return True
            
    async def update_token_count(
        self,
        session_id: str,
        tokens: int,
    ) -> None:
        """
        更新 token 计数
        
        Args:
            session_id: 会话 ID
            tokens: token 数量
        """
        if session_id in self._metadata_cache:
            self._metadata_cache[session_id].token_count += tokens
            await self._save_metadata(session_id)
            
    async def close_session(self, session_id: str) -> bool:
        """
        关闭会话
        
        Args:
            session_id: 会话 ID
            
        Returns:
            是否成功
        """
        return await self.update_session_state(session_id, SessionState.CLOSED)
        
    async def archive_session(self, session_id: str) -> bool:
        """
        归档会话
        
        Args:
            session_id: 会话 ID
            
        Returns:
            是否成功
        """
        async with self._get_lock(session_id):
            if not await self.update_session_state(session_id, SessionState.ARCHIVED):
                return False
                
            # 重命名文件
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            
            session_path = self._get_session_path(session_id)
            if session_path.exists():
                archived_path = session_path.with_suffix(f".archived.{timestamp}.jsonl")
                session_path.rename(archived_path)
                
            metadata_path = self._get_metadata_path(session_id)
            if metadata_path.exists():
                archived_meta = metadata_path.with_suffix(f".archived.{timestamp}.json")
                metadata_path.rename(archived_meta)
                
            # 从缓存移除
            self._sessions.pop(session_id, None)
            self._metadata_cache.pop(session_id, None)
            
            self.logger.info(f"会话已归档: {session_id}")
            return True
            
    async def delete_session(self, session_id: str) -> bool:
        """
        删除会话（实际是归档）
        
        Args:
            session_id: 会话 ID
            
        Returns:
            是否成功
        """
        return await self.archive_session(session_id)
        
    def list_sessions(
        self,
        state: Optional[SessionState] = None,
        channel: Optional[str] = None,
    ) -> List[SessionMetadata]:
        """
        列出会话
        
        Args:
            state: 过滤状态
            channel: 过滤通道
            
        Returns:
            会话元数据列表
        """
        # 加载所有元数据
        sessions = []
        
        if self._sessions_dir.exists():
            for meta_file in self._sessions_dir.glob("*.meta.json"):
                try:
                    meta_data = json.loads(meta_file.read_text(encoding="utf-8"))
                    metadata = SessionMetadata.from_dict(meta_data)
                    
                    # 过滤
                    if state and metadata.state != state:
                        continue
                    if channel and metadata.channel != channel:
                        continue
                        
                    sessions.append(metadata)
                    
                except Exception as e:
                    self.logger.warning(f"加载元数据失败 {meta_file}: {e}")
                    
        return sessions
        
    def get_active_sessions(self) -> List[SessionMetadata]:
        """获取活跃会话"""
        return self.list_sessions(state=SessionState.ACTIVE)
        
    async def find_session_by_key(self, session_key: str) -> Optional[Session]:
        """
        通过会话键查找会话
        
        Args:
            session_key: 会话键
            
        Returns:
            会话对象
        """
        for metadata in self.list_sessions():
            if metadata.session_key == session_key:
                return await self.get_session(metadata.session_id)
        return None
        
    async def get_or_create_session(
        self,
        session_key: str,
        **kwargs,
    ) -> Session:
        """
        获取或创建会话
        
        Args:
            session_key: 会话键
            **kwargs: 创建参数
            
        Returns:
            会话对象
        """
        session = await self.find_session_by_key(session_key)
        if session:
            return session
        return await self.create_session(session_key=session_key, **kwargs)
        
    async def compact_session(
        self,
        session_id: str,
        compacted_messages: List[SessionMessage],
    ) -> bool:
        """
        压缩会话（替换消息列表）
        
        Args:
            session_id: 会话 ID
            compacted_messages: 压缩后的消息列表
            
        Returns:
            是否成功
        """
        async with self._get_lock(session_id):
            session = await self.get_session(session_id)
            if not session:
                return False
                
            # 更新状态
            old_state = session.metadata.state
            session.metadata.state = SessionState.COMPACTING
            
            # 备份原文件
            session_path = self._get_session_path(session_id)
            if session_path.exists():
                backup_path = session_path.with_suffix(".backup.jsonl")
                session_path.rename(backup_path)
                
            # 写入压缩后的消息
            try:
                with open(session_path, "w", encoding="utf-8") as f:
                    for msg in compacted_messages:
                        f.write(json.dumps(msg.to_dict(), ensure_ascii=False) + "\n")
                        
                # 更新内存
                session.messages = compacted_messages
                session.metadata.message_count = len(compacted_messages)
                session.metadata.state = old_state
                session.metadata.metadata["last_compaction"] = datetime.now().isoformat()
                
                await self._save_metadata(session_id)
                
                # 删除备份
                backup_path = session_path.with_suffix(".backup.jsonl")
                if backup_path.exists():
                    backup_path.unlink()
                    
                self.logger.info(f"会话压缩完成: {session_id}")
                return True
                
            except Exception as e:
                # 恢复备份
                backup_path = session_path.with_suffix(".backup.jsonl")
                if backup_path.exists():
                    backup_path.rename(session_path)
                self.logger.error(f"会话压缩失败: {e}")
                return False
                
    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息
        
        Returns:
            统计信息
        """
        all_sessions = self.list_sessions()
        
        state_counts = {}
        for state in SessionState:
            state_counts[state.value] = sum(
                1 for s in all_sessions if s.state == state
            )
            
        total_messages = sum(s.message_count for s in all_sessions)
        total_tokens = sum(s.token_count for s in all_sessions)
        
        return {
            "agent_id": self._agent_id,
            "total_sessions": len(all_sessions),
            "cached_sessions": len(self._sessions),
            "state_counts": state_counts,
            "total_messages": total_messages,
            "total_tokens": total_tokens,
        }
        
    async def check_and_reset_session(
        self,
        session_key: str,
        user_input: Optional[str] = None,
    ) -> tuple[Session, bool]:
        """
        检查并在需要时重置会话
        
        Args:
            session_key: 会话键
            user_input: 用户输入（用于检查重置触发器）
            
        Returns:
            (会话对象, 是否重置)
        """
        # 检查是否存在现有会话
        existing = await self.find_session_by_key(session_key)
        
        if not existing:
            # 不存在，创建新会话
            session = await self.create_session(session_key=session_key)
            return session, True
            
        # 检查手动重置触发器
        if user_input and self._reset_policy.is_reset_trigger(user_input):
            self.logger.info(f"检测到重置触发器，重置会话: {session_key}")
            await self.archive_session(existing.session_id)
            session = await self.create_session(session_key=session_key)
            return session, True
            
        # 检查自动重置策略
        if self._reset_policy.should_reset(existing.metadata.last_activity):
            self.logger.info(f"会话过期，重置: {session_key}")
            await self.archive_session(existing.session_id)
            session = await self.create_session(session_key=session_key)
            return session, True
            
        # 返回现有会话
        return existing, False
        
    async def get_main_session(self) -> Session:
        """
        获取主会话（不存在则创建）
        
        Returns:
            主会话
        """
        main_key = self.generate_session_key(self._agent_id, self._main_key)
        session, _ = await self.check_and_reset_session(main_key)
        return session
        
    async def update_token_usage(
        self,
        session_id: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        """
        更新 token 使用量
        
        Args:
            session_id: 会话 ID
            input_tokens: 输入 token 数
            output_tokens: 输出 token 数
        """
        if session_id in self._metadata_cache:
            meta = self._metadata_cache[session_id]
            meta.input_tokens += input_tokens
            meta.output_tokens += output_tokens
            meta.token_count = meta.input_tokens + meta.output_tokens
            await self._save_metadata(session_id)
            
    async def prune_old_sessions(
        self,
        max_age_days: int = 30,
        max_sessions: Optional[int] = None,
    ) -> int:
        """
        清理旧会话
        
        Args:
            max_age_days: 最大保留天数
            max_sessions: 最大会话数量
            
        Returns:
            清理的会话数量
        """
        all_sessions = self.list_sessions()
        now = datetime.now()
        threshold = now - timedelta(days=max_age_days)
        pruned = 0
        
        # 按时间排序
        all_sessions.sort(
            key=lambda s: s.updated_at if s.updated_at else s.created_at,
            reverse=True,
        )
        
        for i, meta in enumerate(all_sessions):
            # 检查数量限制
            if max_sessions and i >= max_sessions:
                await self.archive_session(meta.session_id)
                pruned += 1
                continue
                
            # 检查时间限制
            if meta.state in [SessionState.CLOSED, SessionState.ARCHIVED]:
                continue
                
            updated = datetime.fromisoformat(meta.updated_at) if meta.updated_at else None
            if updated and updated < threshold:
                await self.archive_session(meta.session_id)
                pruned += 1
                
        if pruned > 0:
            self.logger.info(f"清理了 {pruned} 个旧会话")
            
        return pruned
        
    def get_session_id_by_key(self, session_key: str) -> Optional[str]:
        """
        通过会话键获取会话ID
        
        Args:
            session_key: 会话键
            
        Returns:
            会话ID
        """
        return self._key_to_id.get(session_key)


# ============== 便捷函数 ==============

def create_session_store(
    sessions_dir: Union[Path, str],
    agent_id: str,
    reset_policy: Optional[ResetPolicy] = None,
    main_key: str = "main",
) -> SessionStore:
    """
    创建会话存储
    
    Args:
        sessions_dir: 会话目录
        agent_id: Agent ID
        reset_policy: 重置策略
        main_key: 主会话键
        
    Returns:
        SessionStore 实例
    """
    if isinstance(sessions_dir, str):
        sessions_dir = Path(sessions_dir)
    sessions_dir.mkdir(parents=True, exist_ok=True)
    return SessionStore(
        sessions_dir=sessions_dir,
        agent_id=agent_id,
        reset_policy=reset_policy,
        main_key=main_key,
    )


def create_reset_policy(
    mode: str = "daily",
    at_hour: int = 4,
    idle_minutes: int = 120,
    triggers: Optional[List[str]] = None,
) -> ResetPolicy:
    """
    创建重置策略
    
    Args:
        mode: 重置模式 ("daily", "idle", "manual", "never")
        at_hour: 每日重置时间
        idle_minutes: 空闲超时分钟数
        triggers: 重置触发器列表
        
    Returns:
        ResetPolicy 实例
    """
    return ResetPolicy(
        mode=ResetMode(mode),
        at_hour=at_hour,
        idle_minutes=idle_minutes,
        triggers=triggers or ["/new", "/reset"],
    )
