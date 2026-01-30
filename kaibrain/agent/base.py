"""
Agent基类

定义所有Agent的通用接口和基础功能，包括LLM和工具系统集成。
"""

from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from uuid import uuid4

from kaibrain.system.services.logger import LoggerMixin

if TYPE_CHECKING:
    from kaibrain.system.brain_pipeline.message_bus import MessageBus
    from kaibrain.system.brain_pipeline.protocol import Message
    from kaibrain.system.llm.base import BaseLLM
    from kaibrain.system.llm.message import LLMMessage, LLMResponse
    from kaibrain.system.tools.registry import ToolRegistry
    from kaibrain.system.tools.executor import ToolExecutor
    from kaibrain.system.tools.base import Tool, ToolCall, ToolResult


class AgentState(Enum):
    """Agent状态"""
    CREATED = "created"
    INITIALIZING = "initializing"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class AgentLevel(Enum):
    """Agent层级"""
    SUPER = "super"           # Super Agent
    ORCHESTRATOR = "orchestrator"  # 编排Agent
    SKILL = "skill"           # 技能Agent


@dataclass
class AgentInfo:
    """Agent信息"""
    agent_id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    level: AgentLevel = AgentLevel.SKILL
    agent_type: str = ""
    description: str = ""
    version: str = "1.0.0"
    state: AgentState = AgentState.CREATED
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    skills: List[str] = field(default_factory=list)  # 该Agent可执行的技能
    metadata: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None


