"""
行为执行器

负责行为的调度和执行，关联工作流记忆实现经验复用。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from kaibrain.behavior.base import (
    Behavior,
    BehaviorContext,
    BehaviorResult,
    BehaviorStatus,
)
from kaibrain.behavior.registry import BehaviorRegistry, get_registry
from kaibrain.system.services.logger import LoggerMixin

if TYPE_CHECKING:
    from kaibrain.data.explicit.workflow_memory import WorkflowMemory


@dataclass
class ExecutorConfig:
    """执行器配置"""
    default_timeout: float = 300.0
    max_concurrent_behaviors: int = 5
    enable_workflow_memory: bool = True
    auto_match_threshold: float = 0.5


@dataclass
class ExecutorStats:
    """执行器统计"""
    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    workflow_matches: int = 0
    total_duration_ms: float = 0.0
    
    @property
    def success_rate(self) -> float:
        if self.total_executions == 0:
            return 0.0
        return self.successful_executions / self.total_executions
    
    @property
    def average_duration_ms(self) -> float:
        if self.total_executions == 0:
            return 0.0
        return self.total_duration_ms / self.total_executions
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_executions": self.total_executions,
            "successful_executions": self.successful_executions,
            "failed_executions": self.failed_executions,
            "workflow_matches": self.workflow_matches,
            "success_rate": self.success_rate,
            "average_duration_ms": self.average_duration_ms,
        }


class BehaviorExecutor(LoggerMixin):
    """
    行为执行器
    
    负责行为的调度和执行：
    1. 根据输入自动匹配行为
    2. 关联工作流记忆实现经验复用
    3. 管理并发执行
    4. 收集执行统计
    """
    
    def __init__(
        self,
        registry: Optional[BehaviorRegistry] = None,
        workflow_memory: Optional[WorkflowMemory] = None,
        config: Optional[ExecutorConfig] = None,
    ):
        """
        初始化执行器
        
        Args:
            registry: 行为注册表
            workflow_memory: 工作流记忆
            config: 配置
        """
        self._registry = registry or get_registry()
        self._workflow_memory = workflow_memory
        self._config = config or ExecutorConfig()
        self._stats = ExecutorStats()
        
        # 并发控制
        self._semaphore = asyncio.Semaphore(self._config.max_concurrent_behaviors)
        self._running_behaviors: Dict[str, BehaviorContext] = {}
        
        # 设置工作流记忆
        if workflow_memory:
            self._registry.set_workflow_memory(workflow_memory)
    
    @property
    def registry(self) -> BehaviorRegistry:
        """行为注册表"""
        return self._registry
    
    @property
    def stats(self) -> ExecutorStats:
        """执行统计"""
        return self._stats
    
    async def execute(
        self,
        behavior_name: str,
        user_input: str,
        parameters: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> BehaviorResult:
        """
        执行指定行为
        
        Args:
            behavior_name: 行为名称
            user_input: 用户输入
            parameters: 参数
            timeout: 超时时间
            
        Returns:
            执行结果
        """
        behavior = self._registry.get(behavior_name)
        
        if not behavior:
            return BehaviorResult(
                behavior_id="",
                behavior_name=behavior_name,
                status=BehaviorStatus.FAILED,
                error=f"行为不存在: {behavior_name}",
            )
        
        return await self._execute_behavior(
            behavior,
            user_input,
            parameters,
            timeout,
        )
    
    async def auto_execute(
        self,
        user_input: str,
        parameters: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> BehaviorResult:
        """
        自动匹配并执行行为
        
        Args:
            user_input: 用户输入
            parameters: 参数
            timeout: 超时时间
            
        Returns:
            执行结果
        """
        # 自动匹配行为
        behavior = self._registry.get_best_match(
            user_input,
            threshold=self._config.auto_match_threshold,
        )
        
        if not behavior:
            return BehaviorResult(
                behavior_id="",
                behavior_name="",
                status=BehaviorStatus.FAILED,
                error="没有找到匹配的行为",
            )
        
        self.logger.info(f"自动匹配到行为: {behavior.name}")
        
        return await self._execute_behavior(
            behavior,
            user_input,
            parameters,
            timeout,
        )
    
    async def _execute_behavior(
        self,
        behavior: Behavior,
        user_input: str,
        parameters: Optional[Dict[str, Any]],
        timeout: Optional[float],
    ) -> BehaviorResult:
        """执行行为"""
        actual_timeout = timeout or self._config.default_timeout
        
        # 并发控制
        async with self._semaphore:
            # 创建上下文
            context = BehaviorContext(
                user_input=user_input,
                parameters=parameters or {},
            )
            
            self._running_behaviors[context.behavior_id] = context
            
            try:
                # 执行（带超时）
                result = await asyncio.wait_for(
                    behavior.run(user_input, parameters, context),
                    timeout=actual_timeout,
                )
                
                # 更新统计
                self._update_stats(result)
                
                return result
                
            except asyncio.TimeoutError:
                result = BehaviorResult(
                    behavior_id=context.behavior_id,
                    behavior_name=behavior.name,
                    status=BehaviorStatus.FAILED,
                    error=f"执行超时 ({actual_timeout}s)",
                    started_at=context.started_at,
                )
                self._stats.total_executions += 1
                self._stats.failed_executions += 1
                return result
                
            finally:
                del self._running_behaviors[context.behavior_id]
    
    def _update_stats(self, result: BehaviorResult) -> None:
        """更新统计"""
        self._stats.total_executions += 1
        self._stats.total_duration_ms += result.duration_ms
        
        if result.status == BehaviorStatus.COMPLETED:
            self._stats.successful_executions += 1
        else:
            self._stats.failed_executions += 1
        
        if result.workflow_matched:
            self._stats.workflow_matches += 1
    
    async def execute_batch(
        self,
        requests: List[Dict[str, Any]],
        parallel: bool = True,
    ) -> List[BehaviorResult]:
        """
        批量执行行为
        
        Args:
            requests: 请求列表 [{"behavior": "name", "input": "...", "params": {...}}]
            parallel: 是否并行执行
            
        Returns:
            结果列表
        """
        if parallel:
            tasks = [
                self.execute(
                    req.get("behavior", ""),
                    req.get("input", ""),
                    req.get("params"),
                )
                for req in requests
            ]
            return await asyncio.gather(*tasks)
        else:
            results = []
            for req in requests:
                result = await self.execute(
                    req.get("behavior", ""),
                    req.get("input", ""),
                    req.get("params"),
                )
                results.append(result)
            return results
    
    def get_running_behaviors(self) -> List[Dict[str, Any]]:
        """获取正在运行的行为"""
        return [
            {
                "behavior_id": ctx.behavior_id,
                "user_input": ctx.user_input[:100],
                "started_at": ctx.started_at,
            }
            for ctx in self._running_behaviors.values()
        ]
    
    def get_stats_dict(self) -> Dict[str, Any]:
        """获取统计字典"""
        return {
            **self._stats.to_dict(),
            "running_behaviors": len(self._running_behaviors),
            "registered_behaviors": self._registry.count,
        }


# ============== 便捷函数 ==============

def create_behavior_executor(
    workflow_memory: Optional[WorkflowMemory] = None,
    max_concurrent: int = 5,
    auto_match_threshold: float = 0.5,
) -> BehaviorExecutor:
    """
    创建行为执行器
    
    Args:
        workflow_memory: 工作流记忆
        max_concurrent: 最大并发数
        auto_match_threshold: 自动匹配阈值
        
    Returns:
        BehaviorExecutor 实例
    """
    config = ExecutorConfig(
        max_concurrent_behaviors=max_concurrent,
        auto_match_threshold=auto_match_threshold,
    )
    
    return BehaviorExecutor(
        workflow_memory=workflow_memory,
        config=config,
    )
