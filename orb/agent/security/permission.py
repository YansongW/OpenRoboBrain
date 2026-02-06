"""
Permission Manager

权限管理系统。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from orb.system.services.logger import LoggerMixin


class PermissionLevel(Enum):
    """权限级别"""
    NONE = 0
    READ = 1
    WRITE = 2
    EXECUTE = 3
    ADMIN = 4
    SUPER = 5


@dataclass
class Permission:
    """权限定义"""
    name: str
    level: PermissionLevel = PermissionLevel.READ
    resource: str = "*"  # 资源模式
    actions: List[str] = field(default_factory=list)
    conditions: Dict[str, Any] = field(default_factory=dict)
    
    def matches(self, resource: str, action: str) -> bool:
        """
        检查是否匹配
        
        Args:
            resource: 资源
            action: 动作
            
        Returns:
            是否匹配
        """
        # 资源匹配
        if self.resource != "*":
            if not resource.startswith(self.resource.rstrip("*")):
                return False
                
        # 动作匹配
        if self.actions and action not in self.actions:
            return False
            
        return True


@dataclass
class PermissionGrant:
    """权限授予"""
    permission: Permission
    grantee: str  # 被授予者 ID
    grantor: str = ""  # 授予者 ID
    expires_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class PermissionManager(LoggerMixin):
    """
    权限管理器
    
    管理 Agent 和资源的权限。
    """
    
    def __init__(self):
        """初始化权限管理器"""
        self._grants: Dict[str, List[PermissionGrant]] = {}  # grantee -> grants
        self._roles: Dict[str, List[Permission]] = {}  # role -> permissions
        self._agent_roles: Dict[str, Set[str]] = {}  # agent -> roles
        
    # ============== 角色管理 ==============
    
    def define_role(self, role_name: str, permissions: List[Permission]) -> None:
        """
        定义角色
        
        Args:
            role_name: 角色名称
            permissions: 权限列表
        """
        self._roles[role_name] = permissions
        
    def assign_role(self, agent_id: str, role_name: str) -> bool:
        """
        分配角色给 Agent
        
        Args:
            agent_id: Agent ID
            role_name: 角色名称
            
        Returns:
            是否成功
        """
        if role_name not in self._roles:
            return False
            
        if agent_id not in self._agent_roles:
            self._agent_roles[agent_id] = set()
            
        self._agent_roles[agent_id].add(role_name)
        return True
        
    def revoke_role(self, agent_id: str, role_name: str) -> bool:
        """
        撤销 Agent 的角色
        
        Args:
            agent_id: Agent ID
            role_name: 角色名称
            
        Returns:
            是否成功
        """
        if agent_id not in self._agent_roles:
            return False
            
        if role_name in self._agent_roles[agent_id]:
            self._agent_roles[agent_id].remove(role_name)
            return True
            
        return False
        
    def get_agent_roles(self, agent_id: str) -> List[str]:
        """获取 Agent 的角色"""
        return list(self._agent_roles.get(agent_id, set()))
        
    # ============== 权限授予 ==============
    
    def grant(
        self,
        grantee: str,
        permission: Permission,
        grantor: str = "",
    ) -> PermissionGrant:
        """
        授予权限
        
        Args:
            grantee: 被授予者
            permission: 权限
            grantor: 授予者
            
        Returns:
            权限授予
        """
        grant = PermissionGrant(
            permission=permission,
            grantee=grantee,
            grantor=grantor,
        )
        
        if grantee not in self._grants:
            self._grants[grantee] = []
            
        self._grants[grantee].append(grant)
        return grant
        
    def revoke(self, grantee: str, permission_name: str) -> bool:
        """
        撤销权限
        
        Args:
            grantee: 被授予者
            permission_name: 权限名称
            
        Returns:
            是否成功
        """
        if grantee not in self._grants:
            return False
            
        grants = self._grants[grantee]
        to_remove = [g for g in grants if g.permission.name == permission_name]
        
        for g in to_remove:
            grants.remove(g)
            
        return len(to_remove) > 0
        
    # ============== 权限检查 ==============
    
    def check(
        self,
        agent_id: str,
        resource: str,
        action: str,
        required_level: PermissionLevel = PermissionLevel.READ,
    ) -> bool:
        """
        检查权限
        
        Args:
            agent_id: Agent ID
            resource: 资源
            action: 动作
            required_level: 要求的级别
            
        Returns:
            是否允许
        """
        # 检查直接授予的权限
        for grant in self._grants.get(agent_id, []):
            permission = grant.permission
            if permission.matches(resource, action):
                if permission.level.value >= required_level.value:
                    return True
                    
        # 检查角色权限
        for role_name in self._agent_roles.get(agent_id, set()):
            for permission in self._roles.get(role_name, []):
                if permission.matches(resource, action):
                    if permission.level.value >= required_level.value:
                        return True
                        
        return False
        
    def get_permissions(self, agent_id: str) -> List[Permission]:
        """
        获取 Agent 的所有权限
        
        Args:
            agent_id: Agent ID
            
        Returns:
            权限列表
        """
        permissions = []
        
        # 直接授予的权限
        for grant in self._grants.get(agent_id, []):
            permissions.append(grant.permission)
            
        # 角色权限
        for role_name in self._agent_roles.get(agent_id, set()):
            permissions.extend(self._roles.get(role_name, []))
            
        return permissions
        
    def get_info(self) -> Dict[str, Any]:
        """获取信息"""
        return {
            "roles": list(self._roles.keys()),
            "agents_with_grants": list(self._grants.keys()),
            "agents_with_roles": list(self._agent_roles.keys()),
            "total_grants": sum(len(g) for g in self._grants.values()),
        }


# 预定义角色
def setup_default_roles(manager: PermissionManager) -> None:
    """设置默认角色"""
    
    # 只读角色
    manager.define_role("readonly", [
        Permission("read", PermissionLevel.READ, "*", ["read", "list", "get"]),
    ])
    
    # 编辑角色
    manager.define_role("editor", [
        Permission("read", PermissionLevel.READ, "*", ["read", "list", "get"]),
        Permission("write", PermissionLevel.WRITE, "*", ["write", "edit", "create"]),
    ])
    
    # 执行角色
    manager.define_role("executor", [
        Permission("read", PermissionLevel.READ, "*", ["read", "list", "get"]),
        Permission("execute", PermissionLevel.EXECUTE, "*", ["exec", "run"]),
    ])
    
    # 管理员角色
    manager.define_role("admin", [
        Permission("admin", PermissionLevel.ADMIN, "*", ["*"]),
    ])
