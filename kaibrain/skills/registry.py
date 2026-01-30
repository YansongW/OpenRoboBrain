"""
技能注册中心

管理所有技能的注册、查询和生命周期。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Type, TYPE_CHECKING

from kaibrain.skills.base import (
    BaseSkill,
    SkillCategory,
    SkillInfo,
    SkillLevel,
)
from kaibrain.system.services.logger import LoggerMixin

if TYPE_CHECKING:
    from kaibrain.middleware.cerebellum_pipeline.actions import ActionManager


@dataclass
class RegisteredSkill:
    """已注册的技能信息"""
    skill_class: Type[BaseSkill]
    info: SkillInfo
    registered_at: datetime = field(default_factory=datetime.now)
    instance_count: int = 0  # 创建的实例数量
    
    
class SkillRegistry(LoggerMixin):
    """
    技能注册中心
    
    负责管理所有技能的注册、查询、实例化。
    采用单例模式，确保全局唯一。
    """
    
    _instance: Optional[SkillRegistry] = None
    
    def __new__(cls, *args: Any, **kwargs: Any) -> SkillRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
        
    def __init__(self, action_manager: Optional[ActionManager] = None):
        """
        初始化技能注册中心
        
        Args:
            action_manager: 原子动作管理器
        """
        if self._initialized:
            return
            
        self._skills: Dict[str, RegisteredSkill] = {}
        self._skills_by_category: Dict[SkillCategory, List[str]] = {
            cat: [] for cat in SkillCategory
        }
        self._action_manager = action_manager
        self._initialized = True
        
        self.logger.info("技能注册中心初始化完成")
        
    def register(
        self,
        skill_class: Type[BaseSkill],
        name: Optional[str] = None,
    ) -> bool:
        """
        注册技能
        
        Args:
            skill_class: 技能类
            name: 技能名称（可选，默认使用类的name属性）
            
        Returns:
            是否注册成功
        """
        try:
            # 创建临时实例获取信息
            temp_instance = skill_class.__new__(skill_class)
            temp_instance._info = SkillInfo()
            
            # 调用 __init__ 但不传 action_manager
            skill_class.__init__(
                temp_instance,
                name=name or skill_class.__name__,
                name_cn="",
                category=SkillCategory.DAILY_LIFE,
                action_manager=None,
            )
            
            skill_name = name or temp_instance.name
            
            if skill_name in self._skills:
                self.logger.warning(f"技能 {skill_name} 已注册，将被覆盖")
                
            # 获取技能信息
            info = temp_instance.info
            
            self._skills[skill_name] = RegisteredSkill(
                skill_class=skill_class,
                info=info,
            )
            
            # 按分类索引
            category = info.category
            if skill_name not in self._skills_by_category[category]:
                self._skills_by_category[category].append(skill_name)
                
            self.logger.info(
                f"注册技能: {skill_name} ({info.name_cn}), "
                f"分类: {category.value}"
            )
            return True
            
        except Exception as e:
            self.logger.error(f"注册技能失败: {e}")
            return False
            
    def register_decorator(
        self,
        name: Optional[str] = None,
    ) -> Callable[[Type[BaseSkill]], Type[BaseSkill]]:
        """
        技能注册装饰器
        
        用法:
            @registry.register_decorator()
            class MySkill(BaseSkill):
                ...
                
        Args:
            name: 技能名称
            
        Returns:
            装饰器函数
        """
        def decorator(skill_class: Type[BaseSkill]) -> Type[BaseSkill]:
            self.register(skill_class, name)
            return skill_class
        return decorator
        
    def unregister(self, name: str) -> bool:
        """
        注销技能
        
        Args:
            name: 技能名称
            
        Returns:
            是否注销成功
        """
        if name not in self._skills:
            return False
            
        registered = self._skills.pop(name)
        category = registered.info.category
        
        if name in self._skills_by_category[category]:
            self._skills_by_category[category].remove(name)
            
        self.logger.info(f"注销技能: {name}")
        return True
        
    def get(self, name: str) -> Optional[Type[BaseSkill]]:
        """
        获取技能类
        
        Args:
            name: 技能名称
            
        Returns:
            技能类
        """
        registered = self._skills.get(name)
        return registered.skill_class if registered else None
        
    def get_info(self, name: str) -> Optional[SkillInfo]:
        """
        获取技能信息
        
        Args:
            name: 技能名称
            
        Returns:
            技能信息
        """
        registered = self._skills.get(name)
        return registered.info if registered else None
        
    def create_instance(
        self,
        name: str,
        action_manager: Optional[ActionManager] = None,
        **kwargs: Any,
    ) -> Optional[BaseSkill]:
        """
        创建技能实例
        
        Args:
            name: 技能名称
            action_manager: 原子动作管理器
            **kwargs: 传递给技能构造函数的参数
            
        Returns:
            技能实例
        """
        registered = self._skills.get(name)
        if not registered:
            self.logger.error(f"未找到技能: {name}")
            return None
            
        try:
            am = action_manager or self._action_manager
            instance = registered.skill_class(action_manager=am, **kwargs)
            registered.instance_count += 1
            
            self.logger.debug(f"创建技能实例: {name}")
            return instance
            
        except Exception as e:
            self.logger.error(f"创建技能实例失败: {name} - {e}")
            return None
            
    def list_skills(
        self,
        category: Optional[SkillCategory] = None,
        level: Optional[SkillLevel] = None,
    ) -> List[SkillInfo]:
        """
        列出技能
        
        Args:
            category: 按分类筛选
            level: 按等级筛选
            
        Returns:
            技能信息列表
        """
        skills = []
        
        for name, registered in self._skills.items():
            info = registered.info
            
            if category and info.category != category:
                continue
            if level and info.level != level:
                continue
                
            skills.append(info)
            
        return skills
        
    def list_by_category(self, category: SkillCategory) -> List[str]:
        """
        按分类列出技能名称
        
        Args:
            category: 技能分类
            
        Returns:
            技能名称列表
        """
        return self._skills_by_category.get(category, []).copy()
        
    def search(
        self,
        query: str,
        category: Optional[SkillCategory] = None,
    ) -> List[SkillInfo]:
        """
        搜索技能
        
        Args:
            query: 搜索关键词
            category: 按分类筛选
            
        Returns:
            匹配的技能信息列表
        """
        results = []
        query_lower = query.lower()
        
        for name, registered in self._skills.items():
            info = registered.info
            
            if category and info.category != category:
                continue
                
            # 在名称、中文名、描述中搜索
            if (
                query_lower in info.name.lower() or
                query_lower in info.name_cn or
                query_lower in info.description.lower()
            ):
                results.append(info)
                
        return results
        
    def get_required_actions(self, name: str) -> List[str]:
        """
        获取技能所需的原子动作
        
        Args:
            name: 技能名称
            
        Returns:
            原子动作列表
        """
        registered = self._skills.get(name)
        if registered:
            return registered.info.required_actions.copy()
        return []
        
    @property
    def skill_count(self) -> int:
        """已注册技能数量"""
        return len(self._skills)
        
    @property
    def categories(self) -> Dict[SkillCategory, int]:
        """各分类的技能数量"""
        return {
            cat: len(names)
            for cat, names in self._skills_by_category.items()
        }
        
    def clear(self) -> None:
        """清空所有注册的技能"""
        self._skills.clear()
        for cat in self._skills_by_category:
            self._skills_by_category[cat] = []
        self.logger.info("已清空所有技能注册")


# 全局技能注册中心实例
_global_registry: Optional[SkillRegistry] = None


def get_skill_registry() -> SkillRegistry:
    """获取全局技能注册中心"""
    global _global_registry
    if _global_registry is None:
        _global_registry = SkillRegistry()
    return _global_registry


def register_skill(
    name: Optional[str] = None,
) -> Callable[[Type[BaseSkill]], Type[BaseSkill]]:
    """
    技能注册装饰器（全局）
    
    用法:
        @register_skill()
        class CookingSkill(BaseSkill):
            ...
            
        @register_skill("my_cooking")
        class CookingSkill(BaseSkill):
            ...
    """
    return get_skill_registry().register_decorator(name)
