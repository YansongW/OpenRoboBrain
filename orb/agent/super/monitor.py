"""
Agent监控

监控所有Agent的运行状态。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from orb.agent.base import AgentState
from orb.system.services.logger import LoggerMixin

if TYPE_CHECKING:
    from orb.agent.super.registry import AgentRegistry


@dataclass
class AgentMetrics:
    """Agent指标"""
    agent_id: str
    timestamp: datetime = field(default_factory=datetime.now)
    
    # 处理统计
    messages_processed: int = 0
    messages_failed: int = 0
    avg_processing_time_ms: float = 0.0
    
    # 资源使用
    cpu_usage_percent: float = 0.0
    memory_usage_mb: float = 0.0
    
    # 队列状态
    pending_messages: int = 0


@dataclass
class SystemMetrics:
    """系统指标"""
    timestamp: datetime = field(default_factory=datetime.now)
    
    total_agents: int = 0
    running_agents: int = 0
    paused_agents: int = 0
    error_agents: int = 0
    
    total_messages_processed: int = 0
    avg_latency_ms: float = 0.0


class AgentMonitor(LoggerMixin):
    """
    Agent监控器
    
    收集和报告Agent运行指标。
    """
    
    def __init__(self, registry: AgentRegistry):
        """
        初始化监控器
        
        Args:
            registry: Agent注册表
        """
        self.registry = registry
        self._metrics: Dict[str, AgentMetrics] = {}
        self._running = False
        self._collect_task: Optional[asyncio.Task] = None
        self._collect_interval = 5.0
        
    async def start(self) -> None:
        """启动监控"""
        self._running = True
        self._collect_task = asyncio.create_task(self._collect_loop())
        self.logger.info("Agent监控器已启动")
        
    async def stop(self) -> None:
        """停止监控"""
        self._running = False
        if self._collect_task:
            self._collect_task.cancel()
            try:
                await self._collect_task
            except asyncio.CancelledError:
                pass
        self.logger.info("Agent监控器已停止")
        
    async def _collect_loop(self) -> None:
        """收集循环"""
        while self._running:
            try:
                await self._collect_metrics()
            except Exception as e:
                self.logger.error(f"指标收集错误: {e}")
                
            await asyncio.sleep(self._collect_interval)
            
    async def _collect_metrics(self) -> None:
        """收集指标"""
        for info in self.registry.list_all():
            agent_id = info.agent_id
            
            if agent_id not in self._metrics:
                self._metrics[agent_id] = AgentMetrics(agent_id=agent_id)
                
            metrics = self._metrics[agent_id]
            metrics.timestamp = datetime.now()
            
            # TODO: 收集实际的处理统计和资源使用
            
    def get_agent_metrics(self, agent_id: str) -> Optional[AgentMetrics]:
        """获取Agent指标"""
        return self._metrics.get(agent_id)
        
    def get_system_metrics(self) -> SystemMetrics:
        """获取系统指标"""
        agents = self.registry.list_all()
        
        metrics = SystemMetrics(
            total_agents=len(agents),
            running_agents=sum(1 for a in agents if a.state == AgentState.RUNNING),
            paused_agents=sum(1 for a in agents if a.state == AgentState.PAUSED),
            error_agents=sum(1 for a in agents if a.state == AgentState.ERROR),
        )
        
        # 聚合处理统计
        for agent_metrics in self._metrics.values():
            metrics.total_messages_processed += agent_metrics.messages_processed
            
        if self._metrics:
            metrics.avg_latency_ms = sum(
                m.avg_processing_time_ms for m in self._metrics.values()
            ) / len(self._metrics)
            
        return metrics
        
    def record_message_processed(
        self,
        agent_id: str,
        processing_time_ms: float,
        success: bool = True,
    ) -> None:
        """
        记录消息处理
        
        Args:
            agent_id: Agent ID
            processing_time_ms: 处理时间
            success: 是否成功
        """
        if agent_id not in self._metrics:
            self._metrics[agent_id] = AgentMetrics(agent_id=agent_id)
            
        metrics = self._metrics[agent_id]
        
        if success:
            metrics.messages_processed += 1
        else:
            metrics.messages_failed += 1
            
        # 更新平均处理时间（移动平均）
        alpha = 0.1
        metrics.avg_processing_time_ms = (
            alpha * processing_time_ms +
            (1 - alpha) * metrics.avg_processing_time_ms
        )
