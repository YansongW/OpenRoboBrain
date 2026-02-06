"""
Super Agent

第一级Agent，负责管理所有其他Agent的生命周期。
集成了 Message Router 和 Workspace 管理功能。

借鉴 Moltbot 的设计：
- Multi-Agent Routing: 基于 bindings 的消息路由
- Agent Isolation: 每个 Agent 独立的 workspace 和 agentDir
- Agent Runtime: 管理 Agent 运行时
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Type, TYPE_CHECKING

from kaibrain.agent.base import BaseAgent, AgentInfo, AgentLevel, AgentState
from kaibrain.agent.super.registry import AgentRegistry
from kaibrain.agent.super.lifecycle import LifecycleManager
from kaibrain.agent.super.monitor import AgentMonitor
from kaibrain.system.brain_pipeline.protocol import Message, MessageType
from kaibrain.system.brain_pipeline.routing import (
    MessageRouter,
    Binding,
    MatchRule,
    RoutingResult,
    create_router,
    create_capability_binding,
)
from kaibrain.agent.infrastructure.workspace import (
    WorkspaceManager,
    create_workspace_manager,
)
from kaibrain.agent.infrastructure.agent_dir import (
    AgentDirManager,
    create_agent_dir_manager,
)
from kaibrain.agent.runtime.agent_runtime import (
    AgentRuntime,
    RuntimeConfig,
    create_agent_runtime,
)

if TYPE_CHECKING:
    from kaibrain.system.brain_pipeline.message_bus import MessageBus
    from kaibrain.system.services.config_center import ConfigCenter


class SuperAgent(BaseAgent):
    """
    Super Agent
    
    整个Agent系统的管理者，负责：
    - Agent注册：新Agent加入系统
    - Agent删除：移除不需要的Agent
    - Agent修改：更新Agent配置/版本
    - Agent监控：监控运行状态、健康检查
    - 资源分配：为Agent分配计算资源
    - 消息路由：基于 bindings 的 Multi-Agent Routing
    - Workspace管理：管理每个 Agent 的独立工作空间
    
    注意：即使Super Agent拥有最高Agent权限，也不能修改隐性数据。
    """
    
    def __init__(
        self,
        message_bus: Optional[MessageBus] = None,
        config: Optional[ConfigCenter] = None,
        workspace_base: Optional[str] = None,
        state_dir: Optional[str] = None,
    ):
        """
        初始化Super Agent
        
        Args:
            message_bus: 消息总线
            config: 配置中心
            workspace_base: 工作空间基础目录
            state_dir: 状态目录
        """
        super().__init__(
            name="SuperAgent",
            agent_type="super_agent",
            level=AgentLevel.SUPER,
            message_bus=message_bus,
        )
        
        self.config = config
        self._workspace_base = workspace_base
        self._state_dir = state_dir
        
        # 核心组件
        self.registry = AgentRegistry()
        self.lifecycle = LifecycleManager(self.registry)
        self.monitor = AgentMonitor(self.registry)
        
        # 新增组件
        self.router = create_router(default_agent_id="main")
        self._agent_runtimes: Dict[str, AgentRuntime] = {}
        self._agent_workspaces: Dict[str, WorkspaceManager] = {}
        self._agent_dirs: Dict[str, AgentDirManager] = {}
        
    async def _on_initialize(self) -> None:
        """初始化"""
        # 订阅Agent管理相关话题
        if self._message_bus:
            self._message_bus.subscribe(self.agent_id, "agent.register")
            self._message_bus.subscribe(self.agent_id, "agent.unregister")
            self._message_bus.subscribe(self.agent_id, "agent.control")
            self._message_bus.subscribe(self.agent_id, "agent.query")
            
    async def _on_start(self) -> None:
        """启动"""
        await self.lifecycle.start()
        await self.monitor.start()
        
    async def _on_stop(self) -> None:
        """停止"""
        # 停止所有管理的Agent
        await self.lifecycle.stop_all()
        await self.lifecycle.stop()
        await self.monitor.stop()
        
    async def process(self, message: Message) -> Optional[Message]:
        """
        处理消息
        
        Args:
            message: 输入消息
            
        Returns:
            响应消息
        """
        msg_type = message.type
        payload = message.payload
        
        try:
            if msg_type == MessageType.AGENT_REGISTER:
                return await self._handle_register(message)
                
            elif msg_type == MessageType.AGENT_UNREGISTER:
                return await self._handle_unregister(message)
                
            elif msg_type == MessageType.SYSTEM_COMMAND:
                return await self._handle_command(message)
                
            elif msg_type == MessageType.DATA_QUERY:
                return await self._handle_query(message)
                
        except Exception as e:
            self.logger.error(f"处理消息失败: {e}")
            return message.create_response(
                {"success": False, "error": str(e)},
                type=MessageType.TASK_RESPONSE,
            )
            
        return None
        
    async def _handle_register(self, message: Message) -> Message:
        """处理Agent注册请求"""
        payload = message.payload
        
        # 这里需要根据agent_type动态加载Agent类
        # 实际实现中可能需要Agent工厂
        
        return message.create_response({
            "success": True,
            "message": "Agent注册请求已接收",
        })
        
    async def _handle_unregister(self, message: Message) -> Message:
        """处理Agent注销请求"""
        agent_id = message.payload.get("agent_id")
        
        if not agent_id:
            return message.create_response({
                "success": False,
                "error": "缺少agent_id",
            })
            
        success = await self.registry.unregister(agent_id)
        
        return message.create_response({
            "success": success,
            "agent_id": agent_id,
        })
        
    async def _handle_command(self, message: Message) -> Message:
        """处理系统命令"""
        command = message.payload.get("command")
        agent_id = message.payload.get("agent_id")
        
        if command == "start" and agent_id:
            success = await self.lifecycle.start_agent(agent_id)
        elif command == "stop" and agent_id:
            success = await self.lifecycle.stop_agent(agent_id)
        elif command == "restart" and agent_id:
            success = await self.lifecycle.restart_agent(agent_id)
        elif command == "pause" and agent_id:
            success = await self.lifecycle.pause_agent(agent_id)
        elif command == "resume" and agent_id:
            success = await self.lifecycle.resume_agent(agent_id)
        elif command == "start_all":
            results = await self.lifecycle.start_all()
            return message.create_response({"success": True, "results": results})
        elif command == "stop_all":
            await self.lifecycle.stop_all()
            success = True
        else:
            return message.create_response({
                "success": False,
                "error": f"未知命令: {command}",
            })
            
        return message.create_response({"success": success, "command": command})
        
    async def _handle_query(self, message: Message) -> Message:
        """处理查询请求"""
        query_type = message.payload.get("query_type")
        
        if query_type == "list_agents":
            agents = self.registry.list_all()
            return message.create_response({
                "agents": [
                    {
                        "agent_id": a.agent_id,
                        "name": a.name,
                        "type": a.agent_type,
                        "level": a.level.value,
                        "state": a.state.value,
                    }
                    for a in agents
                ],
            })
            
        elif query_type == "agent_info":
            agent_id = message.payload.get("agent_id")
            info = self.registry.get_info(agent_id)
            if info:
                return message.create_response({
                    "agent_id": info.agent_id,
                    "name": info.name,
                    "type": info.agent_type,
                    "level": info.level.value,
                    "state": info.state.value,
                    "capabilities": info.capabilities,
                    "metadata": info.metadata,
                })
            else:
                return message.create_response({"error": "Agent不存在"})
                
        elif query_type == "system_metrics":
            metrics = self.monitor.get_system_metrics()
            return message.create_response({
                "total_agents": metrics.total_agents,
                "running_agents": metrics.running_agents,
                "paused_agents": metrics.paused_agents,
                "error_agents": metrics.error_agents,
            })
            
        return message.create_response({"error": f"未知查询类型: {query_type}"})
        
    # ============== 公共API ==============
    
    async def register_agent(
        self,
        agent_class: Type[BaseAgent],
        name: str,
        agent_type: str,
        level: AgentLevel = AgentLevel.SKILL,
        config: Optional[Dict[str, Any]] = None,
        auto_start: bool = True,
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
            
        Returns:
            AgentInfo
        """
        return await self.registry.register(
            agent_class=agent_class,
            name=name,
            agent_type=agent_type,
            level=level,
            config=config,
            auto_start=auto_start,
            message_bus=self._message_bus,
        )
        
    async def unregister_agent(self, agent_id: str) -> bool:
        """注销Agent"""
        return await self.registry.unregister(agent_id)
        
    def get_agent(self, agent_id: str) -> Optional[BaseAgent]:
        """获取Agent"""
        return self.registry.get(agent_id)
        
    def list_agents(self) -> List[AgentInfo]:
        """列出所有Agent"""
        return self.registry.list_all()
        
    # ============== Multi-Agent Routing ==============
    
    def add_routing_binding(self, binding: Binding) -> None:
        """
        添加路由绑定
        
        Args:
            binding: 绑定规则
        """
        self.router.add_binding(binding)
        
    def add_capability_binding(
        self,
        agent_id: str,
        capability: str,
        priority: int = 0,
    ) -> None:
        """
        添加能力绑定
        
        Args:
            agent_id: Agent ID
            capability: 能力名称
            priority: 优先级
        """
        binding = create_capability_binding(agent_id, capability, priority)
        self.router.add_binding(binding)
        
    def route_message(
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
        return self.router.route(message, context)
        
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
        return self.router.route_by_capability(capability, context)
        
    # ============== Agent Runtime Management ==============
    
    async def create_agent_runtime(
        self,
        agent_id: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> AgentRuntime:
        """
        创建 Agent 运行时
        
        Args:
            agent_id: Agent ID
            config: 运行时配置
            
        Returns:
            AgentRuntime 实例
        """
        config = config or {}
        
        # 创建运行时
        runtime = create_agent_runtime(
            agent_id=agent_id,
            workspace_path=self._workspace_base,
            state_dir=self._state_dir,
            **config,
        )
        
        # 初始化
        await runtime.initialize()
        
        # 保存引用
        self._agent_runtimes[agent_id] = runtime
        self._agent_workspaces[agent_id] = runtime.workspace
        self._agent_dirs[agent_id] = runtime.agent_dir
        
        self.logger.info(f"创建 Agent 运行时: {agent_id}")
        return runtime
        
    def get_agent_runtime(self, agent_id: str) -> Optional[AgentRuntime]:
        """
        获取 Agent 运行时
        
        Args:
            agent_id: Agent ID
            
        Returns:
            AgentRuntime 实例
        """
        return self._agent_runtimes.get(agent_id)
        
    async def remove_agent_runtime(self, agent_id: str) -> bool:
        """
        移除 Agent 运行时
        
        Args:
            agent_id: Agent ID
            
        Returns:
            是否成功
        """
        runtime = self._agent_runtimes.pop(agent_id, None)
        if runtime:
            await runtime.cleanup()
            self._agent_workspaces.pop(agent_id, None)
            self._agent_dirs.pop(agent_id, None)
            return True
        return False
        
    # ============== Workspace Management ==============
    
    def get_agent_workspace(self, agent_id: str) -> Optional[WorkspaceManager]:
        """
        获取 Agent 的工作空间
        
        Args:
            agent_id: Agent ID
            
        Returns:
            WorkspaceManager 实例
        """
        return self._agent_workspaces.get(agent_id)
        
    def get_agent_dir(self, agent_id: str) -> Optional[AgentDirManager]:
        """
        获取 Agent 的状态目录
        
        Args:
            agent_id: Agent ID
            
        Returns:
            AgentDirManager 实例
        """
        return self._agent_dirs.get(agent_id)
        
    # ============== Enhanced Process ==============
    
    async def process_with_routing(self, message: Message) -> Optional[Message]:
        """
        使用路由处理消息
        
        自动将消息路由到目标 Agent 并执行
        
        Args:
            message: 输入消息
            
        Returns:
            响应消息
        """
        # 路由消息
        routing_result = self.route_message(message)
        target_agent_id = routing_result.agent_id
        
        # 获取目标 Agent 运行时
        runtime = self.get_agent_runtime(target_agent_id)
        
        if runtime and runtime.is_initialized:
            # 使用运行时执行
            user_input = message.payload.get("input", "")
            session_id = message.payload.get("session_id")
            
            result = await runtime.run(
                user_input=user_input,
                session_id=session_id,
                metadata={
                    "source_message_id": message.id,
                    "routing_result": routing_result.reason,
                },
            )
            
            return message.create_response({
                "success": result.status == "success",
                "response": result.response,
                "run_id": result.run_id,
                "agent_id": target_agent_id,
                "routing": routing_result.reason,
            })
        else:
            # 回退到传统处理
            target_agent = self.get_agent(target_agent_id)
            if target_agent:
                return await target_agent.process(message)
            else:
                return message.create_response({
                    "success": False,
                    "error": f"Agent 不存在或未初始化: {target_agent_id}",
                })
                
    # ============== Info ==============
    
    def get_multi_agent_info(self) -> Dict[str, Any]:
        """
        获取多 Agent 系统信息
        
        Returns:
            系统信息
        """
        return {
            "routing": self.router.get_info(),
            "runtimes": {
                agent_id: runtime.get_info()
                for agent_id, runtime in self._agent_runtimes.items()
            },
            "registered_agents": [
                {
                    "agent_id": info.agent_id,
                    "name": info.name,
                    "state": info.state.value,
                    "has_runtime": info.agent_id in self._agent_runtimes,
                }
                for info in self.registry.list_all()
            ],
        }