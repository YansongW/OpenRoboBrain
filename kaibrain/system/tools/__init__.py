"""
工具系统模块

提供统一的工具定义、注册和执行能力，支持内建工具和MCP工具。
"""

from kaibrain.system.tools.base import Tool, ToolCall, ToolResult
from kaibrain.system.tools.registry import ToolRegistry, tool
from kaibrain.system.tools.executor import ToolExecutor

__all__ = [
    # 基础类型
    "Tool",
    "ToolCall",
    "ToolResult",
    # 注册表
    "ToolRegistry",
    "tool",
    # 执行器
    "ToolExecutor",
]
