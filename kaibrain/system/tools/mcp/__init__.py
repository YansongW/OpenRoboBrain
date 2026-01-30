"""
MCP (Model Context Protocol) 集成模块

提供MCP客户端和服务端能力，支持与外部MCP Server互联互通。
"""

from kaibrain.system.tools.mcp.client import MCPClient, MCPClientConfig
from kaibrain.system.tools.mcp.server import KaiBrainMCPServer

__all__ = [
    "MCPClient",
    "MCPClientConfig",
    "KaiBrainMCPServer",
]
