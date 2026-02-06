"""
推理Agent

LLM驱动的认知Agent，负责：
- 自然语言理解
- 意图识别
- 任务规划
- 生成对话响应和ROS2命令
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from kaibrain.agent.atomic.base_atomic import AtomicAgent
from kaibrain.system.services.logger import AgentLoggerMixin, trace_context, Layer

if TYPE_CHECKING:
    from kaibrain.system.llm.base import BaseLLM
    from kaibrain.system.brain_pipeline.message_bus import MessageBus


@dataclass
class ReasoningResult:
    """推理结果"""
    success: bool = True
    intent: str = ""                                    # 识别的意图
    chat_response: str = ""                             # 对话响应
    ros2_commands: List[Dict[str, Any]] = field(default_factory=list)  # ROS2命令
    reasoning_steps: List[str] = field(default_factory=list)  # 推理步骤
    confidence: float = 0.0                             # 置信度
    error: Optional[str] = None
    raw_llm_response: str = ""                          # 原始LLM响应
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "intent": self.intent,
            "chat_response": self.chat_response,
            "ros2_commands": self.ros2_commands,
            "reasoning_steps": self.reasoning_steps,
            "confidence": self.confidence,
            "error": self.error,
        }


class ReasoningAgent(AtomicAgent):
    """
    推理Agent
    
    LLM驱动的认知Agent，负责理解用户输入并生成响应和命令。
    
    工作流程：
    1. 接收用户自然语言输入
    2. 调用LLM进行意图理解和任务规划
    3. 解析LLM输出，提取chat_response和ros2_commands
    4. 返回结构化结果
    """
    
    # 日志层级
    _log_layer = Layer.AGENT
    
    # 系统提示词模板
    SYSTEM_PROMPT = """你是KaiBrain机器人大脑系统的推理Agent。

你的职责是：
1. 理解用户的自然语言请求
2. 识别用户意图
3. 生成友好的对话回复
4. 规划必要的机器人动作（ROS2命令）

请严格以JSON格式回复，包含以下字段：
{
    "intent": "用户意图(greeting/question/command/chat/unknown)",
    "reasoning_steps": ["推理步骤1", "推理步骤2", ...],
    "chat_response": "给用户的自然语言回复",
    "ros2_commands": [
        {
            "command_type": "命令类型",
            "parameters": {"参数": "值"}
        }
    ],
    "confidence": 0.9
}

可用的命令类型：
- move_to: 移动到位置 {"target_position": {"x": 0, "y": 0, "z": 0}, "velocity": 0.5}
- grasp: 抓取物体 {"object": "物体名称", "approach_direction": "top/side/front"}
- navigate: 导航 {"target": "位置名称", "avoid_obstacles": true}
- speak: 语音输出 {"text": "要说的话", "language": "zh-CN"}
- rotate: 旋转 {"angle": 90, "direction": "left/right"}
- stop: 停止 {}
- look_at: 视觉注视 {"target": "目标名称"}

意图类型：
- greeting: 问候
- question: 提问
- command: 执行命令
- chat: 闲聊
- unknown: 无法识别

