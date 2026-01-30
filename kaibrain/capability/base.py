"""
能力基类

定义能力接口的基础结构。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING
from uuid import uuid4

from kaibrain.system.services.logger import LoggerMixin

if TYPE_CHECKING:
    from kaibrain.agent.orchestrator.orchestrator import OrchestratorAgent


class CapabilityCategory(Enum):
    """能力分类"""
    MOTION = "motion"           # 运动能力
    PERCEPTION = "perception"   # 感知能力
    COGNITION = "cognition"     # 认知能力
    INTERACTION = "interaction" # 交互能力
    AUTONOMY = "autonomy"       # 自主能力


@dataclass
class CapabilityInfo:
    """能力信息"""
    capability_id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    category: CapabilityCategory = CapabilityCategory.COGNITION
    description: str = ""
    version: str = "1.0.0"
    
    # 输入输出schema
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    
    # 依赖的Agent类型
    required_agents: List[str] = field(default_factory=list)
    
    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CapabilityResult:
    """能力执行结果"""
    success: bool = True
    result: Any = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class Capability(ABC, LoggerMixin):
    """
    能力基类
    
    所有能力都需要继承此类。
    """
    
    def __init__(
        self,
        name: str,
        category: CapabilityCategory,
        description: str = "",
        orchestrator: Optional[OrchestratorAgent] = None,
    ):
        """
        初始化能力
        
        Args:
            name: 能力名称
            category: 能力分类
            description: 描述
            orchestrator: 编排Agent
        """
        self._info = CapabilityInfo(
            name=name,
            category=category,
            description=description,
        )
        self._orchestrator = orchestrator
        
    @property
    def info(self) -> CapabilityInfo:
        """能力信息"""
        return self._info
        
    @property
    def name(self) -> str:
        """能力名称"""
        return self._info.name
        
    async def execute(
        self,
        input_data: Dict[str, Any],
        parameters: Optional[Dict[str, Any]] = None,
    ) -> CapabilityResult:
        """
        执行能力
        
        Args:
            input_data: 输入数据
            parameters: 参数
            
        Returns:
            CapabilityResult
        """
        start_time = datetime.now()
        
        try:
            # 验证输入
            self._validate_input(input_data)
            
            # 执行
            result = await self._execute(input_data, parameters or {})
            
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            
            return CapabilityResult(
                success=True,
                result=result,
                execution_time_ms=execution_time,
            )
            
        except Exception as e:
            self.logger.error(f"能力执行失败: {self.name} - {e}")
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            
            return CapabilityResult(
                success=False,
                error=str(e),
                execution_time_ms=execution_time,
            )
            
    def _validate_input(self, input_data: Dict[str, Any]) -> None:
        """验证输入数据"""
        # 基础验证，子类可以重写
        pass
        
    @abstractmethod
    async def _execute(
        self,
        input_data: Dict[str, Any],
        parameters: Dict[str, Any],
    ) -> Any:
        """
        执行能力（子类实现）
        
        Args:
            input_data: 输入数据
            parameters: 参数
            
        Returns:
            执行结果
        """
        pass


class CapabilityRegistry(LoggerMixin):
    """
    能力注册表
    
    管理所有能力的注册和查找。
    """
    
    def __init__(self):
        self._capabilities: Dict[str, Capability] = {}
        self._by_category: Dict[CapabilityCategory, List[str]] = {
            cat: [] for cat in CapabilityCategory
        }
        
    def register(self, capability: Capability) -> None:
        """注册能力"""
        cap_id = capability.info.capability_id
        
        if cap_id in self._capabilities:
            raise ValueError(f"能力已存在: {cap_id}")
            
        self._capabilities[cap_id] = capability
        self._by_category[capability.info.category].append(cap_id)
        
        self.logger.info(f"注册能力: {capability.name}")
        
    def unregister(self, capability_id: str) -> None:
        """注销能力"""
        if capability_id not in self._capabilities:
            return
            
        capability = self._capabilities.pop(capability_id)
        self._by_category[capability.info.category].remove(capability_id)
        
        self.logger.info(f"注销能力: {capability.name}")
        
    def get(self, capability_id: str) -> Optional[Capability]:
        """获取能力"""
        return self._capabilities.get(capability_id)
        
    def get_by_name(self, name: str) -> Optional[Capability]:
        """按名称获取能力"""
        for cap in self._capabilities.values():
            if cap.name == name:
                return cap
        return None
        
    def get_by_category(self, category: CapabilityCategory) -> List[Capability]:
        """按分类获取能力"""
        cap_ids = self._by_category.get(category, [])
        return [self._capabilities[cid] for cid in cap_ids]
        
    def list_all(self) -> List[CapabilityInfo]:
        """列出所有能力"""
        return [cap.info for cap in self._capabilities.values()]
