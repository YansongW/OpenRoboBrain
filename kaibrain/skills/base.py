"""
技能基类

定义所有技能的通用接口和基础功能。
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from uuid import uuid4

from kaibrain.system.services.logger import LoggerMixin

if TYPE_CHECKING:
    from kaibrain.middleware.cerebellum_pipeline.actions import ActionManager


class SkillLevel(Enum):
    """技能熟练度等级"""
    NOVICE = "novice"               # 新手 - 刚开始学习
    BEGINNER = "beginner"           # 初学者 - 掌握基础
    INTERMEDIATE = "intermediate"   # 中级 - 能独立完成
    ADVANCED = "advanced"           # 高级 - 熟练运用
    EXPERT = "expert"               # 专家 - 精通并能创新


class SkillCategory(Enum):
    """技能分类"""
    DAILY_LIFE = "daily_life"   # 日常生活技能
    MOVEMENT = "movement"       # 运动技能
    COGNITIVE = "cognitive"     # 认知技能
    SOCIAL = "social"           # 社交技能
    CREATIVE = "creative"       # 创造性技能
    PROFESSIONAL = "professional"  # 专业技能


class SkillState(Enum):
    """技能执行状态"""
    IDLE = "idle"               # 空闲
    PREPARING = "preparing"     # 准备中
    EXECUTING = "executing"     # 执行中
    PAUSED = "paused"           # 暂停
    COMPLETED = "completed"     # 完成
    FAILED = "failed"           # 失败
    CANCELLED = "cancelled"     # 取消


@dataclass
class SkillInfo:
    """技能信息"""
    skill_id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    name_cn: str = ""  # 中文名称
    category: SkillCategory = SkillCategory.DAILY_LIFE
    level: SkillLevel = SkillLevel.NOVICE
    description: str = ""
    version: str = "1.0.0"
    required_actions: List[str] = field(default_factory=list)  # 需要的原子动作
    prerequisites: List[str] = field(default_factory=list)  # 前置技能
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillContext:
    """技能执行上下文"""
    execution_id: str = field(default_factory=lambda: str(uuid4()))
    parameters: Dict[str, Any] = field(default_factory=dict)
    environment: Dict[str, Any] = field(default_factory=dict)  # 环境信息
    constraints: Dict[str, Any] = field(default_factory=dict)  # 约束条件
    started_at: datetime = field(default_factory=datetime.now)
    timeout: Optional[float] = None  # 超时时间（秒）


@dataclass
class SkillResult:
    """技能执行结果"""
    success: bool = False
    state: SkillState = SkillState.COMPLETED
    result_data: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: datetime = field(default_factory=datetime.now)
    actions_executed: List[str] = field(default_factory=list)  # 已执行的原子动作
    
    @property
    def duration(self) -> Optional[float]:
        """执行时长（秒）"""
        if self.started_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None


class BaseSkill(ABC, LoggerMixin):
    """
    技能基类
    
    所有技能都需要继承此类。技能是高层次的语义化能力，
    通过组合多个原子动作来完成复杂任务。
    """
    
    def __init__(
        self,
        name: str,
        name_cn: str,
        category: SkillCategory,
        description: str = "",
        action_manager: Optional[ActionManager] = None,
    ):
        """
        初始化技能
        
        Args:
            name: 技能名称（英文）
            name_cn: 技能名称（中文）
            category: 技能分类
            description: 技能描述
            action_manager: 原子动作管理器
        """
        self._info = SkillInfo(
            name=name,
            name_cn=name_cn,
            category=category,
            description=description,
            required_actions=self.get_required_actions(),
        )
        self._action_manager = action_manager
        self._state = SkillState.IDLE
        self._current_context: Optional[SkillContext] = None
        
    @property
    def skill_id(self) -> str:
        """技能ID"""
        return self._info.skill_id
        
    @property
    def name(self) -> str:
        """技能名称"""
        return self._info.name
        
    @property
    def name_cn(self) -> str:
        """技能中文名称"""
        return self._info.name_cn
        
    @property
    def category(self) -> SkillCategory:
        """技能分类"""
        return self._info.category
        
    @property
    def level(self) -> SkillLevel:
        """技能等级"""
        return self._info.level
        
    @property
    def state(self) -> SkillState:
        """当前状态"""
        return self._state
        
    @property
    def info(self) -> SkillInfo:
        """技能信息"""
        return self._info
        
    def set_level(self, level: SkillLevel) -> None:
        """设置技能等级"""
        self._info.level = level
        self.logger.info(f"技能 {self.name_cn} 等级更新为: {level.value}")
        
    async def run(
        self,
        context: Optional[SkillContext] = None,
        **kwargs: Any,
    ) -> SkillResult:
        """
        运行技能
        
        Args:
            context: 执行上下文
            **kwargs: 额外参数（会合并到context.parameters中）
            
        Returns:
            执行结果
        """
        # 准备上下文
        if context is None:
            context = SkillContext(parameters=kwargs)
        elif kwargs:
            context.parameters.update(kwargs)
            
        self._current_context = context
        self._state = SkillState.PREPARING
        
        self.logger.info(f"开始执行技能: {self.name_cn}")
        
        try:
            # 前置检查
            if not await self._pre_check(context):
                return SkillResult(
                    success=False,
                    state=SkillState.FAILED,
                    error_message="前置检查失败",
                    started_at=context.started_at,
                )
                
            # 执行技能
            self._state = SkillState.EXECUTING
            result = await self.execute(context)
            
            self._state = result.state
            self.logger.info(
                f"技能 {self.name_cn} 执行完成, "
                f"成功: {result.success}, 耗时: {result.duration:.2f}秒"
            )
            
            return result
            
        except asyncio.CancelledError:
            self._state = SkillState.CANCELLED
            return SkillResult(
                success=False,
                state=SkillState.CANCELLED,
                error_message="技能被取消",
                started_at=context.started_at,
            )
            
        except Exception as e:
            self._state = SkillState.FAILED
            self.logger.error(f"技能 {self.name_cn} 执行失败: {e}")
            return SkillResult(
                success=False,
                state=SkillState.FAILED,
                error_message=str(e),
                started_at=context.started_at,
            )
            
        finally:
            self._current_context = None
            
    async def pause(self) -> bool:
        """暂停技能执行"""
        if self._state == SkillState.EXECUTING:
            self._state = SkillState.PAUSED
            await self._on_pause()
            self.logger.info(f"技能 {self.name_cn} 已暂停")
            return True
        return False
        
    async def resume(self) -> bool:
        """恢复技能执行"""
        if self._state == SkillState.PAUSED:
            self._state = SkillState.EXECUTING
            await self._on_resume()
            self.logger.info(f"技能 {self.name_cn} 已恢复")
            return True
        return False
        
    async def cancel(self) -> bool:
        """取消技能执行"""
        if self._state in [SkillState.EXECUTING, SkillState.PAUSED]:
            self._state = SkillState.CANCELLED
            await self._on_cancel()
            self.logger.info(f"技能 {self.name_cn} 已取消")
            return True
        return False
        
    # ============== 子类需要实现的方法 ==============
    
    @abstractmethod
    async def execute(self, context: SkillContext) -> SkillResult:
        """
        执行技能（核心逻辑）
        
        子类必须实现此方法。
        
        Args:
            context: 执行上下文
            
        Returns:
            执行结果
        """
        pass
        
    @abstractmethod
    def get_required_actions(self) -> List[str]:
        """
        获取此技能需要的原子动作列表
        
        子类必须实现此方法，返回执行该技能所需的原子动作ID列表。
        
        Returns:
            原子动作ID列表
        """
        pass
        
    def get_description(self) -> str:
        """
        获取技能描述
        
        子类可重写此方法提供详细描述。
        
        Returns:
            技能描述
        """
        return self._info.description
        
    async def _pre_check(self, context: SkillContext) -> bool:
        """
        前置检查（子类可重写）
        
        在执行技能前进行检查，如检查环境条件、资源可用性等。
        
        Args:
            context: 执行上下文
            
        Returns:
            是否通过检查
        """
        return True
        
    async def _on_pause(self) -> None:
        """暂停回调（子类可重写）"""
        pass
        
    async def _on_resume(self) -> None:
        """恢复回调（子类可重写）"""
        pass
        
    async def _on_cancel(self) -> None:
        """取消回调（子类可重写）"""
        pass
