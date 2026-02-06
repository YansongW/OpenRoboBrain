"""
生命周期管理

管理Agent的生命周期状态转换。
"""

from __future__ import annotations

import asyncio
from typing import Dict, List, Optional, TYPE_CHECKING

from orb.agent.base import BaseAgent, AgentState
from orb.system.services.logger import LoggerMixin

if TYPE_CHECKING:
    from orb.agent.super.registry import AgentRegistry


class LifecycleManager(LoggerMixin):
    """
    生命周期管理器
    
    管理Agent的启动、停止、暂停、恢复等生命周期操作。
    """
    
    def __init__(self, registry: AgentRegistry):
        """
        初始化生命周期管理器
        
        Args:
            registry: Agent注册表
        """
        self.registry = registry
        self._health_check_interval = 10.0
        self._running = False
        self._health_check_task: Optional[asyncio.Task] = None
        
    async def start(self) -> None:
        """启动生命周期管理器"""
        self._running = True
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        self.logger.info("生命周期管理器已启动")
        
    async def stop(self) -> None:
        """停止生命周期管理器"""
        self._running = False
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        self.logger.info("生命周期管理器已停止")
        
    async def start_agent(self, agent_id: str) -> bool:
        """
        启动Agent
        
        Args:
            agent_id: Agent ID
            
        Returns:
            是否成功
        """
        agent = self.registry.get(agent_id)
        if not agent:
            self.logger.warning(f"Agent不存在: {agent_id}")
            return False
            
        if agent.state == AgentState.RUNNING:
            self.logger.info(f"Agent已在运行: {agent_id}")
            return True
            
        if agent.state == AgentState.CREATED:
            if not await agent.initialize():
                return False
                
        return await agent.start()
        
    async def stop_agent(self, agent_id: str) -> bool:
        """
        停止Agent
        
        Args:
            agent_id: Agent ID
            
        Returns:
            是否成功
        """
        agent = self.registry.get(agent_id)
        if not agent:
            return False
            
        await agent.stop()
        return True
        
    async def restart_agent(self, agent_id: str) -> bool:
        """
        重启Agent
        
        Args:
            agent_id: Agent ID
            
        Returns:
            是否成功
        """
        agent = self.registry.get(agent_id)
        if not agent:
            return False
            
        self.logger.info(f"重启Agent: {agent_id}")
        
        await agent.stop()
        await asyncio.sleep(0.5)  # 等待资源释放
        
        if not await agent.initialize():
            return False
            
        return await agent.start()
        
    async def pause_agent(self, agent_id: str) -> bool:
        """暂停Agent"""
        agent = self.registry.get(agent_id)
        if agent and agent.state == AgentState.RUNNING:
            await agent.pause()
            return True
        return False
        
    async def resume_agent(self, agent_id: str) -> bool:
        """恢复Agent"""
        agent = self.registry.get(agent_id)
        if agent and agent.state == AgentState.PAUSED:
            await agent.resume()
            return True
        return False
        
    async def start_all(self) -> Dict[str, bool]:
        """
        启动所有Agent
        
        Returns:
            每个Agent的启动结果
        """
        results = {}
        for info in self.registry.list_all():
            results[info.agent_id] = await self.start_agent(info.agent_id)
        return results
        
    async def stop_all(self) -> None:
        """停止所有Agent"""
        for info in self.registry.list_all():
            await self.stop_agent(info.agent_id)
            
    async def _health_check_loop(self) -> None:
        """健康检查循环"""
        while self._running:
            try:
                await self._perform_health_check()
            except Exception as e:
                self.logger.error(f"健康检查错误: {e}")
                
            await asyncio.sleep(self._health_check_interval)
            
    async def _perform_health_check(self) -> None:
        """执行健康检查"""
        for info in self.registry.list_all():
            agent = self.registry.get(info.agent_id)
            if not agent:
                continue
                
            # 检查运行中的Agent
            if info.state == AgentState.RUNNING:
                # 这里可以添加更多健康检查逻辑
                pass
                
            # 检查错误状态的Agent
            elif info.state == AgentState.ERROR:
                self.logger.warning(
                    f"Agent处于错误状态: {info.name} - {info.error_message}"
                )
