"""
编排Agent

第二级Agent，负责任务编排与输入输出管理。
支持LLM驱动的任务执行，生成chat_response和ros2_commands。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from kaibrain.agent.base import BaseAgent, AgentLevel
from kaibrain.agent.orchestrator.task_decomposer import Task, TaskDecomposer
from kaibrain.agent.orchestrator.flow_controller import FlowController, ExecutionContext
from kaibrain.system.brain_pipeline.protocol import Message, MessageType, TaskRequest, TaskResponse
from kaibrain.system.services.logger import AgentLoggerMixin, trace_context, Layer

if TYPE_CHECKING:
    from kaibrain.system.brain_pipeline.message_bus import MessageBus
    from kaibrain.agent.super.super_agent import SuperAgent
    from kaibrain.system.llm.base import BaseLLM


@dataclass
class LLMExecutionResult:
    """LLM执行结果"""
    success: bool = True
    chat_response: str = ""
    ros2_commands: List[Dict[str, Any]] = field(default_factory=list)
    reasoning: str = ""  # LLM推理过程
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class OrchestratorAgent(BaseAgent):
    """
    编排Agent
    
    负责：
    - 输入管理：接收外部请求，解析任务
    - 任务拆解：复杂任务分解为原子任务
    - Agent选择：根据任务选择合适的子Agent
    - 流程控制：编排执行顺序（串行/并行/条件）
    - 输出管理：聚合结果，返回统一响应
    - LLM驱动执行：生成chat_response和ros2_commands
    """
    
    # 日志层级
    _log_layer = Layer.AGENT
    
    def __init__(
        self,
        name: str = "Orchestrator",
        message_bus: Optional["MessageBus"] = None,
        super_agent: Optional["SuperAgent"] = None,
        llm: Optional["BaseLLM"] = None,
    ):
        """
        初始化编排Agent
        
        Args:
            name: Agent名称
            message_bus: 消息总线
            super_agent: Super Agent引用
            llm: LLM实例（用于智能任务规划）
        """
        super().__init__(
            name=name,
            agent_type="orchestrator",
            level=AgentLevel.ORCHESTRATOR,
            message_bus=message_bus,
            llm=llm,
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
    
    async def execute_with_llm(
        self,
        user_input: str,
        parameters: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
    ) -> LLMExecutionResult:
        """
        使用LLM执行任务
        
        接收自然语言输入，通过LLM理解意图，生成对话响应和ROS2命令。
        
        Args:
            user_input: 用户自然语言输入
            parameters: 额外参数
            trace_id: 追踪ID
            
        Returns:
            LLMExecutionResult: 包含chat_response和ros2_commands
        """
        result = LLMExecutionResult()
        
        with trace_context(trace_id=trace_id, layer=Layer.AGENT, component=self.name):
            self.logger.info(f"开始LLM驱动执行: {user_input[:50]}...")
            
            try:
                # 检查LLM是否可用
                if not self._llm:
                    self.logger.warning("LLM未配置，使用默认响应")
                    result.chat_response = self._generate_default_response(user_input)
                    result.ros2_commands = self._generate_default_commands(user_input)
                    return result
                
                # 构建系统提示词
                system_prompt = self._build_robot_system_prompt()
                
                # 调用LLM进行推理
                from kaibrain.system.llm.message import LLMMessage
                
                messages = [
                    LLMMessage.system(system_prompt),
                    LLMMessage.user(user_input),
                ]
                
                self.logger.info("调用LLM进行推理...")
                response = await self._llm.chat(messages=messages)
                
                # 解析LLM响应
                llm_content = response.content or ""
                self.logger.info(f"LLM响应: {llm_content[:100]}...")
                
                # 解析响应，提取chat和commands
                parsed = self._parse_llm_response(llm_content)
                result.chat_response = parsed.get("chat_response", llm_content)
                result.ros2_commands = parsed.get("ros2_commands", [])
                result.reasoning = parsed.get("reasoning", "")
                result.success = True
                
                self.logger.info(f"解析完成，生成 {len(result.ros2_commands)} 个ROS2命令")
                
            except Exception as e:
                self.logger.error(f"LLM执行失败: {e}")
                result.success = False
                result.error = str(e)
                result.chat_response = f"抱歉，处理您的请求时出现问题: {e}"
        
        return result
    
    def _build_robot_system_prompt(self) -> str:
        """构建机器人系统提示词"""
        return """你是KaiBrain机器人大脑系统的编排Agent。

你的职责是：
1. 理解用户的自然语言请求
2. 生成友好的对话回复
3. 规划必要的机器人动作（ROS2命令）

请以JSON格式回复，包含以下字段：
{
    "reasoning": "你的推理过程",
    "chat_response": "给用户的自然语言回复",
    "ros2_commands": [
        {
            "command_type": "命令类型(move/grasp/navigate/speak等)",
            "parameters": {"参数": "值"}
        }
    ]
}

可用的命令类型：
- move: 移动到指定位置 {"target_position": {"x": 0, "y": 0, "z": 0}}
- grasp: 抓取物体 {"object": "物体名称", "approach_direction": "top/side"}
- navigate: 导航到位置 {"target": "位置名称"}
- speak: 语音输出 {"text": "要说的话"}
- rotate: 旋转 {"angle": 90}

如果请求不需要机器人动作，ros2_commands可以为空数组。
"""
    
    def _parse_llm_response(self, content: str) -> Dict[str, Any]:
        """解析LLM响应"""
        import json
        import re
        
        result = {
            "chat_response": content,
            "ros2_commands": [],
            "reasoning": "",
        }
        
        # 尝试提取JSON
        try:
            # 尝试直接解析
            data = json.loads(content)
            if isinstance(data, dict):
                result["chat_response"] = data.get("chat_response", content)
                result["ros2_commands"] = data.get("ros2_commands", [])
                result["reasoning"] = data.get("reasoning", "")
                return result
        except json.JSONDecodeError:
            pass
        
        # 尝试从markdown代码块提取JSON
        json_pattern = r'```(?:json)?\s*([\s\S]*?)```'
        matches = re.findall(json_pattern, content)
        
        for match in matches:
            try:
                data = json.loads(match.strip())
                if isinstance(data, dict):
                    result["chat_response"] = data.get("chat_response", content)
                    result["ros2_commands"] = data.get("ros2_commands", [])
                    result["reasoning"] = data.get("reasoning", "")
                    return result
            except json.JSONDecodeError:
                continue
        
        # 无法解析JSON，返回原始内容作为chat_response
        return result
    
    def _generate_default_response(self, user_input: str) -> str:
        """生成默认响应（当LLM不可用时）"""
        return f"收到您的请求：{user_input}。系统正在处理中。"
    
    def _generate_default_commands(self, user_input: str) -> List[Dict[str, Any]]:
        """生成默认命令（当LLM不可用时）"""
        # 简单的关键词匹配
        commands = []
        
        input_lower = user_input.lower()
        
        if any(kw in input_lower for kw in ["走", "去", "move", "到", "前往"]):
            commands.append({
                "command_type": "navigate",
                "parameters": {"target": "default_position"},
            })
        
        if any(kw in input_lower for kw in ["拿", "取", "抓", "grasp", "pick"]):
            commands.append({
                "command_type": "grasp",
                "parameters": {"object": "target_object"},
            })
        
        if any(kw in input_lower for kw in ["说", "讲", "speak", "告诉"]):
            commands.append({
                "command_type": "speak",
                "parameters": {"text": "好的"},
            })
        
        return commands
