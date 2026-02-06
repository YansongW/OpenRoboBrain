"""
行为注册表

管理所有可用行为的注册、查询和匹配。
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, TYPE_CHECKING

from orb.behavior.base import Behavior, BehaviorConfig
from orb.system.services.logger import LoggerMixin

if TYPE_CHECKING:
    from orb.data.explicit.workflow_memory import WorkflowMemory


BehaviorFactory = Callable[[], Behavior]


class BehaviorRegistry(LoggerMixin):
    """
    行为注册表
    
    管理所有可用行为的注册、查询和匹配。
    支持按名称、标签、能力等方式查询行为。
    """
    
    def __init__(self):
        """初始化注册表"""
        self._behaviors: Dict[str, Behavior] = {}
        self._factories: Dict[str, BehaviorFactory] = {}
        self._workflow_memory: Optional[WorkflowMemory] = None
    
    def set_workflow_memory(self, memory: WorkflowMemory) -> None:
        """
        设置工作流记忆
        
        Args:
            memory: 工作流记忆实例
        """
        self._workflow_memory = memory
        
        # 更新已注册行为的工作流记忆
        for behavior in self._behaviors.values():
            behavior.set_workflow_memory(memory)
    
    def register(self, behavior: Behavior) -> None:
        """
        注册行为
        
        Args:
            behavior: 行为实例
        """
        name = behavior.name
        
        if name in self._behaviors:
            self.logger.warning(f"行为 '{name}' 已存在，将被覆盖")
        
        # 设置工作流记忆
        if self._workflow_memory:
            behavior.set_workflow_memory(self._workflow_memory)
        
        self._behaviors[name] = behavior
        self.logger.debug(f"注册行为: {name}")
    
    def register_factory(
        self,
        name: str,
        factory: BehaviorFactory,
    ) -> None:
        """
        注册行为工厂（延迟创建）
        
        Args:
            name: 行为名称
            factory: 工厂函数
        """
        self._factories[name] = factory
        self.logger.debug(f"注册行为工厂: {name}")
    
    def unregister(self, name: str) -> bool:
        """
        注销行为
        
        Args:
            name: 行为名称
            
        Returns:
            是否成功
        """
        if name in self._behaviors:
            del self._behaviors[name]
            return True
        if name in self._factories:
            del self._factories[name]
            return True
        return False
    
    def get(self, name: str) -> Optional[Behavior]:
        """
        获取行为
        
        Args:
            name: 行为名称
            
        Returns:
            行为实例
        """
        # 先检查已实例化的行为
        if name in self._behaviors:
            return self._behaviors[name]
        
        # 检查工厂
        if name in self._factories:
            behavior = self._factories[name]()
            if self._workflow_memory:
                behavior.set_workflow_memory(self._workflow_memory)
            self._behaviors[name] = behavior
            return behavior
        
        return None
    
    def list(
        self,
        tags: Optional[List[str]] = None,
        capabilities: Optional[List[str]] = None,
    ) -> List[Behavior]:
        """
        列出行为
        
        Args:
            tags: 过滤标签
            capabilities: 过滤能力
            
        Returns:
            行为列表
        """
        # 实例化所有工厂
        for name, factory in list(self._factories.items()):
            if name not in self._behaviors:
                behavior = factory()
                if self._workflow_memory:
                    behavior.set_workflow_memory(self._workflow_memory)
                self._behaviors[name] = behavior
        
        behaviors = list(self._behaviors.values())
        
        # 按标签过滤
        if tags:
            tags_set = set(tags)
            behaviors = [
                b for b in behaviors
                if tags_set.intersection(set(b.config.tags))
            ]
        
        # 按能力过滤
        if capabilities:
            caps_set = set(capabilities)
            behaviors = [
                b for b in behaviors
                if caps_set.issubset(set(b.required_capabilities))
            ]
        
        return behaviors
    
    def match(
        self,
        user_input: str,
        threshold: float = 0.5,
    ) -> List[tuple[Behavior, float]]:
        """
        匹配适合处理输入的行为
        
        Args:
            user_input: 用户输入
            threshold: 置信度阈值
            
        Returns:
            (行为, 置信度) 列表，按置信度降序排列
        """
        matches = []
        
        for behavior in self.list():
            confidence = behavior.can_handle(user_input)
            if confidence >= threshold:
                matches.append((behavior, confidence))
        
        # 按置信度降序排列
        matches.sort(key=lambda x: x[1], reverse=True)
        
        return matches
    
    def get_best_match(
        self,
        user_input: str,
        threshold: float = 0.5,
    ) -> Optional[Behavior]:
        """
        获取最佳匹配的行为
        
        Args:
            user_input: 用户输入
            threshold: 置信度阈值
            
        Returns:
            最佳匹配的行为
        """
        matches = self.match(user_input, threshold)
        return matches[0][0] if matches else None
    
    @property
    def count(self) -> int:
        """已注册行为数量"""
        return len(self._behaviors) + len(self._factories)
    
    def to_dict(self) -> Dict[str, Dict]:
        """转换为字典"""
        return {
            name: behavior.to_dict()
            for name, behavior in self._behaviors.items()
        }


# ============== 全局注册表 ==============

_global_registry: Optional[BehaviorRegistry] = None


def get_registry(
    auto_register_builtin: bool = True,
) -> BehaviorRegistry:
    """
    获取全局行为注册表
    
    Args:
        auto_register_builtin: 是否自动注册内置行为
        
    Returns:
        BehaviorRegistry实例
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = BehaviorRegistry()
        
        # 自动注册内置行为
        if auto_register_builtin:
            _register_builtin_behaviors(_global_registry)
    
    return _global_registry


def _register_builtin_behaviors(registry: BehaviorRegistry) -> None:
    """注册内置行为"""
    from orb.behavior.builtin.general import GeneralBehavior
    
    # GeneralBehavior作为默认兜底行为
    registry.register(GeneralBehavior())


def register_behavior(behavior: Behavior) -> None:
    """注册行为到全局注册表"""
    get_registry().register(behavior)


def get_behavior(name: str) -> Optional[Behavior]:
    """从全局注册表获取行为"""
    return get_registry().get(name)
