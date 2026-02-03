"""
Tool Executor

工具调用执行器，负责：
- 工具注册和管理
- 工具调用解析
- 工具执行（含策略强制执行）
- 结果处理

安全特性：
- 工具策略强制执行：所有工具调用必须通过策略检查
- 策略检查在执行层进行，无法绕过

借鉴 Moltbot 的工具执行设计。
"""

from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union, TYPE_CHECKING
from uuid import uuid4

from kaibrain.system.services.logger import LoggerMixin

if TYPE_CHECKING:
    from kaibrain.agent.security.tool_policy import ToolPolicy, PolicyDecision


class ToolResultStatus(Enum):
    """工具执行结果状态"""
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"
    DENIED = "denied"


@dataclass
class ToolCall:
    """工具调用"""
    call_id: str = field(default_factory=lambda: str(uuid4()))
    tool_name: str = ""
    arguments: Dict[str, Any] = field(default_factory=dict)
    raw_arguments: Optional[str] = None  # 原始 JSON 字符串
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ToolCall:
        """从字典创建"""
        return cls(
            call_id=data.get("id", str(uuid4())),
            tool_name=data.get("function", {}).get("name", ""),
            arguments=json.loads(data.get("function", {}).get("arguments", "{}")),
            raw_arguments=data.get("function", {}).get("arguments"),
        )


@dataclass
class ToolResult:
    """工具执行结果"""
    call_id: str
    tool_name: str
    status: ToolResultStatus = ToolResultStatus.SUCCESS
    result: Any = None
    error: Optional[str] = None
    executed_at: str = field(default_factory=lambda: datetime.now().isoformat())
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "executed_at": self.executed_at,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
        }
        
    def to_string(self) -> str:
        """转换为字符串（用于 LLM 响应）"""
        if self.status == ToolResultStatus.SUCCESS:
            return json.dumps(self.result, ensure_ascii=False, indent=2)
        elif self.error:
            return f"Error: {self.error}"
        else:
            return f"Status: {self.status.value}"


