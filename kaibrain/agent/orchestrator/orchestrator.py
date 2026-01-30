"""
编排Agent

第二级Agent，负责任务编排与输入输出管理。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from kaibrain.agent.base import BaseAgent, AgentLevel
from kaibrain.agent.orchestrator.task_decomposer import Task, TaskDecomposer
from kaibrain.agent.orchestrator.flow_controller import FlowController, ExecutionContext
from kaibrain.system.brain_pipeline.protocol import Message, MessageType, TaskRequest, TaskResponse

if TYPE_CHECKING:
    from kaibrain.system.brain_pipeline.message_bus import MessageBus
    from kaibrain.agent.super.super_agent import SuperAgent


class OrchestratorAgent(BaseAgent):
    """
    编排Agent
    
    负责：
    - 输入管理：接收外部请求，解析任务
    - 任务拆解：复杂任务分解为原子任务
    - Agent选择：根据任务选择合适的子Agent
    - 流程控制：编排执行顺序（串行/并行/条件）
    - 输出管理：聚合结果，返回统一响应
    """
    
    def __init__(
        self,
        name: str = "Orchestrator",
        message_bus: Optional[MessageBus] = None,
        super_agent: Optional[SuperAgent] = None,
    ):
        """
        初始化编排Agent
        
        Args:
            name: Agent名称
            message_bus: 消息总线
            super_agent: Super Agent引用
        """
        super().__init__(
            name=name,
            agent_type="orchestrator",
            level=AgentLevel.ORCHESTRATOR,
            message_bus=message_bus,
        )
        
        self.super_agent = super_agent
        
        # 核心组件
        self.task_decomposer = TaskDecomposer()
        self.flow_controller = FlowController()
        
        # 设置执行器
        self.flow_controller.set_executor(self._execute_task)
        
    async def _on_initialize(self) -> None:
        """初始化"""
        # 订阅任务相关话题
        if self._message_bus:
            self._message_bus.subscribe(self.agent_id, "task.request")
            self._message_bus.subscribe(self.agent_id, "task.cancel")
            
    async def process(self, message: Message) -> Optional[Message]:
        """
        处理消息
        
        Args:
            message: 输入消息
            
        Returns:
            响应消息
        """
        msg_type = message.type
        
        if msg_type == MessageType.TASK_REQUEST:
            return await self._handle_task_request(message)
            
        elif msg_type == MessageType.TASK_CANCEL:
            return await self._handle_task_cancel(message)
            
        return None
        
    async def _handle_task_request(self, message: Message) -> Message:
        """
        处理任务请求
        
        Args:
            message: 任务请求消息
            
        Returns:
            响应消息
        """
        payload = message.payload
        task_type = payload.get("task_type", "")
        input_data = payload.get("input_data", {})
        parameters = payload.get("parameters", {})
        
        self.logger.info(f"收到任务请求: {task_type}")
        
        try:
            # 1. 任务拆解
            task = self.task_decomposer.decompose(
                task_name=task_type,
                input_data=input_data,
                parameters=parameters,
            )
            
            # 2. 执行任务
            context = await self.flow_controller.execute(task)
            
            # 3. 返回结果
            response = TaskResponse(
                task_id=task.task_id,
                success=task.success,
                result=context.result,
                error=task.error,
            )
            
            return response.to_message(
                source=self.agent_id,
                target=message.source,
                correlation_id=message.message_id,
            )
            
        except Exception as e:
            self.logger.error(f"任务执行失败: {e}")
            
            return message.create_response({
                "success": False,
                "error": str(e),
            })
            
    async def _handle_task_cancel(self, message: Message) -> Message:
        """处理任务取消"""
        task_id = message.payload.get("task_id")
        
        if task_id:
            success = self.flow_controller.cancel(task_id)
        else:
            success = False
            
        return message.create_response({
            "success": success,
            "task_id": task_id,
        })
        
    async def _execute_task(self, task: Task) -> Any:
        """
        执行原子任务
        
        通过消息总线调用对应的子能力Agent。
        
        Args:
            task: 任务
            
        Returns:
            任务结果
        """
        agent_type = task.agent_type
        
        # 查找对应的Agent
        agent = self._find_agent_by_type(agent_type)
        
        if not agent:
            raise RuntimeError(f"找不到Agent: {agent_type}")
            
        # 构造任务请求
        request = Message(
            type=MessageType.TASK_REQUEST,
            source=self.agent_id,
            target=agent.agent_id,
            payload={
                "task_id": task.task_id,
                "task_type": task.name,
                "input_data": task.input_data,
                "parameters": task.parameters,
            },
        )
        
        # 发送请求并等待响应
        response = await self.request(request, timeout=60.0)
        
        if not response:
            raise RuntimeError(f"Agent响应超时: {agent_type}")
            
        payload = response.payload
        
        if not payload.get("success", False):
            raise RuntimeError(f"Agent执行失败: {payload.get('error', 'unknown')}")
            
        return payload.get("result")
        
    def _find_agent_by_type(self, agent_type: str) -> Optional[BaseAgent]:
        """
        根据类型查找Agent
        
        Args:
            agent_type: Agent类型
            
        Returns:
            Agent实例
        """
        if not self.super_agent:
            return None
            
        agents = self.super_agent.registry.get_by_type(agent_type)
        
        # 返回第一个可用的Agent
        for agent in agents:
            if agent.is_running:
                return agent
                
        return agents[0] if agents else None
        
    # ============== 公共API ==============
    
    async def execute_task(
        self,
        task_type: str,
        input_data: Optional[Dict[str, Any]] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> ExecutionContext:
        """
        执行任务
        
        Args:
            task_type: 任务类型
            input_data: 输入数据
            parameters: 参数
            
        Returns:
            ExecutionContext
        """
        task = self.task_decomposer.decompose(
            task_name=task_type,
            input_data=input_data,
            parameters=parameters,
        )
        
        return await self.flow_controller.execute(task)
        
    def register_task_template(
        self,
        task_name: str,
        subtasks: List[Dict[str, Any]],
    ) -> None:
        """注册任务模板"""
        self.task_decomposer.register_template(task_name, subtasks)
