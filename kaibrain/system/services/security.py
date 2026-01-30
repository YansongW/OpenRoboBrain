"""
安全模块

提供权限控制、通信加密和审计追踪。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from kaibrain.system.services.logger import LoggerMixin


class Permission(Enum):
    """权限类型"""
    # 数据权限
    READ_EXPLICIT_DATA = "read_explicit_data"
    WRITE_EXPLICIT_DATA = "write_explicit_data"
    READ_IMPLICIT_DATA = "read_implicit_data"
    # 注意：没有 WRITE_IMPLICIT_DATA，隐性数据只能人工写入
    
    # Agent 权限
    REGISTER_AGENT = "register_agent"
    REMOVE_AGENT = "remove_agent"
    MODIFY_AGENT = "modify_agent"
    EXECUTE_AGENT = "execute_agent"
    
    # 系统权限
    MANAGE_SYSTEM = "manage_system"
    VIEW_LOGS = "view_logs"
    VIEW_METRICS = "view_metrics"


@dataclass
class Role:
    """角色"""
    name: str
    permissions: Set[Permission] = field(default_factory=set)
    description: str = ""


@dataclass
class AuditLog:
    """审计日志"""
    log_id: str
    actor: str
    action: str
    resource: str
    details: Dict[str, Any] = field(default_factory=dict)
    result: str = "success"
    timestamp: datetime = field(default_factory=datetime.now)


# 预定义角色
ROLE_SUPER_AGENT = Role(
    name="super_agent",
    permissions={
        Permission.READ_EXPLICIT_DATA,
        Permission.WRITE_EXPLICIT_DATA,
        Permission.READ_IMPLICIT_DATA,
        Permission.REGISTER_AGENT,
        Permission.REMOVE_AGENT,
        Permission.MODIFY_AGENT,
        Permission.EXECUTE_AGENT,
        Permission.VIEW_LOGS,
        Permission.VIEW_METRICS,
    },
    description="Super Agent 角色，最高Agent权限（但不能写入隐性数据）"
)

ROLE_ORCHESTRATOR = Role(
    name="orchestrator",
    permissions={
        Permission.READ_EXPLICIT_DATA,
        Permission.WRITE_EXPLICIT_DATA,
        Permission.READ_IMPLICIT_DATA,
        Permission.EXECUTE_AGENT,
        Permission.VIEW_LOGS,
    },
    description="编排Agent角色"
)

ROLE_ATOMIC_AGENT = Role(
    name="atomic_agent",
    permissions={
        Permission.READ_EXPLICIT_DATA,
        Permission.WRITE_EXPLICIT_DATA,
        Permission.READ_IMPLICIT_DATA,
    },
    description="子能力Agent角色"
)

ROLE_ADMIN = Role(
    name="admin",
    permissions=set(Permission),
    description="管理员角色，拥有所有权限"
)


class SecurityManager(LoggerMixin):
    """
    安全管理器
    
    管理权限控制和审计日志。
    """
    
    def __init__(self):
        self._roles: Dict[str, Role] = {
            "super_agent": ROLE_SUPER_AGENT,
            "orchestrator": ROLE_ORCHESTRATOR,
            "atomic_agent": ROLE_ATOMIC_AGENT,
            "admin": ROLE_ADMIN,
        }
        self._actor_roles: Dict[str, str] = {}
        self._audit_logs: List[AuditLog] = []
        
    def assign_role(self, actor_id: str, role_name: str) -> None:
        """分配角色"""
        if role_name not in self._roles:
            raise ValueError(f"角色不存在: {role_name}")
            
        self._actor_roles[actor_id] = role_name
        self.logger.info(f"角色分配: {actor_id} -> {role_name}")
        
    def check_permission(self, actor_id: str, permission: Permission) -> bool:
        """
        检查权限
        
        Args:
            actor_id: 操作者ID
            permission: 要检查的权限
            
        Returns:
            是否有权限
        """
        role_name = self._actor_roles.get(actor_id)
        if not role_name:
            return False
            
        role = self._roles.get(role_name)
        if not role:
            return False
            
        return permission in role.permissions
        
    def require_permission(self, actor_id: str, permission: Permission) -> None:
        """
        要求权限（没有则抛出异常）
        
        Args:
            actor_id: 操作者ID
            permission: 要求的权限
            
        Raises:
            PermissionError: 如果没有权限
        """
        if not self.check_permission(actor_id, permission):
            self.audit_log(
                actor=actor_id,
                action="permission_denied",
                resource=permission.value,
                result="denied",
            )
            raise PermissionError(f"权限不足: {actor_id} 没有 {permission.value} 权限")
            
    def audit_log(
        self,
        actor: str,
        action: str,
        resource: str,
        details: Optional[Dict[str, Any]] = None,
        result: str = "success",
    ) -> AuditLog:
        """
        记录审计日志
        
        Args:
            actor: 操作者
            action: 操作
            resource: 资源
            details: 详情
            result: 结果
            
        Returns:
            AuditLog 实例
        """
        log = AuditLog(
            log_id=f"audit_{len(self._audit_logs)}_{datetime.now().timestamp()}",
            actor=actor,
            action=action,
            resource=resource,
            details=details or {},
            result=result,
        )
        
        self._audit_logs.append(log)
        
        # 保留最近10000条
        if len(self._audit_logs) > 10000:
            self._audit_logs = self._audit_logs[-10000:]
            
        return log
        
    def get_audit_logs(
        self,
        actor: Optional[str] = None,
        action: Optional[str] = None,
        limit: int = 100,
    ) -> List[AuditLog]:
        """获取审计日志"""
        logs = self._audit_logs
        
        if actor:
            logs = [l for l in logs if l.actor == actor]
            
        if action:
            logs = [l for l in logs if l.action == action]
            
        return logs[-limit:]
