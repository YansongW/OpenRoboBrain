"""
智能Agent

基于LLM的智能Agent实现，支持自主决策和工具调用。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from orb.agent.base import BaseAgent, AgentLevel
from orb.system.services.logger import get_logger

if TYPE_CHECKING:
    from orb.system.llm.base import BaseLLM
    from orb.system.llm.message import LLMMessage, LLMResponse
    from orb.system.tools.registry import ToolRegistry
    from orb.system.brain_pipeline.message_bus import MessageBus
    from orb.system.brain_pipeline.protocol import Message

logger = get_logger(__name__)


class SmartAgent(BaseAgent):
    """
    智能Agent
    
    具备完整LLM推理和工具调用能力的Agent。
    支持ReAct模式的自主任务执行。
    """
    
    def __init__(
        self,
        name: str,
        llm: "BaseLLM",
        tool_registry: Optional["ToolRegistry"] = None,
        system_prompt: Optional[str] = None,
        max_iterations: int = 15,
        agent_type: str = "smart_agent",
        level: AgentLevel = AgentLevel.SKILL,
        message_bus: Optional["MessageBus"] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        初始化智能Agent
        
        Args:
            name: Agent名称
            llm: LLM实例
            tool_registry: 工具注册表
            system_prompt: 系统提示词
            max_iterations: 最大迭代次数
            agent_type: Agent类型
            level: Agent层级
            message_bus: 消息总线
            config: 配置
        """
        super().__init__(
            name=name,
            agent_type=agent_type,
            level=level,
            message_bus=message_bus,
            config=config,
            llm=llm,
            tool_registry=tool_registry,
            system_prompt=system_prompt,
        )
        
        self._max_iterations = max_iterations
    
    async def process(self, message: "Message") -> Optional["Message"]:
        """
        处理消息
        
        使用LLM理解消息并执行相应动作。
        
        Args:
            message: 输入消息
            
        Returns:
            响应消息
        """
        from orb.system.brain_pipeline.protocol import MessageType
        
        payload = message.payload
        
        # 根据消息类型处理
        if message.type == MessageType.TASK_REQUEST:
            return await self._handle_task_request(message)
        elif message.type == MessageType.DATA_QUERY:
            return await self._handle_query(message)
        else:
            # 默认使用LLM处理
            return await self._handle_with_llm(message)
    
    async def _handle_task_request(self, message: "Message") -> "Message":
        """处理任务请求"""
        task_description = message.payload.get("description", "")
        parameters = message.payload.get("parameters", {})
        
        # 构建任务提示
        prompt = f"请执行以下任务:\n{task_description}"
        if parameters:
            prompt += f"\n\n参数:\n{json.dumps(parameters, ensure_ascii=False, indent=2)}"
        
        # 使用Agent Loop执行
        try:
            result = await self.think_and_act(
                prompt=prompt,
                max_iterations=self._max_iterations,
                context={"task": task_description, "parameters": parameters},
            )
            
            return message.create_response({
                "success": True,
                "result": result,
            })
        except Exception as e:
            self.logger.error(f"任务执行失败: {e}")
            return message.create_response({
                "success": False,
                "error": str(e),
            })
    
    async def _handle_query(self, message: "Message") -> "Message":
        """处理查询请求"""
        query = message.payload.get("query", "")
        
        # 使用LLM回答
        response = await self.think(query, use_tools=False)
        
        return message.create_response({
            "answer": response.content,
        })
    
    async def _handle_with_llm(self, message: "Message") -> "Message":
        """使用LLM处理消息"""
        content = message.payload.get("content", str(message.payload))
        
        response = await self.think(content)
        
        return message.create_response({
            "response": response.content,
            "tool_calls": [tc.to_dict() for tc in response.tool_calls] if response.tool_calls else None,
        })
    
    async def run_task(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        直接运行任务（便捷方法）
        
        Args:
            task: 任务描述
            context: 上下文
            
        Returns:
            执行结果
        """
        return await self.think_and_act(
            prompt=task,
            max_iterations=self._max_iterations,
            context=context,
        )
    
    async def chat(self, message: str) -> str:
        """
        对话（不使用工具）
        
        Args:
            message: 用户消息
            
        Returns:
            回复
        """
        response = await self.think(message, use_tools=False)
        return response.content


class ConversationalAgent(SmartAgent):
    """
    对话型Agent
    
    专注于对话交互，保持上下文连贯性。
    """
    
    def __init__(
        self,
        name: str,
        llm: "BaseLLM",
        tool_registry: Optional["ToolRegistry"] = None,
        persona: Optional[str] = None,
        **kwargs,
    ):
        """
        初始化对话Agent
        
        Args:
            name: Agent名称
            llm: LLM实例
            tool_registry: 工具注册表
            persona: 人设描述
            **kwargs: 其他参数
        """
        # 构建系统提示词
        system_prompt = f"""你是 {name}，一个智能对话助手。
{persona or '你友好、专业，乐于帮助用户解决问题。'}

保持对话的连贯性，记住之前的交流内容。
如果用户的问题不清楚，请礼貌地请求澄清。"""
        
        super().__init__(
            name=name,
            llm=llm,
            tool_registry=tool_registry,
            system_prompt=system_prompt,
            agent_type="conversational_agent",
            **kwargs,
        )
        
        self._max_history_length = 100  # 对话Agent保留更多历史


class TaskAgent(SmartAgent):
    """
    任务型Agent
    
    专注于完成特定任务，强调计划和执行。
    """
    
    def __init__(
        self,
        name: str,
        llm: "BaseLLM",
        tool_registry: "ToolRegistry",
        task_domain: str = "通用任务",
        **kwargs,
    ):
        """
        初始化任务Agent
        
        Args:
            name: Agent名称
            llm: LLM实例
            tool_registry: 工具注册表
            task_domain: 任务领域
            **kwargs: 其他参数
        """
        # 构建任务导向的系统提示词
        system_prompt = f"""你是 {name}，一个专门处理{task_domain}的智能Agent。

你的工作流程：
1. 理解任务 - 分析用户的需求
2. 制定计划 - 将任务分解为步骤
3. 执行步骤 - 使用可用工具完成每个步骤
4. 验证结果 - 确保任务正确完成
5. 总结报告 - 向用户汇报完成情况

重要原则：
- 在执行前先思考和规划
- 每个工具调用都要有明确目的
- 遇到错误时尝试恢复或报告
- 保持输出的清晰和有条理"""
        
        super().__init__(
            name=name,
            llm=llm,
            tool_registry=tool_registry,
            system_prompt=system_prompt,
            agent_type="task_agent",
            **kwargs,
        )