如果用户请求不需要机器人动作，ros2_commands应为空数组[]。
回复必须是有效的JSON格式。
"""
    
    def __init__(
        self,
        name: str = "ReasoningAgent",
        llm: Optional["BaseLLM"] = None,
        message_bus: Optional["MessageBus"] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        初始化推理Agent
        
        Args:
            name: Agent名称
            llm: LLM实例
            message_bus: 消息总线
            config: 配置
        """
        super().__init__(
            name=name,
            agent_type="reasoning",
            capabilities=["reasoning", "intent_recognition", "planning"],
            message_bus=message_bus,
            config=config,
        )
        
        self._llm = llm
        self._system_prompt = self.SYSTEM_PROMPT
        
        # 自定义配置
        if config:
            self._system_prompt = config.get("system_prompt", self.SYSTEM_PROMPT)
    
    @property
    def llm(self) -> Optional["BaseLLM"]:
        """获取LLM实例"""
        return self._llm
    
    @llm.setter
    def llm(self, value: "BaseLLM") -> None:
        """设置LLM实例"""
        self._llm = value
    
    async def execute(
        self,
        input_data: Dict[str, Any],
        parameters: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        执行推理任务
        
        Args:
            input_data: 输入数据，包含 "user_input" 字段
            parameters: 参数，可包含 "trace_id", "context" 等
            
        Returns:
            推理结果字典
        """
        user_input = input_data.get("user_input", "")
        trace_id = parameters.get("trace_id", "")
        context = parameters.get("context", {})
        
        result = await self.reason(
            user_input=user_input,
            context=context,
            trace_id=trace_id,
        )
        
        return result.to_dict()
    
    async def reason(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
    ) -> ReasoningResult:
        """
        执行推理
        
        Args:
            user_input: 用户自然语言输入
            context: 上下文信息
            trace_id: 追踪ID
            
        Returns:
            ReasoningResult
        """
        result = ReasoningResult()
        
        with trace_context(trace_id=trace_id, layer=Layer.AGENT, component=self.name):
            self.logger.info(f"开始推理: {user_input[:50]}...")
            
            try:
                # 检查LLM是否可用
                if not self._llm:
                    self.logger.warning("LLM未配置，使用规则推理")
                    return self._rule_based_reasoning(user_input)
                
                # 构建消息
                from kaibrain.system.llm.message import LLMMessage
                
                messages = [
                    LLMMessage.system(self._system_prompt),
                ]
                
                # 添加上下文
                if context:
                    context_str = f"当前上下文信息:\n{json.dumps(context, ensure_ascii=False, indent=2)}"
                    messages.append(LLMMessage.system(context_str))
                
                messages.append(LLMMessage.user(user_input))
                
                # 调用LLM
                self.logger.info("调用LLM进行推理...")
                response = await self._llm.chat(messages=messages, temperature=0.7)
                
                # 保存原始响应
                result.raw_llm_response = response.content or ""
                self.logger.debug(f"LLM原始响应: {result.raw_llm_response[:200]}...")
                
                # 解析响应
                parsed = self._parse_llm_response(result.raw_llm_response)
                result.intent = parsed.get("intent", "unknown")
                result.chat_response = parsed.get("chat_response", result.raw_llm_response)
                result.ros2_commands = parsed.get("ros2_commands", [])
                result.reasoning_steps = parsed.get("reasoning_steps", [])
                result.confidence = parsed.get("confidence", 0.5)
                result.success = True
                
                self.logger.info(
                    f"推理完成 - 意图: {result.intent}, "
                    f"命令数: {len(result.ros2_commands)}, "
                    f"置信度: {result.confidence:.2f}"
                )
                
            except Exception as e:
                self.logger.error(f"推理失败: {e}")
                result.success = False
                result.error = str(e)
                result.chat_response = "抱歉，我在理解您的请求时遇到了问题。"
        
        return result
    
    def _parse_llm_response(self, content: str) -> Dict[str, Any]:
        """
        解析LLM响应
        
        尝试从LLM输出中提取JSON结构。
        
        Args:
            content: LLM原始输出
            
        Returns:
            解析后的字典
        """
        result = {
            "intent": "unknown",
            "chat_response": content,
            "ros2_commands": [],
            "reasoning_steps": [],
            "confidence": 0.5,
        }
        
        # 尝试直接解析JSON
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                return self._extract_fields(data, result)
        except json.JSONDecodeError:
            pass
        
        # 尝试从markdown代码块提取
        json_patterns = [
            r'```json\s*([\s\S]*?)```',
            r'```\s*([\s\S]*?)```',
            r'\{[\s\S]*\}',
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, content)
            for match in matches:
                try:
                    # 清理匹配内容
                    clean_match = match.strip()
                    # 如果不是以{开头，尝试找到{
                    if not clean_match.startswith('{'):
                        idx = clean_match.find('{')
                        if idx != -1:
                            clean_match = clean_match[idx:]
                    
                    data = json.loads(clean_match)
                    if isinstance(data, dict):
                        return self._extract_fields(data, result)
                except (json.JSONDecodeError, ValueError):
                    continue
        
        # 无法解析JSON，尝试简单关键词匹配
        return self._fallback_parse(content, result)
    
    def _extract_fields(
        self,
        data: Dict[str, Any],
        default: Dict[str, Any],
    ) -> Dict[str, Any]:
        """从解析的数据中提取字段"""
        return {
            "intent": data.get("intent", default["intent"]),
            "chat_response": data.get("chat_response", default["chat_response"]),
            "ros2_commands": data.get("ros2_commands", default["ros2_commands"]),
            "reasoning_steps": data.get("reasoning_steps", default["reasoning_steps"]),
            "confidence": float(data.get("confidence", default["confidence"])),
        }
    
    def _fallback_parse(
        self,
        content: str,
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """回退解析（当JSON解析失败时）"""
        content_lower = content.lower()
        
        # 简单意图识别
        if any(kw in content_lower for kw in ["你好", "hi", "hello", "嗨"]):
            result["intent"] = "greeting"
        elif any(kw in content_lower for kw in ["?", "？", "什么", "为什么", "怎么"]):
            result["intent"] = "question"
        elif any(kw in content_lower for kw in ["去", "拿", "做", "帮"]):
            result["intent"] = "command"
        else:
            result["intent"] = "chat"
        
        result["chat_response"] = content
        result["confidence"] = 0.3
        
        return result
    
    def _rule_based_reasoning(self, user_input: str) -> ReasoningResult:
        """
        基于规则的推理（当LLM不可用时）
        
        Args:
            user_input: 用户输入
            
        Returns:
            ReasoningResult
        """
        result = ReasoningResult(success=True)
        input_lower = user_input.lower()
        
        # 意图识别
        if any(kw in input_lower for kw in ["你好", "hi", "hello", "嗨", "早上好", "晚上好"]):
            result.intent = "greeting"
            result.chat_response = "你好！我是KaiBrain机器人，有什么可以帮助您的吗？"
            result.confidence = 0.8
            
        elif any(kw in input_lower for kw in ["?", "？", "什么", "为什么", "怎么", "哪里", "谁"]):
            result.intent = "question"
            result.chat_response = "这是一个好问题。让我帮您查找相关信息。"
            result.confidence = 0.6
            
        elif any(kw in input_lower for kw in ["去", "到", "走", "前往", "navigate"]):
            result.intent = "command"
            result.chat_response = "好的，我来帮您导航。"
            result.ros2_commands.append({
                "command_type": "navigate",
                "parameters": {"target": "default_target"},
            })
            result.confidence = 0.7
            
        elif any(kw in input_lower for kw in ["拿", "取", "抓", "给我", "grasp"]):
            result.intent = "command"
            result.chat_response = "好的，我来帮您取东西。"
            result.ros2_commands.append({
                "command_type": "grasp",
                "parameters": {"object": "target_object"},
            })
            result.confidence = 0.7
            
        elif any(kw in input_lower for kw in ["停", "stop", "别动"]):
            result.intent = "command"
            result.chat_response = "好的，已停止。"
            result.ros2_commands.append({
                "command_type": "stop",
                "parameters": {},
            })
            result.confidence = 0.9
            
        else:
            result.intent = "chat"
            result.chat_response = f"收到您的消息：{user_input}。有什么具体需要帮助的吗？"
            result.confidence = 0.4
        
        result.reasoning_steps = [
            f"输入分析: {user_input[:30]}...",
            f"意图识别: {result.intent}",
            f"生成响应和命令",
        ]
        
        return result
    
    def update_system_prompt(self, prompt: str) -> None:
        """更新系统提示词"""
        self._system_prompt = prompt
        self.logger.info("系统提示词已更新")
