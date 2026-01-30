"""
工具执行器

负责执行工具调用，处理超时、错误和结果格式化。
"""

from __future__ import annotations

import asyncio
import inspect
import time
import traceback
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from kaibrain.system.tools.base import Tool, ToolCall, ToolResult
from kaibrain.system.services.logger import LoggerMixin, get_logger

if TYPE_CHECKING:
    from kaibrain.system.tools.registry import ToolRegistry

logger = get_logger(__name__)


class ToolExecutor(LoggerMixin):
    """
    工具执行器
    
    负责执行工具调用，处理超时、错误和权限检查。
    """
    
    def __init__(
        self,
        registry: "ToolRegistry",
        default_timeout: float = 30.0,
        max_concurrent: int = 5,
    ):
        """
        初始化执行器
        
        Args:
            registry: 工具注册表
            default_timeout: 默认超时时间（秒）
            max_concurrent: 最大并发执行数
        """
        self.registry = registry
        self.default_timeout = default_timeout
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._execution_history: List[Dict] = []
    
    async def execute(
        self,
        tool_call: ToolCall,
        timeout: Optional[float] = None,
    ) -> ToolResult:
        """
        执行单个工具调用
        
        Args:
            tool_call: 工具调用请求
            timeout: 超时时间（可选）
            
        Returns:
            ToolResult
        """
        start_time = time.time()
        tool = self.registry.get(tool_call.name)
        
        if not tool:
            self.logger.warning(f"Unknown tool: {tool_call.name}")
            return ToolResult(
                tool_call_id=tool_call.id,
                content=f"Error: Unknown tool '{tool_call.name}'",
                is_error=True,
                error_type="UnknownToolError",
            )
        
        # 确定超时时间
        exec_timeout = timeout or tool.timeout or self.default_timeout
        
        try:
            async with self._semaphore:
                result = await self._execute_tool(tool, tool_call, exec_timeout)
            
            execution_time = time.time() - start_time
            
            # 记录执行历史
            self._record_execution(tool_call, result, execution_time)
            
            return ToolResult(
                tool_call_id=tool_call.id,
                content=result,
                is_error=False,
                execution_time=execution_time,
            )
            
        except asyncio.TimeoutError:
            execution_time = time.time() - start_time
            self.logger.error(f"Tool {tool_call.name} timed out after {exec_timeout}s")
            
            return ToolResult(
                tool_call_id=tool_call.id,
                content=f"Error: Tool '{tool_call.name}' timed out after {exec_timeout} seconds",
                is_error=True,
                error_type="TimeoutError",
                execution_time=execution_time,
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"{type(e).__name__}: {str(e)}"
            self.logger.error(f"Tool {tool_call.name} failed: {error_msg}")
            self.logger.debug(traceback.format_exc())
            
            return ToolResult(
                tool_call_id=tool_call.id,
                content=f"Error: {error_msg}",
                is_error=True,
                error_type=type(e).__name__,
                execution_time=execution_time,
            )
    
    async def execute_batch(
        self,
        tool_calls: List[ToolCall],
        parallel: bool = True,
    ) -> List[ToolResult]:
        """
        批量执行工具调用
        
        Args:
            tool_calls: 工具调用列表
            parallel: 是否并行执行
            
        Returns:
            结果列表
        """
        if parallel:
            tasks = [self.execute(tc) for tc in tool_calls]
            return await asyncio.gather(*tasks)
        else:
            results = []
            for tc in tool_calls:
                result = await self.execute(tc)
                results.append(result)
            return results
    
    async def _execute_tool(
        self,
        tool: Tool,
        tool_call: ToolCall,
        timeout: float,
    ) -> Any:
        """
        实际执行工具
        
        Args:
            tool: 工具实例
            tool_call: 工具调用
            timeout: 超时时间
            
        Returns:
            执行结果
        """
        if not tool.handler:
            raise ValueError(f"Tool {tool.name} has no handler")
        
        # 准备参数
        arguments = tool_call.arguments or {}
        
        # 执行
        if tool.is_async or inspect.iscoroutinefunction(tool.handler):
            # 异步执行
            coro = tool.handler(**arguments)
            result = await asyncio.wait_for(coro, timeout=timeout)
        else:
            # 同步执行（在线程池中）
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: tool.handler(**arguments)),
                timeout=timeout,
            )
        
        return result
    
    def _record_execution(
        self,
        tool_call: ToolCall,
        result: Any,
        execution_time: float,
    ) -> None:
        """记录执行历史"""
        record = {
            "tool_call_id": tool_call.id,
            "tool_name": tool_call.name,
            "arguments": tool_call.arguments,
            "execution_time": execution_time,
            "timestamp": time.time(),
        }
        
        self._execution_history.append(record)
        
        # 限制历史记录数量
        if len(self._execution_history) > 100:
            self._execution_history = self._execution_history[-100:]
    
    def get_execution_history(self, limit: int = 10) -> List[Dict]:
        """获取最近的执行历史"""
        return self._execution_history[-limit:]
    
    def get_stats(self) -> Dict:
        """获取执行统计"""
        if not self._execution_history:
            return {
                "total_executions": 0,
                "avg_execution_time": 0,
                "tools_used": [],
            }
        
        total = len(self._execution_history)
        avg_time = sum(r["execution_time"] for r in self._execution_history) / total
        tools_used = list(set(r["tool_name"] for r in self._execution_history))
        
        return {
            "total_executions": total,
            "avg_execution_time": avg_time,
            "tools_used": tools_used,
        }


