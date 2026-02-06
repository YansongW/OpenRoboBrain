"""
Context Builder

构建 Agent 执行上下文，包括：
- 系统提示词
- Bootstrap 文件注入
- 历史消息
- 工具定义
- 记忆

借鉴 Moltbot 的上下文组装设计。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from orb.system.services.logger import LoggerMixin

if TYPE_CHECKING:
    from orb.agent.infrastructure.workspace import WorkspaceManager
    from orb.agent.infrastructure.session_store import (
        Session,
        SessionMessage,
    )
    from orb.agent.runtime.tool_executor import ToolResult


@dataclass
class ContextConfig:
    """上下文配置"""
    # 系统提示词
    base_system_prompt: str = ""
    
    # Bootstrap 文件
    inject_bootstrap: bool = True
    bootstrap_files: List[str] = field(default_factory=lambda: [
        "AGENTS.md",
        "SOUL.md",
        "USER.md",
        "IDENTITY.md",
        "TOOLS.md",
    ])
    
    # 历史消息
    max_history_messages: int = 50
    include_tool_results: bool = True
    
    # 记忆
    inject_memory: bool = True
    memory_days: int = 2
    
    # Token 限制
    max_context_tokens: int = 100000
    reserve_tokens: int = 4000  # 为响应预留
    
    # 时区
    timezone: str = "Asia/Shanghai"


@dataclass
class MessageContext:
    """消息上下文"""
    role: str
    content: str
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于 API 调用）"""
        result = {
            "role": self.role,
            "content": self.content,
        }
        if self.name:
            result["name"] = self.name
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        if self.tool_calls:
            result["tool_calls"] = self.tool_calls
        return result


