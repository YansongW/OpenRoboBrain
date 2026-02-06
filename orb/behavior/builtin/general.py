"""
通用行为

默认行为，接收任意自然语言输入，通过LLM进行理解和规划。
生成chat_response和ros2_commands。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from orb.behavior.base import (
    Behavior,
    BehaviorConfig,
    BehaviorContext,
)
from orb.system.services.logger import trace_context, Layer

if TYPE_CHECKING:
    from orb.agent.orchestrator.orchestrator import OrchestratorAgent
    from orb.agent.atomic.cognitive.reasoning import ReasoningAgent
    from orb.system.llm.base import BaseLLM


class GeneralBehavior(Behavior):
    """
    通用行为
    
    默认行为，可以处理任意自然语言输入：
    - 使用LLM进行意图理解
    - 生成对话响应
    - 规划ROS2命令
    
    这是系统的"兜底"行为，当其他专用行为无法匹配时使用。
    """
    
    def __init__(
        self,
        llm: Optional["BaseLLM"] = None,
        orchestrator: Optional["OrchestratorAgent"] = None,
    ):
        """
        初始化通用行为
        
        Args:
            llm: LLM实例
            orchestrator: 编排Agent
        """
        config = BehaviorConfig(
            name="general",
            description="通用行为 - 处理任意自然语言输入",
            version="1.0.0",
            required_capabilities=[
                "reasoning",       # 认知推理
                "intent_recognition",  # 意图识别
            ],
            tags=["general", "default", "llm"],
            timeout_seconds=60.0,
            enable_workflow_memory=False,  # 通用行为不使用工作流记忆
        )
        super().__init__(config)
        
        self._llm = llm
        self._orchestrator = orchestrator
        self._reasoning_agent: Optional["ReasoningAgent"] = None
    
    @property
    def llm(self) -> Optional["BaseLLM"]:
        """获取LLM实例"""
        return self._llm
    
    @llm.setter
    def llm(self, value: "BaseLLM") -> None:
        """设置LLM实例"""
        self._llm = value
        # 同步到ReasoningAgent
        if self._reasoning_agent:
            self._reasoning_agent.llm = value
    
    def set_reasoning_agent(self, agent: "ReasoningAgent") -> None:
        """设置推理Agent"""
        self._reasoning_agent = agent
    
    def can_handle(self, user_input: str) -> float:
        """
        评估是否可以处理该输入
        
        作为通用行为，总是返回一个较低但非零的置信度，
        以便在没有其他行为匹配时作为兜底。
        
        Args:
            user_input: 用户输入
            
        Returns:
            置信度 (0.1 - 作为兜底行为)
        """
        if not user_input or not user_input.strip():
            return 0.0
        
        # 返回较低的置信度，作为兜底行为
        # 其他专用行为（如CookingBehavior）会返回更高的置信度
        return 0.1
    
    async def execute(self, context: BehaviorContext) -> Dict[str, Any]:
        """
        执行通用行为
        
        流程：
        1. 使用ReasoningAgent或直接调用LLM进行推理
        2. 提取意图、对话响应和ROS2命令
        3. 返回结构化结果
        
        Args:
            context: 行为执行上下文
            
        Returns:
            执行结果，包含chat_response和ros2_commands
        """
        user_input = context.user_input
        trace_id = context.trace_id
        
        with trace_context(trace_id=trace_id, layer=Layer.BEHAVIOR, component=self.name):
            self.logger.info(f"执行通用行为: {user_input[:50]}...")
            
            result = {
                "task": "general",
                "user_input": user_input,
                "intent": "unknown",
                "chat_response": "",
                "ros2_commands": [],
                "steps": [],
            }
            
            try:
                # 方式1: 使用ReasoningAgent
                if self._reasoning_agent:
                    self.logger.info("使用ReasoningAgent进行推理")
                    reasoning_result = await self._reasoning_agent.reason(
                        user_input=user_input,
                        context=context.parameters,
                        trace_id=trace_id,
                    )
                    
                    result["intent"] = reasoning_result.intent
                    result["chat_response"] = reasoning_result.chat_response
                    result["ros2_commands"] = reasoning_result.ros2_commands
                    result["reasoning_steps"] = reasoning_result.reasoning_steps
                    result["confidence"] = reasoning_result.confidence
                    
                    # 同步到context
                    context.chat_response = reasoning_result.chat_response
                    context.ros2_commands = reasoning_result.ros2_commands
                    
                    result["steps"].append({
                        "step": 1,
                        "action": "reasoning",
                        "agent": "ReasoningAgent",
                        "result": f"意图: {reasoning_result.intent}",
                    })
                
                # 方式2: 使用Orchestrator
                elif self._orchestrator:
                    self.logger.info("使用Orchestrator进行LLM推理")
                    llm_result = await self._orchestrator.execute_with_llm(
                        user_input=user_input,
                        parameters=context.parameters,
                        trace_id=trace_id,
                    )
                    
                    result["chat_response"] = llm_result.chat_response
                    result["ros2_commands"] = llm_result.ros2_commands
                    result["reasoning"] = llm_result.reasoning
                    
                    # 同步到context
                    context.chat_response = llm_result.chat_response
                    context.ros2_commands = llm_result.ros2_commands
                    
                    result["steps"].append({
                        "step": 1,
                        "action": "orchestrator_llm",
                        "agent": "Orchestrator",
                        "result": "LLM推理完成",
                    })
                
                # 方式3: 直接调用LLM
                elif self._llm:
                    self.logger.info("直接调用LLM")
                    llm_result = await self._direct_llm_call(user_input, context)
                    
                    result["chat_response"] = llm_result.get("chat_response", "")
                    result["ros2_commands"] = llm_result.get("ros2_commands", [])
                    
                    # 同步到context
                    context.chat_response = result["chat_response"]
                    context.ros2_commands = result["ros2_commands"]
                    
                    result["steps"].append({
                        "step": 1,
                        "action": "direct_llm",
                        "result": "LLM直接调用完成",
                    })
                
                # 方式4: 基于规则的简单响应
                else:
                    self.logger.warning("无LLM可用，使用规则响应")
                    rule_result = self._rule_based_response(user_input)
                    
                    result["chat_response"] = rule_result["chat_response"]
                    result["ros2_commands"] = rule_result["ros2_commands"]
                    result["intent"] = rule_result["intent"]
                    
                    # 同步到context
                    context.chat_response = result["chat_response"]
                    context.ros2_commands = result["ros2_commands"]
                    
                    result["steps"].append({
                        "step": 1,
                        "action": "rule_based",
                        "result": "规则响应",
                    })
                
                self.logger.info(
                    f"通用行为完成 - 响应: {result['chat_response'][:50]}..., "
                    f"命令数: {len(result['ros2_commands'])}"
                )
                
            except Exception as e:
                self.logger.error(f"通用行为执行失败: {e}")
                result["error"] = str(e)
                result["chat_response"] = "抱歉，我在处理您的请求时遇到了问题。"
                context.chat_response = result["chat_response"]
            
            return result
    
    async def _direct_llm_call(
        self,
        user_input: str,
        context: BehaviorContext,
    ) -> Dict[str, Any]:
        """
        直接调用LLM
        
        Args:
            user_input: 用户输入
            context: 行为上下文
            
        Returns:
            LLM响应结果
        """
        if not self._llm:
            return self._rule_based_response(user_input)
        
        from orb.system.llm.message import LLMMessage
        import json
        import re
        
        # 构建系统提示词
        system_prompt = """你是OpenRoboBrain机器人大脑系统。