class BaseAgent(ABC, LoggerMixin):
    """
    Agent基类
    
    所有Agent都需要继承此类。
    支持LLM集成和工具调用能力。
    """
    
    def __init__(
        self,
        name: str,
        agent_type: str,
        level: AgentLevel = AgentLevel.SKILL,
        message_bus: Optional["MessageBus"] = None,
        config: Optional[Dict[str, Any]] = None,
        llm: Optional["BaseLLM"] = None,
        tool_registry: Optional["ToolRegistry"] = None,
        system_prompt: Optional[str] = None,
    ):
        """
        初始化Agent
        
        Args:
            name: Agent名称
            agent_type: Agent类型
            level: Agent层级
            message_bus: 消息总线
            config: 配置
            llm: LLM实例（用于智能决策）
            tool_registry: 工具注册表（用于执行动作）
            system_prompt: 系统提示词
        """
        self._info = AgentInfo(
            name=name,
            agent_type=agent_type,
            level=level,
        )
        self._message_bus = message_bus
        self._config = config or {}
        self._message_queue: Optional[asyncio.Queue] = None
        self._running = False
        self._process_task: Optional[asyncio.Task] = None
        
        # LLM和工具系统
        self._llm = llm
        self._tool_registry = tool_registry
        self._tool_executor: Optional["ToolExecutor"] = None
        self._system_prompt = system_prompt or self._get_default_system_prompt()
        
        # 对话历史
        self._conversation_history: List["LLMMessage"] = []
        self._max_history_length = 50
        
    @property
    def agent_id(self) -> str:
        """Agent ID"""
        return self._info.agent_id
        
    @property
    def name(self) -> str:
        """Agent名称"""
        return self._info.name
        
    @property
    def agent_type(self) -> str:
        """Agent类型"""
        return self._info.agent_type
        
    @property
    def level(self) -> AgentLevel:
        """Agent层级"""
        return self._info.level
        
    @property
    def state(self) -> AgentState:
        """Agent状态"""
        return self._info.state
        
    @property
    def info(self) -> AgentInfo:
        """Agent信息"""
        return self._info
        
    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        return self._running and self._info.state == AgentState.RUNNING
        
    async def initialize(self) -> bool:
        """
        初始化Agent
        
        子类可以重写此方法进行自定义初始化。
        
        Returns:
            是否成功
        """
        self._info.state = AgentState.INITIALIZING
        self.logger.info(f"初始化Agent: {self.name}")
        
        try:
            # 注册到消息总线
            if self._message_bus:
                self._message_queue = self._message_bus.register(
                    self.agent_id,
                    handler=self._on_message,
                )
                
            # 调用子类初始化
            await self._on_initialize()
            
            self._info.state = AgentState.READY
            self.logger.info(f"Agent初始化完成: {self.name}")
            return True
            
        except Exception as e:
            self._info.state = AgentState.ERROR
            self._info.error_message = str(e)
            self.logger.error(f"Agent初始化失败: {self.name} - {e}")
            return False
            
    async def start(self) -> bool:
        """
        启动Agent
        
        Returns:
            是否成功
        """
        if self._info.state != AgentState.READY:
            self.logger.warning(f"Agent未就绪，无法启动: {self.name}")
            return False
            
        self.logger.info(f"启动Agent: {self.name}")
        
        try:
            self._running = True
            self._info.state = AgentState.RUNNING
            self._info.started_at = datetime.now()
            
            # 启动消息处理任务
            self._process_task = asyncio.create_task(self._message_loop())
            
            # 调用子类启动
            await self._on_start()
            
            self.logger.info(f"Agent启动完成: {self.name}")
            return True
            
        except Exception as e:
            self._info.state = AgentState.ERROR
            self._info.error_message = str(e)
            self.logger.error(f"Agent启动失败: {self.name} - {e}")
            return False
            
    async def stop(self) -> None:
        """停止Agent"""
        if not self._running:
            return
            
        self.logger.info(f"停止Agent: {self.name}")
        self._info.state = AgentState.STOPPING
        self._running = False
        
        # 取消消息处理任务
        if self._process_task and not self._process_task.done():
            self._process_task.cancel()
            try:
                await self._process_task
            except asyncio.CancelledError:
                pass
                
        # 从消息总线注销
        if self._message_bus:
            self._message_bus.unregister(self.agent_id)
            
        # 调用子类停止
        await self._on_stop()
        
        self._info.state = AgentState.STOPPED
        self.logger.info(f"Agent已停止: {self.name}")
        
    async def pause(self) -> None:
        """暂停Agent"""
        if self._info.state == AgentState.RUNNING:
            self._info.state = AgentState.PAUSED
            await self._on_pause()
            self.logger.info(f"Agent已暂停: {self.name}")
            
    async def resume(self) -> None:
        """恢复Agent"""
        if self._info.state == AgentState.PAUSED:
            self._info.state = AgentState.RUNNING
            await self._on_resume()
            self.logger.info(f"Agent已恢复: {self.name}")
            
    async def _message_loop(self) -> None:
        """消息处理循环"""
        while self._running:
            try:
                if self._message_bus and self._info.state == AgentState.RUNNING:
                    message = await self._message_bus.receive(
                        self.agent_id,
                        timeout=1.0,
                    )
                    if message:
                        await self._handle_message(message)
                else:
                    await asyncio.sleep(0.1)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"消息处理错误: {e}")
                await asyncio.sleep(0.1)
                
    async def _handle_message(self, message: Message) -> None:
        """
        处理消息
        
        Args:
            message: 消息
        """
        try:
            response = await self.process(message)
            
            if response and self._message_bus:
                await self._message_bus.respond(response)
                
        except Exception as e:
            self.logger.error(f"处理消息失败: {e}")
            
    async def send_message(self, message: Message) -> None:
        """
        发送消息
        
        Args:
            message: 消息
        """
        if self._message_bus:
            message.source = self.agent_id
            await self._message_bus.send(message)
            
    async def request(self, message: Message, timeout: float = 30.0) -> Optional[Message]:
        """
        发送请求并等待响应
        
        Args:
            message: 请求消息
            timeout: 超时时间
            
        Returns:
            响应消息
        """
        if self._message_bus:
            message.source = self.agent_id
            return await self._message_bus.request(message, timeout)
        return None
        
    # ============== 子类需要实现的方法 ==============
    
    @abstractmethod
    async def process(self, message: Message) -> Optional[Message]:
        """
        处理消息（核心处理逻辑）
        
        Args:
            message: 输入消息
            
        Returns:
            响应消息
        """
        pass
        
    async def _on_initialize(self) -> None:
        """初始化回调（子类可重写）"""
        pass
        
    async def _on_start(self) -> None:
        """启动回调（子类可重写）"""
        pass
        
    async def _on_stop(self) -> None:
        """停止回调（子类可重写）"""
        pass
        
    async def _on_pause(self) -> None:
        """暂停回调（子类可重写）"""
        pass
        
    async def _on_resume(self) -> None:
        """恢复回调（子类可重写）"""
        pass
        
    async def _on_message(self, message: "Message") -> None:
        """消息回调（子类可重写）"""
        pass
    
    # ============== LLM和工具系统方法 ==============
    
    def _get_default_system_prompt(self) -> str:
        """获取默认系统提示词"""
        return f"""你是 {self._info.name}，一个KaiBrain系统中的Agent。
你的类型是: {self._info.agent_type}
你的职责是处理分配给你的任务，使用可用的工具完成目标。
在执行操作前，请先思考计划，然后逐步执行。"""
    
    @property
    def llm(self) -> Optional["BaseLLM"]:
        """获取LLM实例"""
        return self._llm
    
    @llm.setter
    def llm(self, value: "BaseLLM") -> None:
        """设置LLM实例"""
        self._llm = value
    
    @property
    def tool_registry(self) -> Optional["ToolRegistry"]:
        """获取工具注册表"""
        return self._tool_registry
    
    @tool_registry.setter
    def tool_registry(self, value: "ToolRegistry") -> None:
        """设置工具注册表"""
        self._tool_registry = value
        # 创建执行器
        if value:
            from kaibrain.system.tools.executor import ToolExecutor
            self._tool_executor = ToolExecutor(value)
    
    @property
    def has_llm(self) -> bool:
        """是否有LLM能力"""
        return self._llm is not None
    
    @property
    def has_tools(self) -> bool:
        """是否有工具能力"""
        return self._tool_registry is not None
    
    async def think(
        self,
        prompt: str,
        context: Optional[Dict[str, Any]] = None,
        use_tools: bool = True,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> "LLMResponse":
        """
        思考 - 调用LLM进行推理
        
        Args:
            prompt: 用户输入/任务描述
            context: 额外上下文
            use_tools: 是否使用工具
            temperature: 温度参数
            max_tokens: 最大输出token
            
        Returns:
            LLM响应
            
        Raises:
            RuntimeError: 如果没有配置LLM
        """
        if not self._llm:
            raise RuntimeError(f"Agent {self.name} 没有配置LLM")
        
        from kaibrain.system.llm.message import LLMMessage, MessageRole
        
        # 构建消息列表
        messages = self._build_messages(prompt, context)
        
        # 获取工具列表
        tools = None
        if use_tools and self._tool_registry:
            tools = self._tool_registry.get_tools()
        
        # 调用LLM
        response = await self._llm.chat(
            messages=messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        
        # 记录到历史
        self._conversation_history.append(LLMMessage.user(prompt))
        if response.content:
            self._conversation_history.append(
                LLMMessage.assistant(response.content, response.tool_calls)
            )
        
        # 限制历史长度
        if len(self._conversation_history) > self._max_history_length:
            self._conversation_history = self._conversation_history[-self._max_history_length:]
        
        return response
    
    async def act(self, tool_call: "ToolCall") -> "ToolResult":
        """
        执行动作 - 调用工具
        
        Args:
            tool_call: 工具调用请求
            
        Returns:
            工具执行结果
            
        Raises:
            RuntimeError: 如果没有配置工具系统
        """
        if not self._tool_executor:
            if not self._tool_registry:
                raise RuntimeError(f"Agent {self.name} 没有配置工具系统")
            from kaibrain.system.tools.executor import ToolExecutor
            self._tool_executor = ToolExecutor(self._tool_registry)
        
        result = await self._tool_executor.execute(tool_call)
        
        # 记录工具结果到历史
        from kaibrain.system.llm.message import LLMMessage
        self._conversation_history.append(
            LLMMessage.tool(
                tool_call_id=tool_call.id,
                content=result.to_string(),
                name=tool_call.name,
            )
        )
        
        return result
    
    async def think_and_act(
        self,
        prompt: str,
        max_iterations: int = 10,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        思考并执行 - Agent Loop (ReAct模式)
        
        循环: 思考 -> 工具调用 -> 观察 -> 思考 -> ...
        直到LLM决定停止或达到最大迭代次数
        
        Args:
            prompt: 任务描述
            max_iterations: 最大迭代次数
            context: 额外上下文
            
        Returns:
            最终响应内容
        """
        from kaibrain.system.llm.message import FinishReason
        
        for i in range(max_iterations):
            self.logger.debug(f"Agent loop iteration {i+1}/{max_iterations}")
            
            # 思考
            response = await self.think(prompt if i == 0 else "", context=context)
            
            # 检查是否完成
            if response.finish_reason == FinishReason.STOP or not response.has_tool_calls:
                return response.content
            
            # 执行工具调用
            if response.tool_calls:
                for tool_call in response.tool_calls:
                    self.logger.info(f"执行工具: {tool_call.name}")
                    result = await self.act(tool_call)
                    
                    if result.is_error:
                        self.logger.warning(f"工具执行错误: {result.content}")
        
        # 达到最大迭代次数，进行最终总结
        final_response = await self.think(
            "请总结你的工作结果。",
            use_tools=False,
        )
        return final_response.content
    
    def _build_messages(
        self,
        prompt: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> List["LLMMessage"]:
        """
        构建消息列表
        
        Args:
            prompt: 用户输入
            context: 上下文
            
        Returns:
            消息列表
        """
        from kaibrain.system.llm.message import LLMMessage
        
        messages = []
        
        # 系统消息
        system_content = self._system_prompt
        if context:
            system_content += f"\n\n当前上下文:\n{json.dumps(context, ensure_ascii=False, indent=2)}"
        messages.append(LLMMessage.system(system_content))
        
        # 历史消息
        messages.extend(self._conversation_history)
        
        # 当前用户消息
        if prompt:
            messages.append(LLMMessage.user(prompt))
        
        return messages
    
    def clear_history(self) -> None:
        """清空对话历史"""
        self._conversation_history.clear()
    
    def get_available_tools(self) -> List[str]:
        """获取可用工具名称列表"""
        if not self._tool_registry:
            return []
        return self._tool_registry.list_tools()