@dataclass
class AgentContext:
    """Agent 上下文"""
    # 消息列表（用于 LLM 调用）
    messages: List[MessageContext] = field(default_factory=list)
    
    # 系统信息
    system_prompt: str = ""
    agent_id: str = ""
    session_id: str = ""
    
    # 工具定义
    tools: List[Dict[str, Any]] = field(default_factory=list)
    tool_choice: str = "auto"
    
    # 模型参数
    model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 4096
    
    # 元数据
    token_estimate: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_api_format(self) -> Dict[str, Any]:
        """转换为 API 调用格式"""
        result = {
            "messages": [m.to_dict() for m in self.messages],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if self.model:
            result["model"] = self.model
        if self.tools:
            result["tools"] = self.tools
            result["tool_choice"] = self.tool_choice
        return result


class ContextBuilder(LoggerMixin):
    """
    上下文构建器
    
    负责构建 Agent 执行所需的完整上下文。
    """
    
    def __init__(
        self,
        config: ContextConfig,
        workspace: Optional[WorkspaceManager] = None,
    ):
        """
        初始化上下文构建器
        
        Args:
            config: 上下文配置
            workspace: 工作空间管理器
        """
        self._config = config
        self._workspace = workspace
        self._tool_definitions: List[Dict[str, Any]] = []
        
    @property
    def config(self) -> ContextConfig:
        """配置"""
        return self._config
        
    def set_workspace(self, workspace: WorkspaceManager) -> None:
        """设置工作空间"""
        self._workspace = workspace
        
    def register_tools(self, tools: List[Dict[str, Any]]) -> None:
        """
        注册工具定义
        
        Args:
            tools: 工具定义列表
        """
        self._tool_definitions = tools
        
    async def build(
        self,
        session: Optional[Session] = None,
        user_input: str = "",
        tool_results: Optional[List[ToolResult]] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> AgentContext:
        """
        构建 Agent 上下文
        
        Args:
            session: 会话对象
            user_input: 用户输入
            tool_results: 工具执行结果
            parameters: 额外参数
            
        Returns:
            Agent 上下文
        """
        parameters = parameters or {}
        
        context = AgentContext(
            agent_id=session.metadata.agent_id if session else "",
            session_id=session.session_id if session else "",
            model=parameters.get("model"),
            temperature=parameters.get("temperature", 0.7),
            max_tokens=parameters.get("max_tokens", 4096),
        )
        
        # 1. 构建系统提示词
        system_prompt = self._build_system_prompt()
        context.system_prompt = system_prompt
        
        # 添加系统消息
        context.messages.append(MessageContext(
            role="system",
            content=system_prompt,
        ))
        
        # 2. 添加历史消息
        if session:
            history_messages = self._build_history_messages(session)
            context.messages.extend(history_messages)
            
        # 3. 添加工具结果（如果是多轮对话）
        if tool_results:
            for result in tool_results:
                context.messages.append(MessageContext(
                    role="tool",
                    content=str(result.result),
                    tool_call_id=result.call_id,
                    name=result.tool_name,
                ))
                
        # 4. 添加当前用户输入
        if user_input:
            context.messages.append(MessageContext(
                role="user",
                content=user_input,
            ))
            
        # 5. 添加工具定义
        context.tools = self._tool_definitions
        
        # 6. 估算 token 数量
        context.token_estimate = self._estimate_tokens(context)
        
        # 7. 如果超出限制，进行压缩
        if context.token_estimate > self._config.max_context_tokens - self._config.reserve_tokens:
            context = self._compact_context(context)
            
        return context
        
    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        parts = []
        
        # 基础提示词
        if self._config.base_system_prompt:
            parts.append(self._config.base_system_prompt)
            
        # Bootstrap 文件
        if self._config.inject_bootstrap and self._workspace:
            bootstrap_content = self._get_bootstrap_content()
            if bootstrap_content:
                parts.append(bootstrap_content)
                
        # 记忆
        if self._config.inject_memory and self._workspace:
            memory_content = self._get_memory_content()
            if memory_content:
                parts.append(memory_content)
                
        # 时间信息
        now = datetime.now()
        time_info = f"\n当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')} ({self._config.timezone})"
        parts.append(time_info)
        
        return "\n\n".join(parts)
        
    def _get_bootstrap_content(self) -> str:
        """获取 bootstrap 文件内容"""
        if not self._workspace:
            return ""
            
        parts = []
        
        for filename in self._config.bootstrap_files:
            file_info = self._workspace.get_bootstrap_file(filename)
            
            if file_info.exists and file_info.content:
                parts.append(f"### {filename}\n{file_info.content}")
            else:
                parts.append(f"### {filename}\n[文件缺失]")
                
        if parts:
            return "## Agent Configuration\n\n" + "\n\n".join(parts)
        return ""
        
    def _get_memory_content(self) -> str:
        """获取记忆内容"""
        if not self._workspace:
            return ""
            
        memory_files = self._workspace.get_memory_files(days=self._config.memory_days)
        
        if not memory_files:
            return ""
            
        parts = ["## Recent Memory"]
        
        for memory_file in memory_files:
            try:
                content = memory_file.read_text(encoding="utf-8")
                date = memory_file.stem
                parts.append(f"### {date}\n{content}")
            except Exception as e:
                self.logger.warning(f"读取记忆文件失败 {memory_file}: {e}")
                
        return "\n\n".join(parts)
        
    def _build_history_messages(
        self,
        session: Session,
    ) -> List[MessageContext]:
        """
        构建历史消息
        
        Args:
            session: 会话对象
            
        Returns:
            消息列表
        """
        messages = []
        
        # 获取最近的历史消息
        history = session.messages[-self._config.max_history_messages:]
        
        for msg in history:
            role = msg.role.value
            
            # 跳过系统消息（已在系统提示词中）
            if role == "system":
                continue
                
            # 跳过工具结果（如果配置不包含）
            if role == "tool" and not self._config.include_tool_results:
                continue
                
            messages.append(MessageContext(
                role=role,
                content=msg.content,
                name=msg.tool_name,
                tool_call_id=msg.tool_call_id,
            ))
            
        return messages
        
    def _estimate_tokens(self, context: AgentContext) -> int:
        """
        估算 token 数量
        
        使用简单的字符数估算（实际应使用 tokenizer）
        
        Args:
            context: Agent 上下文
            
        Returns:
            估算的 token 数量
        """
        total_chars = 0
        
        for msg in context.messages:
            total_chars += len(msg.content)
            
        # 工具定义
        if context.tools:
            import json
            total_chars += len(json.dumps(context.tools))
            
        # 粗略估算：4 个字符 ≈ 1 个 token（中文可能更少）
        return total_chars // 3
        
    def _compact_context(self, context: AgentContext) -> AgentContext:
        """
        压缩上下文
        
        Args:
            context: 原始上下文
            
        Returns:
            压缩后的上下文
        """
        self.logger.info("上下文超出限制，进行压缩")
        
        # 策略：保留系统消息和最近的消息
        system_message = None
        other_messages = []
        
        for msg in context.messages:
            if msg.role == "system":
                system_message = msg
            else:
                other_messages.append(msg)
                
        # 保留最近的消息
        max_keep = self._config.max_history_messages // 2
        kept_messages = other_messages[-max_keep:]
        
        # 重建消息列表
        new_messages = []
        if system_message:
            new_messages.append(system_message)
        new_messages.extend(kept_messages)
        
        context.messages = new_messages
        context.token_estimate = self._estimate_tokens(context)
        context.metadata["compacted"] = True
        
        return context
        
    def build_subagent_context(
        self,
        task: str,
        parent_context: Optional[AgentContext] = None,
    ) -> AgentContext:
        """
        构建子 Agent 上下文
        
        子 Agent 只注入 AGENTS.md 和 TOOLS.md
        
        Args:
            task: 任务描述
            parent_context: 父上下文
            
        Returns:
            子 Agent 上下文
        """
        context = AgentContext()
        
        # 简化的系统提示词
        parts = ["You are a sub-agent tasked with a specific job."]
        
        # 只注入 AGENTS.md 和 TOOLS.md
        if self._workspace:
            for filename in ["AGENTS.md", "TOOLS.md"]:
                file_info = self._workspace.get_bootstrap_file(filename)
                if file_info.exists and file_info.content:
                    parts.append(f"### {filename}\n{file_info.content}")
                    
        system_prompt = "\n\n".join(parts)
        
        context.messages.append(MessageContext(
            role="system",
            content=system_prompt,
        ))
        
        context.messages.append(MessageContext(
            role="user",
            content=task,
        ))
        
        context.tools = self._tool_definitions
        context.metadata["is_subagent"] = True
        
        return context


# 便捷函数
def create_context_builder(
    workspace: Optional[WorkspaceManager] = None,
    **config_kwargs,
) -> ContextBuilder:
    """
    创建上下文构建器
    
    Args:
        workspace: 工作空间管理器
        **config_kwargs: 配置参数
        
    Returns:
        ContextBuilder 实例
    """
    config = ContextConfig(**config_kwargs)
    return ContextBuilder(config, workspace)