请以JSON格式回复用户，包含以下字段：
{
    "chat_response": "给用户的自然语言回复",
    "ros2_commands": [
        {"command_type": "命令类型", "parameters": {}}
    ]
}

如果不需要机器人动作，ros2_commands为空数组。
"""
        
        messages = [
            LLMMessage.system(system_prompt),
            LLMMessage.user(user_input),
        ]
        
        response = await self._llm.chat(messages=messages)
        content = response.content or ""
        
        # 解析响应
        result = {
            "chat_response": content,
            "ros2_commands": [],
        }
        
        # 尝试解析JSON
        try:
            data = json.loads(content)
            result["chat_response"] = data.get("chat_response", content)
            result["ros2_commands"] = data.get("ros2_commands", [])
        except json.JSONDecodeError:
            # 尝试从代码块提取
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', content)
            if json_match:
                try:
                    data = json.loads(json_match.group(1))
                    result["chat_response"] = data.get("chat_response", content)
                    result["ros2_commands"] = data.get("ros2_commands", [])
                except json.JSONDecodeError:
                    pass
        
        return result
    
    def _rule_based_response(self, user_input: str) -> Dict[str, Any]:
        """
        基于规则的响应（当LLM不可用时）
        
        Args:
            user_input: 用户输入
            
        Returns:
            响应结果
        """
        result = {
            "chat_response": "",
            "ros2_commands": [],
            "intent": "unknown",
        }
        
        input_lower = user_input.lower()
        
        # 简单的规则匹配
        if any(kw in input_lower for kw in ["你好", "hi", "hello", "嗨"]):
            result["intent"] = "greeting"
            result["chat_response"] = "你好！我是OpenRoboBrain机器人，有什么可以帮您的吗？"
            
        elif any(kw in input_lower for kw in ["再见", "拜拜", "bye", "goodbye"]):
            result["intent"] = "farewell"
            result["chat_response"] = "再见！祝您有美好的一天！"
            
        elif any(kw in input_lower for kw in ["去", "到", "走", "前往"]):
            result["intent"] = "command"
            result["chat_response"] = "好的，我来帮您导航。"
            result["ros2_commands"].append({
                "command_type": "navigate",
                "parameters": {"target": "default"},
            })
            
        elif any(kw in input_lower for kw in ["拿", "取", "抓", "给我"]):
            result["intent"] = "command"
            result["chat_response"] = "好的，我来帮您取东西。"
            result["ros2_commands"].append({
                "command_type": "grasp",
                "parameters": {"object": "target"},
            })
            
        elif any(kw in input_lower for kw in ["停", "别动", "stop"]):
            result["intent"] = "command"
            result["chat_response"] = "好的，已停止。"
            result["ros2_commands"].append({
                "command_type": "stop",
                "parameters": {},
            })
            
        else:
            result["intent"] = "chat"
            result["chat_response"] = f"收到您的消息。我是机器人，正在学习中。您可以让我帮您做一些简单的任务，比如导航或抓取物品。"
        
        return result
