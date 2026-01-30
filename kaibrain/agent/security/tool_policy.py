"""
Tool Policy

工具策略系统，支持多级工具过滤：
1. Tool profile (预设配置)
2. Global tool policy
3. Agent-specific tool policy  
4. Sandbox tool policy
5. Subagent tool policy

借鉴 Moltbot 的工具策略设计。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from kaibrain.system.services.logger import LoggerMixin


class ToolGroup(Enum):
    """工具组（简写）"""
    RUNTIME = "group:runtime"      # exec, bash, process
    FS = "group:fs"                # read, write, edit, apply_patch
    SESSIONS = "group:sessions"    # sessions_list, sessions_history, sessions_send, sessions_spawn
    MEMORY = "group:memory"        # memory_search, memory_get
    UI = "group:ui"                # browser, canvas
    AUTOMATION = "group:automation"  # cron, gateway
    MESSAGING = "group:messaging"  # message
    NODES = "group:nodes"          # nodes
    ALL = "group:all"              # 所有工具


# 工具组展开映射
TOOL_GROUP_EXPANSIONS = {
    ToolGroup.RUNTIME: ["exec", "bash", "process"],
    ToolGroup.FS: ["read", "write", "edit", "apply_patch"],
    ToolGroup.SESSIONS: ["sessions_list", "sessions_history", "sessions_send", "sessions_spawn", "session_status"],
    ToolGroup.MEMORY: ["memory_search", "memory_get"],
    ToolGroup.UI: ["browser", "canvas"],
    ToolGroup.AUTOMATION: ["cron", "gateway"],
    ToolGroup.MESSAGING: ["message"],
    ToolGroup.NODES: ["nodes"],
}


class PolicyDecision(Enum):
    """策略决策"""
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


@dataclass
class ToolPolicyConfig:
    """工具策略配置"""
    # 允许列表（优先级低于拒绝列表）
    allow: List[str] = field(default_factory=lambda: ["*"])
    
    # 拒绝列表（最高优先级）
    deny: List[str] = field(default_factory=list)
    
    # 需要审批的工具
    require_approval: List[str] = field(default_factory=list)
    
    # 预设配置
    profile: Optional[str] = None
    
    # 是否启用
    enabled: bool = True


# 预设策略配置
POLICY_PROFILES = {
    "full": ToolPolicyConfig(
        allow=["*"],
        deny=[],
    ),
    "coding": ToolPolicyConfig(
        allow=["read", "write", "edit", "apply_patch", "exec", "process"],
        deny=["browser", "gateway", "cron"],
    ),
    "messaging": ToolPolicyConfig(
        allow=["message", "sessions_list", "sessions_send", "sessions_history"],
        deny=["exec", "write", "edit", "apply_patch"],
    ),
    "readonly": ToolPolicyConfig(
        allow=["read", "sessions_list", "sessions_history"],
        deny=["exec", "write", "edit", "apply_patch", "process"],
    ),
    "safe": ToolPolicyConfig(
        allow=["read", "message"],
        deny=["exec", "write", "edit", "apply_patch", "process", "browser", "gateway"],
    ),
}


class ToolPolicy(LoggerMixin):
    """
    工具策略
    
    支持多级策略过滤，每一级只能进一步限制，不能放宽。
    """
    
    def __init__(
        self,
        global_config: Optional[ToolPolicyConfig] = None,
    ):
        """
        初始化工具策略
        
        Args:
            global_config: 全局配置
        """
        self._global_config = global_config or ToolPolicyConfig()
        self._agent_configs: Dict[str, ToolPolicyConfig] = {}
        self._sandbox_config: Optional[ToolPolicyConfig] = None
        self._subagent_config: Optional[ToolPolicyConfig] = None
        
        # 缓存展开后的工具列表
        self._cache: Dict[str, Set[str]] = {}
        
    @property
    def global_config(self) -> ToolPolicyConfig:
        """全局配置"""
        return self._global_config
        
    def set_global_config(self, config: ToolPolicyConfig) -> None:
        """设置全局配置"""
        self._global_config = config
        self._invalidate_cache()
        
    def set_agent_config(self, agent_id: str, config: ToolPolicyConfig) -> None:
        """
        设置 Agent 配置
        
        Args:
            agent_id: Agent ID
            config: 配置
        """
        self._agent_configs[agent_id] = config
        self._invalidate_cache()
        
    def get_agent_config(self, agent_id: str) -> Optional[ToolPolicyConfig]:
        """获取 Agent 配置"""
        return self._agent_configs.get(agent_id)
        
    def set_sandbox_config(self, config: ToolPolicyConfig) -> None:
        """设置沙箱配置"""
        self._sandbox_config = config
        self._invalidate_cache()
        
    def set_subagent_config(self, config: ToolPolicyConfig) -> None:
        """设置子 Agent 配置"""
        self._subagent_config = config
        self._invalidate_cache()
        
    def _invalidate_cache(self) -> None:
        """清除缓存"""
        self._cache.clear()
        
    def _expand_tools(self, tools: List[str]) -> Set[str]:
        """
        展开工具列表（处理组和通配符）
        
        Args:
            tools: 工具列表
            
        Returns:
            展开后的工具集合
        """
        expanded = set()
        
        for tool in tools:
            # 检查是否是组
            if tool.startswith("group:"):
                try:
                    group = ToolGroup(tool)
                    if group in TOOL_GROUP_EXPANSIONS:
                        expanded.update(TOOL_GROUP_EXPANSIONS[group])
                except ValueError:
                    pass
            # 通配符
            elif tool == "*":
                expanded.add("*")
            else:
                expanded.add(tool)
                
        return expanded
        
    def _apply_config(
        self,
        current_allow: Set[str],
        current_deny: Set[str],
        config: ToolPolicyConfig,
    ) -> tuple[Set[str], Set[str]]:
        """
        应用配置层（只能进一步限制）
        
        Args:
            current_allow: 当前允许集合
            current_deny: 当前拒绝集合
            config: 配置
            
        Returns:
            更新后的 (allow, deny) 集合
        """
        if not config.enabled:
            return current_allow, current_deny
            
        # 获取预设
        if config.profile and config.profile in POLICY_PROFILES:
            profile = POLICY_PROFILES[config.profile]
            config_allow = self._expand_tools(profile.allow)
            config_deny = self._expand_tools(profile.deny)
        else:
            config_allow = self._expand_tools(config.allow)
            config_deny = self._expand_tools(config.deny)
            
        # 拒绝列表总是累加
        new_deny = current_deny | config_deny
        
        # 允许列表取交集（只能进一步限制）
        if "*" in current_allow:
            new_allow = config_allow
        elif "*" in config_allow:
            new_allow = current_allow
        else:
            new_allow = current_allow & config_allow
            
        # 从允许中移除被拒绝的
        new_allow = new_allow - new_deny
        
        return new_allow, new_deny
        
    def check(
        self,
        tool_name: str,
        agent_id: Optional[str] = None,
        is_sandbox: bool = False,
        is_subagent: bool = False,
    ) -> PolicyDecision:
        """
        检查工具是否允许
        
        Args:
            tool_name: 工具名称
            agent_id: Agent ID
            is_sandbox: 是否在沙箱中
            is_subagent: 是否是子 Agent
            
        Returns:
            策略决策
        """
        # 构建缓存键
        cache_key = f"{tool_name}:{agent_id}:{is_sandbox}:{is_subagent}"
        
        # 检查缓存
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if tool_name in cached:
                return PolicyDecision.ALLOW
            return PolicyDecision.DENY
            
        # 初始：全部允许
        allow: Set[str] = {"*"}
        deny: Set[str] = set()
        
        # 1. 应用全局配置
        allow, deny = self._apply_config(allow, deny, self._global_config)
        
        # 2. 应用 Agent 配置
        if agent_id and agent_id in self._agent_configs:
            allow, deny = self._apply_config(allow, deny, self._agent_configs[agent_id])
            
        # 3. 应用沙箱配置
        if is_sandbox and self._sandbox_config:
            allow, deny = self._apply_config(allow, deny, self._sandbox_config)
            
        # 4. 应用子 Agent 配置
        if is_subagent and self._subagent_config:
            allow, deny = self._apply_config(allow, deny, self._subagent_config)
            
        # 缓存结果
        self._cache[cache_key] = allow
        
        # 检查
        if tool_name in deny:
            return PolicyDecision.DENY
            
        if "*" in allow or tool_name in allow:
            # 检查是否需要审批
            require_approval = (
                self._global_config.require_approval +
                (self._agent_configs.get(agent_id, ToolPolicyConfig()).require_approval if agent_id else [])
            )
            if tool_name in require_approval:
                return PolicyDecision.REQUIRE_APPROVAL
            return PolicyDecision.ALLOW
            
        return PolicyDecision.DENY
        
    def filter_tools(
        self,
        tools: List[str],
        agent_id: Optional[str] = None,
        is_sandbox: bool = False,
        is_subagent: bool = False,
    ) -> List[str]:
        """
        过滤工具列表
        
        Args:
            tools: 工具列表
            agent_id: Agent ID
            is_sandbox: 是否在沙箱中
            is_subagent: 是否是子 Agent
            
        Returns:
            允许的工具列表
        """
        return [
            tool for tool in tools
            if self.check(tool, agent_id, is_sandbox, is_subagent) == PolicyDecision.ALLOW
        ]
        
    def get_allowed_tools(
        self,
        agent_id: Optional[str] = None,
        is_sandbox: bool = False,
        is_subagent: bool = False,
        available_tools: Optional[List[str]] = None,
    ) -> List[str]:
        """
        获取允许的工具列表
        
        Args:
            agent_id: Agent ID
            is_sandbox: 是否在沙箱中
            is_subagent: 是否是子 Agent
            available_tools: 可用工具列表
            
        Returns:
            允许的工具列表
        """
        if available_tools:
            return self.filter_tools(available_tools, agent_id, is_sandbox, is_subagent)
            
        # 返回所有展开的允许工具
        all_tools = set()
        for group in TOOL_GROUP_EXPANSIONS.values():
            all_tools.update(group)
            
        return self.filter_tools(list(all_tools), agent_id, is_sandbox, is_subagent)
        
    def get_info(self) -> Dict[str, Any]:
        """获取策略信息"""
        return {
            "global": {
                "allow": self._global_config.allow,
                "deny": self._global_config.deny,
                "profile": self._global_config.profile,
            },
            "agents": {
                agent_id: {
                    "allow": config.allow,
                    "deny": config.deny,
                    "profile": config.profile,
                }
                for agent_id, config in self._agent_configs.items()
            },
            "sandbox": {
                "allow": self._sandbox_config.allow if self._sandbox_config else [],
                "deny": self._sandbox_config.deny if self._sandbox_config else [],
            } if self._sandbox_config else None,
            "subagent": {
                "allow": self._subagent_config.allow if self._subagent_config else [],
                "deny": self._subagent_config.deny if self._subagent_config else [],
            } if self._subagent_config else None,
        }


# 便捷函数
def create_tool_policy(
    profile: Optional[str] = None,
    allow: Optional[List[str]] = None,
    deny: Optional[List[str]] = None,
) -> ToolPolicy:
    """
    创建工具策略
    
    Args:
        profile: 预设配置名称
        allow: 允许列表
        deny: 拒绝列表
        
    Returns:
        ToolPolicy 实例
    """
    config = ToolPolicyConfig(
        profile=profile,
        allow=allow if allow is not None else ["*"],
        deny=deny if deny is not None else [],
    )
    return ToolPolicy(config)