class SafeToolExecutor(ToolExecutor):
    """
    安全工具执行器
    
    添加额外的安全检查和确认机制。
    """
    
    def __init__(
        self,
        registry: "ToolRegistry",
        confirmation_callback: Optional[callable] = None,
        blocked_tools: Optional[List[str]] = None,
        **kwargs,
    ):
        """
        初始化安全执行器
        
        Args:
            registry: 工具注册表
            confirmation_callback: 确认回调函数
            blocked_tools: 被阻止的工具列表
            **kwargs: 其他参数
        """
        super().__init__(registry, **kwargs)
        self.confirmation_callback = confirmation_callback
        self.blocked_tools = set(blocked_tools or [])
    
    async def execute(
        self,
        tool_call: ToolCall,
        timeout: Optional[float] = None,
    ) -> ToolResult:
        """
        安全执行工具调用
        
        包含额外的安全检查。
        """
        # 检查是否被阻止
        if tool_call.name in self.blocked_tools:
            return ToolResult(
                tool_call_id=tool_call.id,
                content=f"Error: Tool '{tool_call.name}' is blocked",
                is_error=True,
                error_type="BlockedToolError",
            )
        
        # 检查是否需要确认
        tool = self.registry.get(tool_call.name)
        if tool and tool.require_confirmation and self.confirmation_callback:
            confirmed = await self._request_confirmation(tool_call)
            if not confirmed:
                return ToolResult(
                    tool_call_id=tool_call.id,
                    content="Tool execution cancelled by user",
                    is_error=True,
                    error_type="CancelledError",
                )
        
        return await super().execute(tool_call, timeout)
    
    async def _request_confirmation(self, tool_call: ToolCall) -> bool:
        """
        请求用户确认
        
        Args:
            tool_call: 工具调用
            
        Returns:
            是否确认
        """
        if self.confirmation_callback:
            if asyncio.iscoroutinefunction(self.confirmation_callback):
                return await self.confirmation_callback(tool_call)
            else:
                return self.confirmation_callback(tool_call)
        return True
    
    def block_tool(self, name: str) -> None:
        """阻止工具"""
        self.blocked_tools.add(name)
    
    def unblock_tool(self, name: str) -> None:
        """解除阻止"""
        self.blocked_tools.discard(name)