@dataclass
class ToolDefinition:
    """工具定义"""
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema
    handler: Callable
    is_async: bool = False
    timeout: float = 60.0
    requires_approval: bool = False
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_api_format(self) -> Dict[str, Any]:
        """转换为 API 格式（OpenAI function calling）"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


# 类型定义
ToolHandler = Callable[..., Any]
ToolFilter = Callable[[ToolDefinition], bool]


class ToolRegistry(LoggerMixin):
    """
    工具注册表
    
    管理所有可用工具的注册和查询。
    """
    
    def __init__(self):
        """初始化工具注册表"""
        self._tools: Dict[str, ToolDefinition] = {}
        
    def register(
        self,
        name: str,
        handler: ToolHandler,
        description: str = "",
        parameters: Optional[Dict[str, Any]] = None,
        timeout: float = 60.0,
        requires_approval: bool = False,
        tags: Optional[List[str]] = None,
    ) -> None:
        """
        注册工具
        
        Args:
            name: 工具名称
            handler: 处理函数
            description: 描述
            parameters: 参数 schema
            timeout: 超时时间
            requires_approval: 是否需要审批
            tags: 标签
        """
        is_async = asyncio.iscoroutinefunction(handler)
        
        # 如果没有提供参数 schema，尝试从函数签名推断
        if parameters is None:
            parameters = self._infer_parameters(handler)
            
        tool = ToolDefinition(
            name=name,
            description=description or handler.__doc__ or "",
            parameters=parameters,
            handler=handler,
            is_async=is_async,
            timeout=timeout,
            requires_approval=requires_approval,
            tags=tags or [],
        )
        
        self._tools[name] = tool
        self.logger.debug(f"注册工具: {name}")
        
    def register_decorator(
        self,
        name: Optional[str] = None,
        description: str = "",
        parameters: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Callable[[ToolHandler], ToolHandler]:
        """
        装饰器方式注册工具
        
        Args:
            name: 工具名称（默认使用函数名）
            description: 描述
            parameters: 参数 schema
            **kwargs: 其他参数
            
        Returns:
            装饰器
        """
        def decorator(handler: ToolHandler) -> ToolHandler:
            tool_name = name or handler.__name__
            self.register(
                name=tool_name,
                handler=handler,
                description=description,
                parameters=parameters,
                **kwargs,
            )
            return handler
        return decorator
        
    def _infer_parameters(self, handler: ToolHandler) -> Dict[str, Any]:
        """从函数签名推断参数 schema"""
        sig = inspect.signature(handler)
        
        properties = {}
        required = []
        
        for param_name, param in sig.parameters.items():
            if param_name in ["self", "cls"]:
                continue
                
            prop = {"type": "string"}  # 默认类型
            
            # 尝试从类型注解推断
            if param.annotation != inspect.Parameter.empty:
                anno = param.annotation
                if anno == int:
                    prop["type"] = "integer"
                elif anno == float:
                    prop["type"] = "number"
                elif anno == bool:
                    prop["type"] = "boolean"
                elif anno == list:
                    prop["type"] = "array"
                elif anno == dict:
                    prop["type"] = "object"
                    
            properties[param_name] = prop
            
            # 没有默认值的参数是必需的
            if param.default == inspect.Parameter.empty:
                required.append(param_name)
                
        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }
        
    def unregister(self, name: str) -> bool:
        """
        注销工具
        
        Args:
            name: 工具名称
            
        Returns:
            是否成功
        """
        if name in self._tools:
            del self._tools[name]
            return True
        return False
        
    def get(self, name: str) -> Optional[ToolDefinition]:
        """
        获取工具
        
        Args:
            name: 工具名称
            
        Returns:
            工具定义
        """
        return self._tools.get(name)
        
    def list(
        self,
        tags: Optional[List[str]] = None,
        filter_func: Optional[ToolFilter] = None,
    ) -> List[ToolDefinition]:
        """
        列出工具
        
        Args:
            tags: 过滤标签
            filter_func: 过滤函数
            
        Returns:
            工具列表
        """
        tools = list(self._tools.values())
        
        if tags:
            tools = [t for t in tools if any(tag in t.tags for tag in tags)]
            
        if filter_func:
            tools = [t for t in tools if filter_func(t)]
            
        return tools
        
    def get_api_definitions(
        self,
        filter_func: Optional[ToolFilter] = None,
    ) -> List[Dict[str, Any]]:
        """
        获取 API 格式的工具定义列表
        
        Args:
            filter_func: 过滤函数
            
        Returns:
            工具定义列表
        """
        tools = self.list(filter_func=filter_func)
        return [t.to_api_format() for t in tools]


class ToolExecutor(LoggerMixin):
    """
    工具执行器
    
    负责解析和执行工具调用。
    
    安全特性：
    - 强制执行工具策略：如果配置了 policy，所有工具调用必须通过策略检查
    - 策略检查在 execute() 中进行，无法被绕过
    - 被拒绝的工具调用返回 DENIED 状态
    """
    
    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        default_timeout: float = 60.0,
        policy: Optional["ToolPolicy"] = None,
        enforce_policy: bool = True,
    ):
        """
        初始化工具执行器
        
        Args:
            registry: 工具注册表
            default_timeout: 默认超时时间
            policy: 工具策略（如果提供，将强制执行策略检查）
            enforce_policy: 是否强制执行策略（默认 True）
        """
        self._registry = registry or ToolRegistry()
        self._default_timeout = default_timeout
        self._policy = policy
        self._enforce_policy = enforce_policy
        
        # 执行统计
        self._execution_count = 0
        self._error_count = 0
        self._denied_count = 0  # 被策略拒绝的次数
    
    @property
    def policy(self) -> Optional["ToolPolicy"]:
        """工具策略"""
        return self._policy
    
    def set_policy(self, policy: Optional["ToolPolicy"]) -> None:
        """
        设置工具策略
        
        Args:
            policy: 工具策略
        """
        self._policy = policy
        self.logger.info(f"工具执行器策略已更新: policy={'已配置' if policy else '无'}")
        
    @property
    def registry(self) -> ToolRegistry:
        """工具注册表"""
        return self._registry
        
    def parse_tool_call(self, data: Union[Dict[str, Any], str]) -> ToolCall:
        """
        解析工具调用
        
        Args:
            data: 工具调用数据
            
        Returns:
            ToolCall 对象
        """
        if isinstance(data, str):
            data = json.loads(data)
            
        return ToolCall.from_dict(data)
        
    async def execute(
        self,
        tool_call: ToolCall,
        context: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        """
        执行工具调用
        
        执行流程：
        1. 工具存在检查
        2. 策略检查（如果配置了 policy）
        3. 工具执行
        
        Args:
            tool_call: 工具调用
            context: 执行上下文，可包含:
                - agent_id: Agent ID
                - is_sandbox: 是否在沙箱中
                - is_subagent: 是否是子 Agent
            
        Returns:
            执行结果
        """
        start_time = datetime.now()
        self._execution_count += 1
        context = context or {}
        
        # 获取工具定义
        tool = self._registry.get(tool_call.tool_name)
        
        if not tool:
            self._error_count += 1
            return ToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status=ToolResultStatus.ERROR,
                error=f"工具不存在: {tool_call.tool_name}",
            )
        
        # ========== 策略检查（安全关键）==========
        if self._policy and self._enforce_policy:
            try:
                from kaibrain.agent.security.tool_policy import PolicyDecision
                
                decision = self._policy.check(
                    tool_name=tool_call.tool_name,
                    agent_id=context.get("agent_id"),
                    is_sandbox=context.get("is_sandbox", False),
                    is_subagent=context.get("is_subagent", False),
                )
                
                if decision == PolicyDecision.DENY:
                    self._denied_count += 1
                    self.logger.warning(
                        f"工具调用被策略拒绝: {tool_call.tool_name} "
                        f"(agent={context.get('agent_id')}, "
                        f"sandbox={context.get('is_sandbox')}, "
                        f"subagent={context.get('is_subagent')})"
                    )
                    return self.deny_tool_call(
                        tool_call,
                        f"工具 '{tool_call.tool_name}' 被策略拒绝",
                    )
                    
                elif decision == PolicyDecision.REQUIRE_APPROVAL:
                    # TODO: 实现审批流程
                    # 目前暂时拒绝需要审批的工具
                    self._denied_count += 1
                    self.logger.warning(
                        f"工具调用需要审批（当前拒绝）: {tool_call.tool_name}"
                    )
                    return self.deny_tool_call(
                        tool_call,
                        f"工具 '{tool_call.tool_name}' 需要审批，当前暂不支持",
                    )
                    
                # PolicyDecision.ALLOW - 继续执行
                
            except ImportError as e:
                self.logger.error(f"无法加载策略模块: {e}")
                # 如果策略模块无法加载但配置了策略，安全起见拒绝执行
                return self.deny_tool_call(
                    tool_call,
                    "策略模块加载失败，工具调用被拒绝",
                )
        # ========== 策略检查结束 ==========
            
        # 执行工具
        try:
            timeout = tool.timeout or self._default_timeout
            
            if tool.is_async:
                result = await asyncio.wait_for(
                    tool.handler(**tool_call.arguments),
                    timeout=timeout,
                )
            else:
                # 在线程池中运行同步函数
                loop = asyncio.get_event_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: tool.handler(**tool_call.arguments),
                    ),
                    timeout=timeout,
                )
                
            duration = (datetime.now() - start_time).total_seconds() * 1000
            
            return ToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status=ToolResultStatus.SUCCESS,
                result=result,
                duration_ms=duration,
            )
            
        except asyncio.TimeoutError:
            self._error_count += 1
            duration = (datetime.now() - start_time).total_seconds() * 1000
            
            return ToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status=ToolResultStatus.TIMEOUT,
                error=f"工具执行超时 ({timeout}s)",
                duration_ms=duration,
            )
            
        except Exception as e:
            self._error_count += 1
            duration = (datetime.now() - start_time).total_seconds() * 1000
            
            self.logger.error(f"工具执行失败 {tool_call.tool_name}: {e}")
            
            return ToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status=ToolResultStatus.ERROR,
                error=str(e),
                duration_ms=duration,
            )
            
    async def execute_batch(
        self,
        tool_calls: List[ToolCall],
        parallel: bool = False,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[ToolResult]:
        """
        批量执行工具调用
        
        Args:
            tool_calls: 工具调用列表
            parallel: 是否并行执行
            context: 执行上下文
            
        Returns:
            结果列表
        """
        if parallel:
            tasks = [self.execute(tc, context) for tc in tool_calls]
            return await asyncio.gather(*tasks)
        else:
            results = []
            for tc in tool_calls:
                result = await self.execute(tc, context)
                results.append(result)
            return results
            
    def skip_tool_call(
        self,
        tool_call: ToolCall,
        reason: str = "Skipped due to queued user message",
    ) -> ToolResult:
        """
        跳过工具调用
        
        Args:
            tool_call: 工具调用
            reason: 跳过原因
            
        Returns:
            跳过结果
        """
        return ToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status=ToolResultStatus.SKIPPED,
            error=reason,
        )
        
    def deny_tool_call(
        self,
        tool_call: ToolCall,
        reason: str = "Tool call denied by policy",
    ) -> ToolResult:
        """
        拒绝工具调用
        
        Args:
            tool_call: 工具调用
            reason: 拒绝原因
            
        Returns:
            拒绝结果
        """
        return ToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status=ToolResultStatus.DENIED,
            error=reason,
        )
        
    def get_stats(self) -> Dict[str, Any]:
        """
        获取执行统计
        
        Returns:
            统计信息
        """
        return {
            "execution_count": self._execution_count,
            "error_count": self._error_count,
            "denied_count": self._denied_count,
            "success_rate": (
                (self._execution_count - self._error_count - self._denied_count) / self._execution_count
                if self._execution_count > 0 else 0
            ),
            "registered_tools": len(self._registry._tools),
            "policy_enabled": self._policy is not None and self._enforce_policy,
        }


# 便捷函数
def create_tool_executor(
    tools: Optional[List[Dict[str, Any]]] = None,
    **kwargs,
) -> ToolExecutor:
    """
    创建工具执行器
    
    Args:
        tools: 初始工具列表
        **kwargs: 其他参数
        
    Returns:
        ToolExecutor 实例
    """
    executor = ToolExecutor(**kwargs)
    
    if tools:
        for tool in tools:
            executor.registry.register(
                name=tool["name"],
                handler=tool["handler"],
                description=tool.get("description", ""),
                parameters=tool.get("parameters"),
            )
            
    return executor


# 内置工具示例
def register_builtin_tools(registry: ToolRegistry) -> None:
    """注册内置工具"""
    
    @registry.register_decorator(
        name="read_file",
        description="读取文件内容",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
            },
            "required": ["path"],
        },
        tags=["fs", "read"],
    )
    def read_file(path: str) -> str:
        """读取文件内容"""
        from pathlib import Path
        return Path(path).read_text(encoding="utf-8")
        
    @registry.register_decorator(
        name="write_file",
        description="写入文件内容",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "content": {"type": "string", "description": "文件内容"},
            },
            "required": ["path", "content"],
        },
        tags=["fs", "write"],
    )
    def write_file(path: str, content: str) -> str:
        """写入文件内容"""
        from pathlib import Path
        Path(path).write_text(content, encoding="utf-8")
        return f"文件已写入: {path}"
        
    @registry.register_decorator(
        name="list_directory",
        description="列出目录内容",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "目录路径"},
            },
            "required": ["path"],
        },
        tags=["fs", "read"],
    )
    def list_directory(path: str) -> List[str]:
        """列出目录内容"""
        from pathlib import Path
        return [str(p) for p in Path(path).iterdir()]
