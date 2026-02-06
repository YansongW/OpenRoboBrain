"""
Agent注册管理

管理Agent的注册、删除和修改。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Type

from kaibrain.agent.base import BaseAgent, AgentInfo, AgentLevel, AgentState
from kaibrain.system.services.logger import LoggerMixin


@dataclass
class RegisteredAgent:
    """已注册的Agent"""
    info: AgentInfo
    agent_class: Type[BaseAgent]
    instance: Optional[BaseAgent] = None
    config: Dict[str, Any] = field(default_factory=dict)
    registered_at: datetime = field(default_factory=datetime.now)


class AgentRegistry(LoggerMixin):
    """
    Agent注册表
    
    管理所有Agent的注册信息。
    """
    
    def __init__(self):
        self._registry: Dict[str, RegisteredAgent] = {}
        self._by_type: Dict[str, List[str]] = {}
        self._by_level: Dict[AgentLevel, List[str]] = {
            level: [] for level in AgentLevel
        }
        self._lock = asyncio.Lock()
        
    async def register(
        self,
        agent_class: Type[BaseAgent],
        name: str,
        agent_type: str,
        level: AgentLevel = AgentLevel.SKILL,
        config: Optional[Dict[str, Any]] = None,
        auto_start: bool = False,
        message_bus: Optional[Any] = None,
    ) -> AgentInfo:
        """
        注册Agent
        
        Args:
            agent_class: Agent类
            name: Agent名称
            agent_type: Agent类型
            level: Agent层级
            config: 配置
            auto_start: 是否自动启动
            message_bus: 消息总线
            
        Returns:
            AgentInfo
        """
        async with self._lock:
            # 创建Agent实例
            instance = agent_class(
                name=name,
                agent_type=agent_type,
                level=level,
                message_bus=message_bus,
                config=config,
            )
            
            agent_id = instance.agent_id
            
            # 检查是否已存在
            if agent_id in self._registry:
                raise ValueError(f"Agent已存在: {agent_id}")
                
            # 注册
            registered = RegisteredAgent(
                info=instance.info,
                agent_class=agent_class,
                instance=instance,
                config=config or {},
            )
            
            self._registry[agent_id] = registered
            
            # 按类型索引
            if agent_type not in self._by_type:
                self._by_type[agent_type] = []
            self._by_type[agent_type].append(agent_id)
            
            # 按层级索引
            self._by_level[level].append(agent_id)
            
            self.logger.info(f"注册Agent: {name} ({agent_type}) [{level.value}]")
            
            # 自动启动
            if auto_start:
                await instance.initialize()
                await instance.start()
                
            return instance.info
            
    async def unregister(self, agent_id: str) -> bool:
        """
        注销Agent
        
        Args:
            agent_id: Agent ID
            
        Returns:
            是否成功
        """
        async with self._lock:
            if agent_id not in self._registry:
                return False
                
            registered = self._registry[agent_id]
            
            # 停止Agent
            if registered.instance and registered.instance.is_running:
                await registered.instance.stop()
                
            # 从索引中移除
            info = registered.info
            if info.agent_type in self._by_type:
                self._by_type[info.agent_type].remove(agent_id)
            self._by_level[info.level].remove(agent_id)
            
            # 从注册表移除
            del self._registry[agent_id]
            
            self.logger.info(f"注销Agent: {info.name} ({agent_id})")
            return True
            
    async def update(
        self,
        agent_id: str,
        config: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        更新Agent配置
        
        Args:
            agent_id: Agent ID
            config: 新配置
            metadata: 新元数据
            
        Returns:
            是否成功
        """
        async with self._lock:
            if agent_id not in self._registry:
                return False
                
            registered = self._registry[agent_id]
            
            if config:
                registered.config.update(config)
                
            if metadata and registered.instance:
                registered.instance.info.metadata.update(metadata)
                
            self.logger.info(f"更新Agent: {registered.info.name} ({agent_id})")
            return True
            
    def get(self, agent_id: str) -> Optional[BaseAgent]:
        """获取Agent实例"""
        registered = self._registry.get(agent_id)
        return registered.instance if registered else None
        
    def get_info(self, agent_id: str) -> Optional[AgentInfo]:
        """获取Agent信息"""
        registered = self._registry.get(agent_id)
        return registered.info if registered else None
        
    def get_by_type(self, agent_type: str) -> List[BaseAgent]:
        """按类型获取Agent"""
        agent_ids = self._by_type.get(agent_type, [])
        return [
            self._registry[aid].instance
            for aid in agent_ids
            if self._registry[aid].instance
        ]
        
    def get_by_level(self, level: AgentLevel) -> List[BaseAgent]:
        """按层级获取Agent"""
        agent_ids = self._by_level.get(level, [])
        return [
            self._registry[aid].instance
            for aid in agent_ids
            if self._registry[aid].instance
        ]
        
    def list_all(self) -> List[AgentInfo]:
        """列出所有Agent"""
        return [r.info for r in self._registry.values()]
        
    def count(self) -> int:
        """Agent数量"""
        return len(self._registry)
        
    def count_by_state(self, state: AgentState) -> int:
        """按状态统计Agent数量"""
        return sum(
            1 for r in self._registry.values()
            if r.info.state == state
        )
