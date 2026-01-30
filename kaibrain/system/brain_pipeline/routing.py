"""
Message Router

基于 bindings 的消息路由机制。
借鉴 Moltbot 的 Multi-Agent Routing 设计，实现确定性路由。

路由优先级（从高到低）：
1. peer match (精确的 peer ID 匹配)
2. capability match (能力匹配)
3. channel match (通道匹配)
4. default agent (默认 Agent)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from kaibrain.system.services.logger import LoggerMixin
from kaibrain.system.brain_pipeline.protocol import Message


class MatchType(Enum):
    """匹配类型"""
    PEER = "peer"           # 对端 ID 匹配
    CAPABILITY = "capability"  # 能力匹配
    CHANNEL = "channel"     # 通道匹配
    TOPIC = "topic"         # 话题匹配
    WILDCARD = "wildcard"   # 通配符


class PeerKind(Enum):
    """对端类型"""
    DM = "dm"       # 私聊
    GROUP = "group"  # 群聊
    ANY = "any"     # 任意


@dataclass
class PeerMatch:
    """对端匹配规则"""
    kind: PeerKind = PeerKind.ANY
    id: Optional[str] = None  # 精确匹配的 peer ID
    
    def matches(self, peer_id: Optional[str], peer_kind: Optional[str]) -> bool:
        """
        检查是否匹配
        
        Args:
            peer_id: 对端 ID
            peer_kind: 对端类型
            
        Returns:
            是否匹配
        """
        # 类型匹配
        if self.kind != PeerKind.ANY:
            if peer_kind and peer_kind != self.kind.value:
                return False
                
        # ID 匹配
        if self.id:
            return self.id == peer_id
            
        return True


@dataclass
class MatchRule:
    """匹配规则"""
    # 对端匹配
    peer: Optional[PeerMatch] = None
    
    # 能力匹配
    capability: Optional[str] = None
    
    # 通道匹配
    channel: Optional[str] = None
    
    # 话题匹配
    topic: Optional[str] = None
    
    # 来源匹配
    source: Optional[str] = None
    
    # 消息类型匹配
    message_type: Optional[str] = None
    
    # 自定义匹配条件
    conditions: Dict[str, Any] = field(default_factory=dict)
    
    def get_specificity(self) -> int:
        """
        获取规则的特异性分数（越高越具体）
        
        Returns:
            特异性分数
        """
        score = 0
        
        # peer ID 匹配最具体
        if self.peer and self.peer.id:
            score += 100
        elif self.peer and self.peer.kind != PeerKind.ANY:
            score += 50
            
        # 能力匹配
        if self.capability and self.capability != "*":
            score += 40
            
        # 通道匹配
        if self.channel and self.channel != "*":
            score += 30
            
        # 话题匹配
        if self.topic and self.topic != "*":
            score += 20
            
        # 来源匹配
        if self.source:
            score += 10
            
        # 消息类型匹配
        if self.message_type:
            score += 5
            
        # 自定义条件
        score += len(self.conditions) * 2
        
        return score
        
    def matches(self, message: Message, context: Optional[Dict[str, Any]] = None) -> bool:
        """
        检查消息是否匹配此规则
        
        Args:
            message: 消息
            context: 路由上下文
            
        Returns:
            是否匹配
        """
        context = context or {}
        
        # Peer 匹配
        if self.peer:
            peer_id = context.get("peer_id") or message.payload.get("peer_id")
            peer_kind = context.get("peer_kind") or message.payload.get("peer_kind")
            if not self.peer.matches(peer_id, peer_kind):
                return False
                
        # 能力匹配
        if self.capability and self.capability != "*":
            capability = context.get("capability") or message.payload.get("capability")
            if capability != self.capability:
                return False
                
        # 通道匹配
        if self.channel and self.channel != "*":
            channel = context.get("channel") or message.payload.get("channel")
            if channel != self.channel:
                return False
                
        # 话题匹配
        if self.topic and self.topic != "*":
            if message.topic and message.topic != self.topic:
                return False
                
        # 来源匹配
        if self.source:
            if message.source != self.source:
                return False
                
        # 消息类型匹配
        if self.message_type:
            if message.type.value != self.message_type:
                return False
                
        # 自定义条件
        for key, expected in self.conditions.items():
            actual = message.payload.get(key)
            if actual != expected:
                return False
                
        return True


@dataclass
class Binding:
    """路由绑定"""
    agent_id: str
    match: MatchRule
    priority: int = 0  # 手动指定的优先级（可选）
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def effective_priority(self) -> int:
        """有效优先级（结合手动优先级和规则特异性）"""
        return self.priority * 1000 + self.match.get_specificity()
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Binding:
        """从字典创建"""
        match_data = data.get("match", {})
        
        # 解析 peer 匹配
        peer = None
        if "peer" in match_data:
            peer_data = match_data["peer"]
            peer = PeerMatch(
                kind=PeerKind(peer_data.get("kind", "any")),
                id=peer_data.get("id"),
            )
            
        match_rule = MatchRule(
            peer=peer,
            capability=match_data.get("capability"),
            channel=match_data.get("channel"),
            topic=match_data.get("topic"),
            source=match_data.get("source"),
            message_type=match_data.get("message_type"),
            conditions=match_data.get("conditions", {}),
        )
        
        return cls(
            agent_id=data["agentId"],
            match=match_rule,
            priority=data.get("priority", 0),
            enabled=data.get("enabled", True),
            metadata=data.get("metadata", {}),
        )
        
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        match_dict = {}
        
        if self.match.peer:
            match_dict["peer"] = {
                "kind": self.match.peer.kind.value,
                "id": self.match.peer.id,
            }
            
        if self.match.capability:
            match_dict["capability"] = self.match.capability
        if self.match.channel:
            match_dict["channel"] = self.match.channel
        if self.match.topic:
            match_dict["topic"] = self.match.topic
        if self.match.source:
            match_dict["source"] = self.match.source
        if self.match.message_type:
            match_dict["message_type"] = self.match.message_type
        if self.match.conditions:
            match_dict["conditions"] = self.match.conditions
            
        return {
            "agentId": self.agent_id,
            "match": match_dict,
            "priority": self.priority,
            "enabled": self.enabled,
            "metadata": self.metadata,
        }


@dataclass
class RoutingResult:
    """路由结果"""
    agent_id: str
    binding: Optional[Binding] = None
    matched: bool = True
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class MessageRouter(LoggerMixin):
    """
    消息路由器
    
    基于 bindings 将消息路由到目标 Agent。
    支持确定性路由，最具体的规则优先匹配。
    """
    
    def __init__(
        self,
        default_agent_id: str = "main",
    ):
        """
        初始化消息路由器
        
        Args:
            default_agent_id: 默认 Agent ID
        """
        self._default_agent_id = default_agent_id
        self._bindings: List[Binding] = []
        self._agent_bindings: Dict[str, List[Binding]] = {}
        
    @property
    def default_agent_id(self) -> str:
        """默认 Agent ID"""
        return self._default_agent_id
        
    @default_agent_id.setter
    def default_agent_id(self, value: str) -> None:
        """设置默认 Agent ID"""
        self._default_agent_id = value
        
    @property
    def bindings(self) -> List[Binding]:
        """所有绑定"""
        return self._bindings.copy()
        
    def add_binding(self, binding: Binding) -> None:
        """
        添加路由绑定
        
        Args:
            binding: 绑定规则
        """
        self._bindings.append(binding)
        
        # 按 Agent 分组
        if binding.agent_id not in self._agent_bindings:
            self._agent_bindings[binding.agent_id] = []
        self._agent_bindings[binding.agent_id].append(binding)
        
        # 重新排序（按有效优先级降序）
        self._bindings.sort(key=lambda b: b.effective_priority, reverse=True)
        
        self.logger.debug(f"添加绑定: {binding.agent_id} <- {binding.match}")
        
    def add_bindings(self, bindings: List[Binding]) -> None:
        """
        批量添加绑定
        
        Args:
            bindings: 绑定列表
        """
        for binding in bindings:
            self.add_binding(binding)
            
    def remove_binding(self, binding: Binding) -> bool:
        """
        移除绑定
        
        Args:
            binding: 绑定规则
            
        Returns:
            是否成功
        """
        if binding in self._bindings:
            self._bindings.remove(binding)
            
            if binding.agent_id in self._agent_bindings:
                agent_list = self._agent_bindings[binding.agent_id]
                if binding in agent_list:
                    agent_list.remove(binding)
                    
            return True
        return False
        
    def clear_bindings(self, agent_id: Optional[str] = None) -> None:
        """
        清空绑定
        
        Args:
            agent_id: 如果指定，只清空该 Agent 的绑定
        """
        if agent_id:
            if agent_id in self._agent_bindings:
                for binding in self._agent_bindings[agent_id]:
                    if binding in self._bindings:
                        self._bindings.remove(binding)
                del self._agent_bindings[agent_id]
        else:
            self._bindings.clear()
            self._agent_bindings.clear()
            
    def route(
        self,
        message: Message,
        context: Optional[Dict[str, Any]] = None,
    ) -> RoutingResult:
        """
        路由消息到目标 Agent
        
        Args:
            message: 消息
            context: 路由上下文
            
        Returns:
            路由结果
        """
        # 如果消息已指定目标，直接返回
        if message.target:
            return RoutingResult(
                agent_id=message.target,
                matched=True,
                reason="explicit_target",
            )
            
        # 遍历绑定（已按优先级排序）
        for binding in self._bindings:
            if not binding.enabled:
                continue
                
            if binding.match.matches(message, context):
                self.logger.debug(
                    f"消息匹配绑定: {binding.agent_id} "
                    f"(优先级: {binding.effective_priority})"
                )
                return RoutingResult(
                    agent_id=binding.agent_id,
                    binding=binding,
                    matched=True,
                    reason="binding_match",
                )
                
        # 使用默认 Agent
        return RoutingResult(
            agent_id=self._default_agent_id,
            matched=False,
            reason="default_fallback",
        )
        
    def route_by_capability(
        self,
        capability: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> RoutingResult:
        """
        按能力路由
        
        Args:
            capability: 能力名称
            context: 路由上下文
            
        Returns:
            路由结果
        """
        context = context or {}
        context["capability"] = capability
        
        # 创建临时消息用于匹配
        from kaibrain.system.brain_pipeline.protocol import Message, MessageType
        
        temp_message = Message(
            type=MessageType.TASK_REQUEST,
            payload={"capability": capability},
        )
        
        return self.route(temp_message, context)
        
    def get_agent_bindings(self, agent_id: str) -> List[Binding]:
        """
        获取 Agent 的所有绑定
        
        Args:
            agent_id: Agent ID
            
        Returns:
            绑定列表
        """
        return self._agent_bindings.get(agent_id, []).copy()
        
    def get_agents_for_capability(self, capability: str) -> List[str]:
        """
        获取支持指定能力的所有 Agent
        
        Args:
            capability: 能力名称
            
        Returns:
            Agent ID 列表
        """
        agents = []
        
        for binding in self._bindings:
            if binding.enabled and binding.match.capability == capability:
                if binding.agent_id not in agents:
                    agents.append(binding.agent_id)
                    
        return agents
        
    def get_info(self) -> Dict[str, Any]:
        """
        获取路由器信息
        
        Returns:
            路由器信息
        """
        return {
            "default_agent_id": self._default_agent_id,
            "total_bindings": len(self._bindings),
            "agents": list(self._agent_bindings.keys()),
            "bindings": [b.to_dict() for b in self._bindings],
        }


# 便捷函数
def create_router(
    default_agent_id: str = "main",
    bindings: Optional[List[Dict[str, Any]]] = None,
) -> MessageRouter:
    """
    创建消息路由器
    
    Args:
        default_agent_id: 默认 Agent ID
        bindings: 初始绑定配置
        
    Returns:
        MessageRouter 实例
    """
    router = MessageRouter(default_agent_id)
    
    if bindings:
        for binding_data in bindings:
            binding = Binding.from_dict(binding_data)
            router.add_binding(binding)
            
    return router


def create_capability_binding(
    agent_id: str,
    capability: str,
    priority: int = 0,
) -> Binding:
    """
    创建能力绑定
    
    Args:
        agent_id: Agent ID
        capability: 能力名称
        priority: 优先级
        
    Returns:
        Binding 实例
    """
    return Binding(
        agent_id=agent_id,
        match=MatchRule(capability=capability),
        priority=priority,
    )


def create_channel_binding(
    agent_id: str,
    channel: str,
    priority: int = 0,
) -> Binding:
    """
    创建通道绑定
    
    Args:
        agent_id: Agent ID
        channel: 通道名称
        priority: 优先级
        
    Returns:
        Binding 实例
    """
    return Binding(
        agent_id=agent_id,
        match=MatchRule(channel=channel),
        priority=priority,
    )


def create_peer_binding(
    agent_id: str,
    peer_id: str,
    peer_kind: str = "any",
    priority: int = 0,
) -> Binding:
    """
    创建对端绑定
    
    Args:
        agent_id: Agent ID
        peer_id: 对端 ID
        peer_kind: 对端类型
        priority: 优先级
        
    Returns:
        Binding 实例
    """
    return Binding(
        agent_id=agent_id,
        match=MatchRule(
            peer=PeerMatch(
                kind=PeerKind(peer_kind),
                id=peer_id,
            )
        ),
        priority=priority,
    )
