"""
MCP (Model Context Protocol) 集成模块

提供MCP客户端和服务端能力，支持与外部MCP Server互联互通。
"""

from orb.system.tools.mcp.client import MCPClient, MCPClientConfig
from orb.system.tools.mcp.server import orbMCPServer

__all__ = [
    "MCPClient",
    "MCPClientConfig",
    "ORBMCPServer",
]
