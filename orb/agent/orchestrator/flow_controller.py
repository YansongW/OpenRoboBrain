"""
流程控制

管理任务的执行流程。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from orb.agent.orchestrator.task_decomposer import Task, TaskType
from orb.system.services.logger import LoggerMixin

if TYPE_CHECKING:
    from orb.agent.base import BaseAgent


class ExecutionState(Enum):
    """执行状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ExecutionContext:
    """执行上下文"""
    task: Task
    state: ExecutionState = ExecutionState.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    
    # 用于存储中间结果
    variables: Dict[str, Any] = field(default_factory=dict)


class FlowController(LoggerMixin):
    """
    流程控制器
    
    管理任务的执行流程，支持：
    - 顺序执行
    - 并行执行
    - 条件分支
    """
    
    def __init__(self):
        self._executor: Optional[Callable] = None
        self._running_contexts: Dict[str, ExecutionContext] = {}
        
    def set_executor(self, executor: Callable) -> None:
        """
        设置任务执行器
        
        Args:
            executor: 执行函数，签名为 async (task: Task) -> Any
        """
        self._executor = executor
        
    async def execute(self, task: Task) -> ExecutionContext:
        """
        执行任务
        
        Args:
            task: 任务
            
        Returns:
            ExecutionContext
        """
        context = ExecutionContext(task=task)
        self._running_contexts[task.task_id] = context
        
        context.state = ExecutionState.RUNNING
        context.started_at = datetime.now()
        
        try:
            if task.task_type == TaskType.ATOMIC:
                result = await self._execute_atomic(task)
                
            elif task.task_type == TaskType.SEQUENTIAL:
                result = await self._execute_sequential(task)
                
            elif task.task_type == TaskType.PARALLEL:
                result = await self._execute_parallel(task)
                
            elif task.task_type == TaskType.CONDITIONAL:
                result = await self._execute_conditional(task)
                
            else:
                raise ValueError(f"未知任务类型: {task.task_type}")
                
            context.result = result
            context.state = ExecutionState.COMPLETED
            task.result = result
            task.success = True
            
        except Exception as e:
            context.error = str(e)
            context.state = ExecutionState.FAILED
            task.error = str(e)
            task.success = False
            self.logger.error(f"任务执行失败: {task.name} - {e}")
            
        finally:
            context.completed_at = datetime.now()
            
        return context
        
    async def _execute_atomic(self, task: Task) -> Any:
        """执行原子任务"""
        if not self._executor:
            raise RuntimeError("执行器未设置")
            
        self.logger.info(f"执行原子任务: {task.name} ({task.agent_type})")
        return await self._executor(task)
        
    async def _execute_sequential(self, task: Task) -> List[Any]:
        """执行顺序任务"""
        self.logger.info(f"执行顺序任务: {task.name} ({len(task.subtasks)} 个子任务)")
        
        results = []
        prev_result = task.input_data
        
        for subtask in task.subtasks:
            # 将上一个任务的结果作为下一个任务的输入
            if prev_result and isinstance(prev_result, dict):
                subtask.input_data.update(prev_result)
                
            context = await self.execute(subtask)
            
            if context.state == ExecutionState.FAILED:
                raise Exception(f"子任务失败: {subtask.name} - {context.error}")
                
            results.append(context.result)
            prev_result = context.result
            
        return results
        
    async def _execute_parallel(self, task: Task) -> List[Any]:
        """执行并行任务"""
        self.logger.info(f"执行并行任务: {task.name} ({len(task.subtasks)} 个子任务)")
        
        # 并行执行所有子任务
        coroutines = [self.execute(subtask) for subtask in task.subtasks]
        contexts = await asyncio.gather(*coroutines, return_exceptions=True)
        
        results = []
        for context in contexts:
            if isinstance(context, Exception):
                self.logger.error(f"并行子任务异常: {context}")
                results.append(None)
            elif context.state == ExecutionState.FAILED:
                self.logger.error(f"并行子任务失败: {context.error}")
                results.append(None)
            else:
                results.append(context.result)
                
        return results
        
    async def _execute_conditional(self, task: Task) -> Any:
        """执行条件任务"""
        self.logger.info(f"执行条件任务: {task.name}")
        
        # 评估条件
        condition_result = self._evaluate_condition(
            task.condition,
            task.input_data,
        )
        
        # 根据条件选择子任务
        if task.subtasks:
            if condition_result and len(task.subtasks) > 0:
                return await self.execute(task.subtasks[0])
            elif not condition_result and len(task.subtasks) > 1:
                return await self.execute(task.subtasks[1])
                
        return None
        
    def _evaluate_condition(
        self,
        condition: Optional[str],
        context: Dict[str, Any],
    ) -> bool:
        """评估条件表达式"""
        if not condition:
            return True
            
        # 简单的条件评估（实际可能需要更复杂的表达式解析）
        try:
            return bool(eval(condition, {"__builtins__": {}}, context))
        except Exception:
            return False
            
    def cancel(self, task_id: str) -> bool:
        """取消任务"""
        context = self._running_contexts.get(task_id)
        if context and context.state == ExecutionState.RUNNING:
            context.state = ExecutionState.CANCELLED
            return True
        return False
        
    def get_context(self, task_id: str) -> Optional[ExecutionContext]:
        """获取执行上下文"""
        return self._running_contexts.get(task_id)
