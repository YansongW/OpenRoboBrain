"""
Hook Manager

生命周期钩子管理器，支持：
- 内部钩子 (Internal Hooks)
- 插件钩子 (Plugin Hooks)

借鉴 Moltbot 的 Hook 系统设计。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

from orb.system.services.logger import LoggerMixin


class HookType(Enum):
    """钩子类型"""
    # Agent 生命周期
    BEFORE_AGENT_START = "before_agent_start"
    AFTER_AGENT_START = "after_agent_start"
    BEFORE_AGENT_STOP = "before_agent_stop"
    AFTER_AGENT_STOP = "after_agent_stop"
    AGENT_ERROR = "agent_error"
    
    # Agent 运行时
    BEFORE_RUN = "before_run"
    AFTER_RUN = "after_run"
    ON_INTAKE = "on_intake"
    
    # 推理
    BEFORE_INFERENCE = "before_inference"
    AFTER_INFERENCE = "after_inference"
    
    # 工具
    BEFORE_TOOL_CALL = "before_tool_call"
    AFTER_TOOL_CALL = "after_tool_call"
    TOOL_ERROR = "tool_error"
    
    # 消息
    MESSAGE_RECEIVED = "message_received"
    MESSAGE_SENDING = "message_sending"
    MESSAGE_SENT = "message_sent"
    
    # 会话
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    
    # 压缩
    BEFORE_COMPACTION = "before_compaction"
    AFTER_COMPACTION = "after_compaction"
    
    # 系统
    GATEWAY_START = "gateway_start"
    GATEWAY_STOP = "gateway_stop"
    AGENT_BOOTSTRAP = "agent_bootstrap"


@dataclass
class HookContext:
    """钩子上下文"""
    hook_type: HookType
    agent_id: str = ""
    session_id: str = ""
    run_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 控制流
    cancelled: bool = False
    modified_data: Optional[Dict[str, Any]] = None
    
    def cancel(self) -> None:
        """取消后续处理"""
        self.cancelled = True
        
    def modify(self, key: str, value: Any) -> None:
        """修改数据"""
        if self.modified_data is None:
            self.modified_data = {}
        self.modified_data[key] = value


# 类型定义
HookCallback = Callable[[HookContext], Any]


@dataclass
class HookRegistration:
    """钩子注册信息"""
    callback: HookCallback
    hook_type: HookType
    name: str = ""
    priority: int = 0  # 越小越先执行
    is_async: bool = False
    enabled: bool = True
    agent_filter: Optional[str] = None  # 只对特定 Agent 生效
    metadata: Dict[str, Any] = field(default_factory=dict)


class HookManager(LoggerMixin):
    """
    钩子管理器
    
    管理所有生命周期钩子的注册和执行。
    """
    
    def __init__(self):
        """初始化钩子管理器"""
        self._hooks: Dict[HookType, List[HookRegistration]] = {
            hook_type: [] for hook_type in HookType
        }
        self._global_hooks: List[HookRegistration] = []
        
    def register(
        self,
        hook_type: HookType,
        callback: HookCallback,
        name: str = "",
        priority: int = 0,
        agent_filter: Optional[str] = None,
    ) -> HookRegistration:
        """
        注册钩子
        
        Args:
            hook_type: 钩子类型
            callback: 回调函数
            name: 名称
            priority: 优先级
            agent_filter: Agent 过滤
            
        Returns:
            注册信息
        """
        is_async = asyncio.iscoroutinefunction(callback)
        
        registration = HookRegistration(
            callback=callback,
            hook_type=hook_type,
            name=name or callback.__name__,
            priority=priority,
            is_async=is_async,
            agent_filter=agent_filter,
        )
        
        self._hooks[hook_type].append(registration)
        
        # 按优先级排序
        self._hooks[hook_type].sort(key=lambda r: r.priority)
        
        self.logger.debug(f"注册钩子: {hook_type.value} -> {registration.name}")
        return registration
        
    def register_decorator(
        self,
        hook_type: HookType,
        name: str = "",
        priority: int = 0,
        agent_filter: Optional[str] = None,
    ) -> Callable[[HookCallback], HookCallback]:
        """
        装饰器方式注册钩子
        
        Args:
            hook_type: 钩子类型
            name: 名称
            priority: 优先级
            agent_filter: Agent 过滤
            
        Returns:
            装饰器
        """
        def decorator(callback: HookCallback) -> HookCallback:
            self.register(
                hook_type=hook_type,
                callback=callback,
                name=name,
                priority=priority,
                agent_filter=agent_filter,
            )
            return callback
        return decorator
        
    def register_global(
        self,
        callback: HookCallback,
        name: str = "",
        priority: int = 0,
    ) -> HookRegistration:
        """
        注册全局钩子（对所有钩子类型生效）
        
        Args:
            callback: 回调函数
            name: 名称
            priority: 优先级
            
        Returns:
            注册信息
        """
        is_async = asyncio.iscoroutinefunction(callback)
        
        registration = HookRegistration(
            callback=callback,
            hook_type=HookType.BEFORE_RUN,  # 占位
            name=name or callback.__name__,
            priority=priority,
            is_async=is_async,
        )
        
        self._global_hooks.append(registration)
        self._global_hooks.sort(key=lambda r: r.priority)
        
        return registration
        
    def unregister(self, registration: HookRegistration) -> bool:
        """
        注销钩子
        
        Args:
            registration: 注册信息
            
        Returns:
            是否成功
        """
        hook_type = registration.hook_type
        
        if registration in self._hooks[hook_type]:
            self._hooks[hook_type].remove(registration)
            return True
            
        if registration in self._global_hooks:
            self._global_hooks.remove(registration)
            return True
            
        return False
        
    def unregister_by_name(
        self,
        name: str,
        hook_type: Optional[HookType] = None,
    ) -> int:
        """
        按名称注销钩子
        
        Args:
            name: 名称
            hook_type: 钩子类型（如果为空则检查所有类型）
            
        Returns:
            注销的数量
        """
        count = 0
        
        if hook_type:
            hooks = self._hooks[hook_type]
            to_remove = [h for h in hooks if h.name == name]
            for h in to_remove:
                hooks.remove(h)
                count += 1
        else:
            for hooks in self._hooks.values():
                to_remove = [h for h in hooks if h.name == name]
                for h in to_remove:
                    hooks.remove(h)
                    count += 1
                    
            to_remove = [h for h in self._global_hooks if h.name == name]
            for h in to_remove:
                self._global_hooks.remove(h)
                count += 1
                
        return count
        
    async def emit(
        self,
        hook_type: HookType,
        agent_id: str = "",
        session_id: str = "",
        run_id: str = "",
        data: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> HookContext:
        """
        触发钩子
        
        Args:
            hook_type: 钩子类型
            agent_id: Agent ID
            session_id: 会话 ID
            run_id: 运行 ID
            data: 数据
            metadata: 元数据
            
        Returns:
            钩子上下文
        """
        context = HookContext(
            hook_type=hook_type,
            agent_id=agent_id,
            session_id=session_id,
            run_id=run_id,
            data=data or {},
            metadata=metadata or {},
        )
        
        # 获取要执行的钩子
        hooks = self._hooks.get(hook_type, [])
        all_hooks = self._global_hooks + hooks
        
        # 按优先级排序
        all_hooks.sort(key=lambda h: h.priority)
        
        # 执行钩子
        for registration in all_hooks:
            if not registration.enabled:
                continue
                
            # 检查 Agent 过滤
            if registration.agent_filter and registration.agent_filter != agent_id:
                continue
                
            try:
                if registration.is_async:
                    await registration.callback(context)
                else:
                    registration.callback(context)
                    
                # 检查是否取消
                if context.cancelled:
                    self.logger.debug(f"钩子链被取消: {hook_type.value}")
                    break
                    
            except Exception as e:
                self.logger.warning(f"钩子执行失败 {registration.name}: {e}")
                
        return context
        
    def emit_sync(
        self,
        hook_type: HookType,
        agent_id: str = "",
        session_id: str = "",
        run_id: str = "",
        data: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> HookContext:
        """
        同步触发钩子（只执行同步钩子）
        
        Args:
            hook_type: 钩子类型
            agent_id: Agent ID
            session_id: 会话 ID
            run_id: 运行 ID
            data: 数据
            metadata: 元数据
            
        Returns:
            钩子上下文
        """
        context = HookContext(
            hook_type=hook_type,
            agent_id=agent_id,
            session_id=session_id,
            run_id=run_id,
            data=data or {},
            metadata=metadata or {},
        )
        
        hooks = self._hooks.get(hook_type, [])
        all_hooks = self._global_hooks + hooks
        all_hooks.sort(key=lambda h: h.priority)
        
        for registration in all_hooks:
            if not registration.enabled or registration.is_async:
                continue
                
            if registration.agent_filter and registration.agent_filter != agent_id:
                continue
                
            try:
                registration.callback(context)
                
                if context.cancelled:
                    break
                    
            except Exception as e:
                self.logger.warning(f"钩子执行失败 {registration.name}: {e}")
                
        return context
        
    def list_hooks(
        self,
        hook_type: Optional[HookType] = None,
    ) -> List[HookRegistration]:
        """
        列出钩子
        
        Args:
            hook_type: 钩子类型（如果为空则列出所有）
            
        Returns:
            钩子列表
        """
        if hook_type:
            return self._hooks.get(hook_type, []).copy()
            
        all_hooks = []
        for hooks in self._hooks.values():
            all_hooks.extend(hooks)
        return all_hooks
        
    def clear(self, hook_type: Optional[HookType] = None) -> None:
        """
        清空钩子
        
        Args:
            hook_type: 钩子类型（如果为空则清空所有）
        """
        if hook_type:
            self._hooks[hook_type].clear()
        else:
            for hooks in self._hooks.values():
                hooks.clear()
            self._global_hooks.clear()
            
    def enable(self, registration: HookRegistration) -> None:
        """启用钩子"""
        registration.enabled = True
        
    def disable(self, registration: HookRegistration) -> None:
        """禁用钩子"""
        registration.enabled = False
        
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total": sum(len(hooks) for hooks in self._hooks.values()) + len(self._global_hooks),
            "by_type": {
                hook_type.value: len(hooks)
                for hook_type, hooks in self._hooks.items()
            },
            "global": len(self._global_hooks),
        }


# 全局钩子管理器
_global_hook_manager: Optional[HookManager] = None


def get_hook_manager() -> HookManager:
    """获取全局钩子管理器"""
    global _global_hook_manager
    if _global_hook_manager is None:
        _global_hook_manager = HookManager()
    return _global_hook_manager


def hook(
    hook_type: HookType,
    name: str = "",
    priority: int = 0,
    agent_filter: Optional[str] = None,
) -> Callable[[HookCallback], HookCallback]:
    """
    便捷装饰器，注册到全局钩子管理器
    
    Args:
        hook_type: 钩子类型
        name: 名称
        priority: 优先级
        agent_filter: Agent 过滤
        
    Returns:
        装饰器
    """
    return get_hook_manager().register_decorator(
        hook_type=hook_type,
        name=name,
        priority=priority,
        agent_filter=agent_filter,
    )
