"""
工具注册表

统一管理所有工具，支持内建工具、自定义工具和MCP工具。

借鉴 OpenClaw/Moltbot 的设计：
- 工具分组 (group shorthand)
- Tool Profile (预设配置)
- 权限控制集成
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, TYPE_CHECKING, Union

from orb.system.tools.base import Tool, ToolCall, ToolResult
from orb.system.services.logger import LoggerMixin, get_logger

if TYPE_CHECKING:
    from orb.system.tools.mcp.client import MCPClient
    from orb.agent.security.tool_policy import ToolPolicy

logger = get_logger(__name__)


class ToolGroup(Enum):
    """工具组定义"""
    RUNTIME = "group:runtime"       # exec, bash, process
    FS = "group:fs"                 # read, write, edit, apply_patch
    SESSIONS = "group:sessions"     # sessions_list, sessions_history, sessions_send
    MEMORY = "group:memory"         # memory_search, memory_get
    WEB = "group:web"               # web_search, web_fetch
    IMAGE = "group:image"           # image_generate, image_edit
    BROWSER = "group:browser"       # browser automation
    MESSAGING = "group:messaging"   # message
    ROBOT = "group:robot"           # locomotion, manipulation, sensing
    SENSORS = "group:sensors"       # camera, lidar, imu, etc
    ACTUATORS = "group:actuators"   # motors, grippers, etc


# 工具组到具体工具的映射
TOOL_GROUP_MEMBERS: Dict[str, List[str]] = {
    ToolGroup.RUNTIME.value: ["exec", "shell", "bash", "process", "background"],
    ToolGroup.FS.value: ["read_file", "write_file", "edit_file", "list_directory", "apply_patch", "delete_file"],
    ToolGroup.SESSIONS.value: ["sessions_list", "sessions_history", "sessions_send", "sessions_spawn", "session_status"],
    ToolGroup.MEMORY.value: ["memory_search", "memory_get", "memory_set", "memory_delete"],
    ToolGroup.WEB.value: ["web_search", "web_fetch", "http_request"],
    ToolGroup.IMAGE.value: ["image_generate", "image_edit", "image_analyze"],
    ToolGroup.BROWSER.value: ["browser_navigate", "browser_click", "browser_type", "browser_screenshot"],
    ToolGroup.MESSAGING.value: ["message", "notify", "send_message"],
    ToolGroup.ROBOT.value: ["move", "rotate", "grasp", "release", "navigate_to"],
    ToolGroup.SENSORS.value: ["camera_capture", "lidar_scan", "imu_read", "joint_states"],
    ToolGroup.ACTUATORS.value: ["motor_control", "gripper_control", "arm_control"],
}


@dataclass
class ToolProfile:
    """工具配置预设"""
    name: str
    description: str
    include_groups: List[str] = field(default_factory=list)
    include_tools: List[str] = field(default_factory=list)
    exclude_tools: List[str] = field(default_factory=list)
    
    def get_tool_names(self) -> Set[str]:
        """获取预设中的所有工具名"""
        tools = set(self.include_tools)
        for group in self.include_groups:
            if group in TOOL_GROUP_MEMBERS:
                tools.update(TOOL_GROUP_MEMBERS[group])
        tools -= set(self.exclude_tools)
        return tools


# 预定义配置
TOOL_PROFILES: Dict[str, ToolProfile] = {
    "minimal": ToolProfile(
        name="minimal",
        description="最小工具集，仅状态查询",
        include_tools=["session_status"],
    ),
    "coding": ToolProfile(
        name="coding",
        description="编程工具集",
        include_groups=[ToolGroup.FS.value, ToolGroup.RUNTIME.value, ToolGroup.MEMORY.value],
        include_tools=["sessions_list", "sessions_history"],
        exclude_tools=["browser_navigate", "browser_click"],
    ),
    "messaging": ToolProfile(
        name="messaging",
        description="消息工具集",
        include_groups=[ToolGroup.MESSAGING.value],
        include_tools=["sessions_list", "sessions_send", "image_generate"],
    ),
    "full": ToolProfile(
        name="full",
        description="完整工具集",
        include_groups=[g.value for g in ToolGroup],
    ),
    "robot_basic": ToolProfile(
        name="robot_basic",
        description="机器人基础工具集",
        include_groups=[ToolGroup.ROBOT.value, ToolGroup.SENSORS.value],
        exclude_tools=["shell", "exec"],
    ),
    "robot_full": ToolProfile(
        name="robot_full",
        description="机器人完整工具集",
        include_groups=[ToolGroup.ROBOT.value, ToolGroup.SENSORS.value, ToolGroup.ACTUATORS.value, ToolGroup.MEMORY.value],
    ),
}


class ToolRegistry(LoggerMixin):
    """
    工具注册表
    
    统一管理内建工具和MCP工具，支持：
    - 工具分组 (ToolGroup)
    - 配置预设 (ToolProfile)
    - 权限策略集成 (ToolPolicy)
    """
    
    def __init__(self, policy: Optional["ToolPolicy"] = None):
        """
        初始化工具注册表
        
        Args:
            policy: 工具权限策略
        """
        self._tools: Dict[str, Tool] = {}
        self._mcp_clients: Dict[str, "MCPClient"] = {}
        self._categories: Dict[str, List[str]] = {}  # 分类 -> 工具名列表
        self._groups: Dict[str, Set[str]] = {}       # 组 -> 工具名集合
        self._tool_to_groups: Dict[str, Set[str]] = {}  # 工具 -> 所属组集合
        self._policy = policy
        
        # 初始化组定义
        for group, members in TOOL_GROUP_MEMBERS.items():
            self._groups[group] = set(members)
    
    @property
    def policy(self) -> Optional["ToolPolicy"]:
        """工具权限策略"""
        return self._policy
        
    @policy.setter
    def policy(self, value: "ToolPolicy") -> None:
        """设置工具权限策略"""
        self._policy = value
    
    def register(
        self,
        tool: Tool,
        category: Optional[str] = None,
        groups: Optional[List[str]] = None,
    ) -> None:
        """
        注册工具
        
        Args:
            tool: 工具实例
            category: 工具分类
            groups: 所属工具组列表
        """
        if tool.name in self._tools:
            self.logger.warning(f"Tool {tool.name} already registered, overwriting")
        
        self._tools[tool.name] = tool
        
        # 分类
        if category:
            if category not in self._categories:
                self._categories[category] = []
            if tool.name not in self._categories[category]:
                self._categories[category].append(tool.name)
        
        # 组
        if groups:
            self._tool_to_groups[tool.name] = set(groups)
            for group in groups:
                if group not in self._groups:
                    self._groups[group] = set()
                self._groups[group].add(tool.name)
        
        # 自动添加到匹配的预定义组
        for group_name, members in TOOL_GROUP_MEMBERS.items():
            if tool.name in members:
                if tool.name not in self._tool_to_groups:
                    self._tool_to_groups[tool.name] = set()
                self._tool_to_groups[tool.name].add(group_name)
                self._groups[group_name].add(tool.name)
        
        self.logger.debug(f"Registered tool: {tool.name}")
    
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
            # 从分类中移除
            for category, tools in self._categories.items():
                if name in tools:
                    tools.remove(name)
            self.logger.debug(f"Unregistered tool: {name}")
            return True
        return False
    
    def get(self, name: str) -> Optional[Tool]:
        """
        获取工具
        
        Args:
            name: 工具名称
            
        Returns:
            Tool实例或None
        """
        return self._tools.get(name)
    
    def get_tools(
        self,
        names: Optional[List[str]] = None,
        category: Optional[str] = None,
        group: Optional[str] = None,
        profile: Optional[str] = None,
        agent_id: Optional[str] = None,
        apply_policy: bool = True,
    ) -> List[Tool]:
        """
        获取工具列表
        
        Args:
            names: 工具名称列表（可选）
            category: 分类（可选）
            group: 工具组（可选）
            profile: 配置预设名称（可选）
            agent_id: Agent ID（用于权限检查）
            apply_policy: 是否应用权限策略
            
        Returns:
            工具列表
        """
        # 收集候选工具
        candidates: Set[str] = set()
        
        if names:
            candidates = set(names)
        elif profile and profile in TOOL_PROFILES:
            candidates = TOOL_PROFILES[profile].get_tool_names()
        elif group:
            # 支持 "group:xxx" 格式
            group_key = group if group.startswith("group:") else f"group:{group}"
            if group_key in self._groups:
                candidates = self._groups[group_key].copy()
            elif group in self._groups:
                candidates = self._groups[group].copy()
        elif category and category in self._categories:
            candidates = set(self._categories[category])
        else:
            candidates = set(self._tools.keys())
            
        # 过滤出实际存在的工具
        tools = [self._tools[n] for n in candidates if n in self._tools]
        
        # 应用权限策略
        if apply_policy and self._policy:
            from orb.agent.security.tool_policy import PolicyDecision
            tools = [
                t for t in tools
                if self._policy.check(t.name, agent_id=agent_id) == PolicyDecision.ALLOW
            ]
        
        return tools
        
    def get_tools_by_groups(
        self,
        groups: List[str],
        agent_id: Optional[str] = None,
        apply_policy: bool = True,
    ) -> List[Tool]:
        """
        通过多个组获取工具
        
        Args:
            groups: 工具组列表
            agent_id: Agent ID
            apply_policy: 是否应用权限策略
            
        Returns:
            工具列表
        """
        candidates: Set[str] = set()
        
        for group in groups:
            group_key = group if group.startswith("group:") else f"group:{group}"
            if group_key in self._groups:
                candidates.update(self._groups[group_key])
            elif group in self._groups:
                candidates.update(self._groups[group])
                
        tools = [self._tools[n] for n in candidates if n in self._tools]
        
        if apply_policy and self._policy:
            from orb.agent.security.tool_policy import PolicyDecision
            tools = [
                t for t in tools
                if self._policy.check(t.name, agent_id=agent_id) == PolicyDecision.ALLOW
            ]
            
        return tools
    
    def get_tools_for_llm(
        self,
        provider: str = "openai",
        names: Optional[List[str]] = None,
        category: Optional[str] = None,
        group: Optional[str] = None,
        profile: Optional[str] = None,
        agent_id: Optional[str] = None,
        apply_policy: bool = True,
    ) -> List[dict]:
        """
        获取LLM格式的工具定义
        
        Args:
            provider: LLM提供商 ("openai", "anthropic", "mcp")
            names: 工具名称列表
            category: 分类
            group: 工具组
            profile: 配置预设
            agent_id: Agent ID（用于权限检查）
            apply_policy: 是否应用权限策略
            
        Returns:
            格式化的工具定义列表
        """
        tools = self.get_tools(
            names=names,
            category=category,
            group=group,
            profile=profile,
            agent_id=agent_id,
            apply_policy=apply_policy,
        )
        
        if provider == "openai":
            return [t.to_openai_format() for t in tools]
        elif provider == "anthropic":
            return [t.to_anthropic_format() for t in tools]
        elif provider == "mcp":
            return [t.to_mcp_format() for t in tools]
        
        return [t.to_dict() for t in tools]
    
    def list_tools(self) -> List[str]:
        """列出所有工具名称"""
        return list(self._tools.keys())
    
    def list_categories(self) -> List[str]:
        """列出所有分类"""
        return list(self._categories.keys())
        
    def list_groups(self) -> List[str]:
        """列出所有工具组"""
        return list(self._groups.keys())
        
    def list_profiles(self) -> List[str]:
        """列出所有配置预设"""
        return list(TOOL_PROFILES.keys())
        
    def get_tool_groups(self, tool_name: str) -> List[str]:
        """获取工具所属的组"""
        return list(self._tool_to_groups.get(tool_name, []))
        
    def get_group_tools(self, group: str) -> List[str]:
        """获取组内的所有工具"""
        group_key = group if group.startswith("group:") else f"group:{group}"
        if group_key in self._groups:
            return list(self._groups[group_key])
        return []
        
    def get_profile(self, name: str) -> Optional[ToolProfile]:
        """获取配置预设"""
        return TOOL_PROFILES.get(name)
        
    def add_tool_to_group(self, tool_name: str, group: str) -> bool:
        """
        将工具添加到组
        
        Args:
            tool_name: 工具名
            group: 组名
            
        Returns:
            是否成功
        """
        if tool_name not in self._tools:
            return False
            
        group_key = group if group.startswith("group:") else f"group:{group}"
        
        if group_key not in self._groups:
            self._groups[group_key] = set()
            
        self._groups[group_key].add(tool_name)
        
        if tool_name not in self._tool_to_groups:
            self._tool_to_groups[tool_name] = set()
        self._tool_to_groups[tool_name].add(group_key)
        
        return True
        
    def remove_tool_from_group(self, tool_name: str, group: str) -> bool:
        """
        从组中移除工具
        
        Args:
            tool_name: 工具名
            group: 组名
            
        Returns:
            是否成功
        """
        group_key = group if group.startswith("group:") else f"group:{group}"
        
        if group_key in self._groups:
            self._groups[group_key].discard(tool_name)
            
        if tool_name in self._tool_to_groups:
            self._tool_to_groups[tool_name].discard(group_key)
            
        return True
        
    def create_custom_profile(
        self,
        name: str,
        description: str,
        include_groups: Optional[List[str]] = None,
        include_tools: Optional[List[str]] = None,
        exclude_tools: Optional[List[str]] = None,
    ) -> ToolProfile:
        """
        创建自定义配置预设
        
        Args:
            name: 预设名称
            description: 描述
            include_groups: 包含的组
            include_tools: 包含的工具
            exclude_tools: 排除的工具
            
        Returns:
            ToolProfile 实例
        """
        profile = ToolProfile(
            name=name,
            description=description,
            include_groups=include_groups or [],
            include_tools=include_tools or [],
            exclude_tools=exclude_tools or [],
        )
        TOOL_PROFILES[name] = profile
        return profile
    
    # ============== MCP集成 ==============
    
    async def connect_mcp_server(
        self,
        server_id: str,
        transport: str,
        **config,
    ) -> int:
        """
        连接MCP Server并导入其工具
        
        Args:
            server_id: Server标识
            transport: 传输方式 ("stdio", "sse", "http")
            **config: 传输配置
            
        Returns:
            导入的工具数量
        """
        from orb.system.tools.mcp.client import MCPClient
        
        client = MCPClient(transport=transport, **config)
        await client.connect()
        
        # 发现并注册MCP工具
        mcp_tools = await client.list_tools()
        count = 0
        
        for mcp_tool in mcp_tools:
            tool = self._adapt_mcp_tool(mcp_tool, server_id, client)
            self.register(tool, category=f"mcp:{server_id}")
            count += 1
        
        self._mcp_clients[server_id] = client
        self.logger.info(f"Connected to MCP server {server_id}, imported {count} tools")
        
        return count
    
    async def disconnect_mcp_server(self, server_id: str) -> None:
        """
        断开MCP Server连接
        
        Args:
            server_id: Server标识
        """
        if server_id in self._mcp_clients:
            client = self._mcp_clients[server_id]
            await client.disconnect()
            del self._mcp_clients[server_id]
            
            # 移除该server的所有工具
            category = f"mcp:{server_id}"
            if category in self._categories:
                for tool_name in self._categories[category]:
                    if tool_name in self._tools:
                        del self._tools[tool_name]
                del self._categories[category]
            
            self.logger.info(f"Disconnected from MCP server {server_id}")
    
    def _adapt_mcp_tool(
        self,
        mcp_tool: dict,
        server_id: str,
        client: "MCPClient",
    ) -> Tool:
        """
        将MCP工具适配为内部Tool格式
        
        Args:
            mcp_tool: MCP工具定义
            server_id: Server标识
            client: MCP客户端
            
        Returns:
            Tool实例
        """
        name = mcp_tool.get("name", "")
        
        # 创建调用handler
        async def mcp_handler(**kwargs):
            return await client.call_tool(name, kwargs)
        
        return Tool(
            name=name,
            description=mcp_tool.get("description", ""),
            parameters=mcp_tool.get("inputSchema", {"type": "object", "properties": {}}),
            handler=mcp_handler,
            mcp_server=server_id,
            annotations=mcp_tool.get("annotations"),
            is_async=True,
        )
    
    def get_mcp_client(self, server_id: str) -> Optional["MCPClient"]:
        """获取MCP客户端"""
        return self._mcp_clients.get(server_id)
    
    # ============== 工具统计 ==============
    
    def stats(self) -> dict:
        """获取工具统计信息"""
        mcp_tools = [t for t in self._tools.values() if t.mcp_server]
        builtin_tools = [t for t in self._tools.values() if not t.mcp_server]
        
        # 组统计
        group_stats = {}
        for group_name, tools in self._groups.items():
            registered = [t for t in tools if t in self._tools]
            group_stats[group_name] = {
                "defined": len(tools),
                "registered": len(registered),
            }
        
        return {
            "total": len(self._tools),
            "builtin": len(builtin_tools),
            "mcp": len(mcp_tools),
            "categories": len(self._categories),
            "groups": len(self._groups),
            "profiles": len(TOOL_PROFILES),
            "mcp_servers": len(self._mcp_clients),
            "group_stats": group_stats,
        }


def tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
    category: Optional[str] = None,
    registry: Optional[ToolRegistry] = None,
):
    """
    工具注册装饰器
    
    用于将函数注册为工具。
    
    Args:
        name: 工具名称（默认使用函数名）
        description: 工具描述（默认使用docstring）
        category: 工具分类
        registry: 注册表实例
        
    Examples:
        @tool(name="read_file", category="file")
        async def read_file(path: str) -> str:
            '''读取文件内容'''
            ...
    """
    def decorator(func: Callable):
        tool_instance = Tool.from_function(
            func,
            name=name,
            description=description,
        )
        
        if registry:
            registry.register(tool_instance, category=category)
        
        # 将工具信息附加到函数上
        func._tool = tool_instance
        func._tool_category = category
        
        return func
    
    return decorator


# 全局默认注册表
_default_registry: Optional[ToolRegistry] = None


def get_default_registry() -> ToolRegistry:
    """获取默认工具注册表"""
    global _default_registry
    if _default_registry is None:
        _default_registry = ToolRegistry()
    return _default_registry


def set_default_registry(registry: ToolRegistry) -> None:
    """设置默认工具注册表"""
    global _default_registry
    _default_registry = registry


def create_registry_with_policy(
    policy: Optional["ToolPolicy"] = None,
    profile: Optional[str] = None,
) -> ToolRegistry:
    """
    创建带权限策略的工具注册表
    
    Args:
        policy: 工具权限策略
        profile: 默认配置预设
        
    Returns:
        ToolRegistry 实例
    """
    registry = ToolRegistry(policy=policy)
    return registry


def get_profile_tools(profile_name: str) -> List[str]:
    """
    获取预设中的工具名列表
    
    Args:
        profile_name: 预设名称
        
    Returns:
        工具名列表
    """
    if profile_name in TOOL_PROFILES:
        return list(TOOL_PROFILES[profile_name].get_tool_names())
    return []


def expand_tool_groups(tools_or_groups: List[str]) -> Set[str]:
    """
    展开工具列表中的组引用
    
    Args:
        tools_or_groups: 工具名或组名列表
        
    Returns:
        展开后的工具名集合
    """
    result: Set[str] = set()
    
    for item in tools_or_groups:
        if item.startswith("group:"):
            if item in TOOL_GROUP_MEMBERS:
                result.update(TOOL_GROUP_MEMBERS[item])
        else:
            result.add(item)
            
    return result
