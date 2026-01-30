"""
MCP客户端

连接外部MCP Server，发现并调用其工具。
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from kaibrain.system.services.logger import LoggerMixin, get_logger

logger = get_logger(__name__)


class MCPTransport(str, Enum):
    """MCP传输方式"""
    STDIO = "stdio"
    SSE = "sse"
    HTTP = "http"
    WEBSOCKET = "websocket"


@dataclass
class MCPClientConfig:
    """MCP客户端配置"""
    transport: MCPTransport = MCPTransport.STDIO
    
    # stdio配置
    command: Optional[str] = None
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    cwd: Optional[str] = None
    
    # HTTP/SSE配置
    url: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    
    # 通用配置
    timeout: float = 30.0
    
    @classmethod
    def from_dict(cls, data: dict) -> "MCPClientConfig":
        """从字典创建"""
        transport = data.get("transport", "stdio")
        if isinstance(transport, str):
            transport = MCPTransport(transport)
        
        return cls(
            transport=transport,
            command=data.get("command"),
            args=data.get("args", []),
            env=data.get("env", {}),
            cwd=data.get("cwd"),
            url=data.get("url"),
            headers=data.get("headers", {}),
            timeout=data.get("timeout", 30.0),
        )


class MCPClient(LoggerMixin):
    """
    MCP客户端
    
    连接外部MCP Server，提供工具发现和调用能力。
    支持stdio、SSE、HTTP多种传输方式。
    """
    
    def __init__(
        self,
        transport: Union[str, MCPTransport] = MCPTransport.STDIO,
        **config,
    ):
        """
        初始化MCP客户端
        
        Args:
            transport: 传输方式
            **config: 传输配置
        """
        if isinstance(transport, str):
            transport = MCPTransport(transport)
        
        self.transport = transport
        self.config = MCPClientConfig(transport=transport, **config)
        
        self._session = None
        self._read_stream = None
        self._write_stream = None
        self._process = None
        self._connected = False
        self._tools_cache: Optional[List[dict]] = None
        self._resources_cache: Optional[List[dict]] = None
    
    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self._connected
    
    async def connect(self) -> None:
        """建立连接"""
        if self._connected:
            self.logger.warning("Already connected")
            return
        
        try:
            if self.transport == MCPTransport.STDIO:
                await self._connect_stdio()
            elif self.transport == MCPTransport.SSE:
                await self._connect_sse()
            elif self.transport == MCPTransport.HTTP:
                await self._connect_http()
            else:
                raise ValueError(f"Unsupported transport: {self.transport}")
            
            self._connected = True
            self.logger.info(f"Connected to MCP server via {self.transport.value}")
            
        except Exception as e:
            self.logger.error(f"Failed to connect: {e}")
            raise
    
    async def disconnect(self) -> None:
        """断开连接"""
        if not self._connected:
            return
        
        try:
            if self._process:
                self._process.terminate()
                await asyncio.sleep(0.5)
                if self._process.returncode is None:
                    self._process.kill()
                self._process = None
            
            if self._session:
                # 关闭HTTP/SSE会话
                await self._session.close()
                self._session = None
            
            self._connected = False
            self._tools_cache = None
            self._resources_cache = None
            
            self.logger.info("Disconnected from MCP server")
            
        except Exception as e:
            self.logger.error(f"Error during disconnect: {e}")
    
    async def _connect_stdio(self) -> None:
        """通过stdio连接"""
        if not self.config.command:
            raise ValueError("command is required for stdio transport")
        
        # 尝试使用官方MCP SDK
        try:
            from mcp import ClientSession
            from mcp.client.stdio import stdio_client, StdioServerParameters
            
            server_params = StdioServerParameters(
                command=self.config.command,
                args=self.config.args,
                env=self.config.env or None,
            )
            
            # 创建stdio连接
            self._read_stream, self._write_stream = await stdio_client(server_params)
            self._session = ClientSession(self._read_stream, self._write_stream)
            await self._session.initialize()
            
            self.logger.info("Connected using MCP SDK (stdio)")
            return
            
        except ImportError:
            self.logger.warning("MCP SDK not available, using fallback implementation")
        
        # Fallback: 直接启动进程
        import os
        
        env = os.environ.copy()
        if self.config.env:
            env.update(self.config.env)
        
        self._process = await asyncio.create_subprocess_exec(
            self.config.command,
            *self.config.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=self.config.cwd,
        )
        
        # 发送初始化请求
        await self._send_jsonrpc({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "KaiBrain",
                    "version": "0.1.0",
                }
            }
        })
        
        response = await self._read_jsonrpc()
        if "error" in response:
            raise RuntimeError(f"Initialize failed: {response['error']}")
        
        # 发送initialized通知
        await self._send_jsonrpc({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        })
    
    async def _connect_sse(self) -> None:
        """通过SSE连接"""
        if not self.config.url:
            raise ValueError("url is required for SSE transport")
        
        try:
            from mcp import ClientSession
            from mcp.client.sse import sse_client
            
            self._read_stream, self._write_stream = await sse_client(self.config.url)
            self._session = ClientSession(self._read_stream, self._write_stream)
            await self._session.initialize()
            
            self.logger.info("Connected using MCP SDK (SSE)")
            return
            
        except ImportError:
            self.logger.warning("MCP SDK not available for SSE")
            raise ImportError("MCP SDK required for SSE transport")
    
    async def _connect_http(self) -> None:
        """通过HTTP连接"""
        if not self.config.url:
            raise ValueError("url is required for HTTP transport")
        
        try:
            import httpx
            self._session = httpx.AsyncClient(
                base_url=self.config.url,
                headers=self.config.headers,
                timeout=self.config.timeout,
            )
        except ImportError:
            import aiohttp
            self._session = aiohttp.ClientSession(
                base_url=self.config.url,
                headers=self.config.headers,
            )
    
    async def _send_jsonrpc(self, message: dict) -> None:
        """发送JSON-RPC消息（用于fallback实现）"""
        if self._process and self._process.stdin:
            data = json.dumps(message) + "\n"
            self._process.stdin.write(data.encode())
            await self._process.stdin.drain()
    
    async def _read_jsonrpc(self) -> dict:
        """读取JSON-RPC响应（用于fallback实现）"""
        if self._process and self._process.stdout:
            line = await asyncio.wait_for(
                self._process.stdout.readline(),
                timeout=self.config.timeout,
            )
            return json.loads(line.decode())
        return {}
    
    async def list_tools(self, force_refresh: bool = False) -> List[dict]:
        """
        获取可用工具列表
        
        Args:
            force_refresh: 是否强制刷新缓存
            
        Returns:
            工具定义列表
        """
        if self._tools_cache and not force_refresh:
            return self._tools_cache
        
        if not self._connected:
            raise RuntimeError("Not connected to MCP server")
        
        if self._session and hasattr(self._session, "list_tools"):
            # 使用MCP SDK
            result = await self._session.list_tools()
            self._tools_cache = [
                {
                    "name": tool.name,
                    "description": tool.description or "",
                    "inputSchema": tool.inputSchema,
                }
                for tool in result.tools
            ]
        else:
            # Fallback实现
            await self._send_jsonrpc({
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
            })
            response = await self._read_jsonrpc()
            self._tools_cache = response.get("result", {}).get("tools", [])
        
        return self._tools_cache
    
    async def call_tool(
        self,
        name: str,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        调用工具
        
        Args:
            name: 工具名称
            arguments: 工具参数
            
        Returns:
            工具执行结果
        """
        if not self._connected:
            raise RuntimeError("Not connected to MCP server")
        
        arguments = arguments or {}
        
        if self._session and hasattr(self._session, "call_tool"):
            # 使用MCP SDK
            result = await self._session.call_tool(name, arguments)
            
            # 解析结果
            if result.content:
                if len(result.content) == 1:
                    content = result.content[0]
                    if hasattr(content, "text"):
                        return content.text
                    return content
                return [
                    c.text if hasattr(c, "text") else c 
                    for c in result.content
                ]
            return None
        else:
            # Fallback实现
            await self._send_jsonrpc({
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": name,
                    "arguments": arguments,
                }
            })
            response = await self._read_jsonrpc()
            
            if "error" in response:
                raise RuntimeError(f"Tool call failed: {response['error']}")
            
            result = response.get("result", {})
            content = result.get("content", [])
            
            if content:
                if len(content) == 1:
                    return content[0].get("text", content[0])
                return content
            return None
    
    async def list_resources(self, force_refresh: bool = False) -> List[dict]:
        """
        获取可用资源列表
        
        Args:
            force_refresh: 是否强制刷新
            
        Returns:
            资源定义列表
        """
        if self._resources_cache and not force_refresh:
            return self._resources_cache
        
        if not self._connected:
            raise RuntimeError("Not connected to MCP server")
        
        if self._session and hasattr(self._session, "list_resources"):
            result = await self._session.list_resources()
            self._resources_cache = [
                {
                    "uri": r.uri,
                    "name": r.name or "",
                    "description": r.description or "",
                    "mimeType": r.mimeType or "",
                }
                for r in result.resources
            ]
        else:
            await self._send_jsonrpc({
                "jsonrpc": "2.0",
                "id": 4,
                "method": "resources/list",
            })
            response = await self._read_jsonrpc()
            self._resources_cache = response.get("result", {}).get("resources", [])
        
        return self._resources_cache
    
    async def read_resource(self, uri: str) -> Any:
        """
        读取资源
        
        Args:
            uri: 资源URI
            
        Returns:
            资源内容
        """
        if not self._connected:
            raise RuntimeError("Not connected to MCP server")
        
        if self._session and hasattr(self._session, "read_resource"):
            result = await self._session.read_resource(uri)
            if result.contents:
                content = result.contents[0]
                if hasattr(content, "text"):
                    return content.text
                return content
            return None
        else:
            await self._send_jsonrpc({
                "jsonrpc": "2.0",
                "id": 5,
                "method": "resources/read",
                "params": {"uri": uri}
            })
            response = await self._read_jsonrpc()
            
            if "error" in response:
                raise RuntimeError(f"Resource read failed: {response['error']}")
            
            contents = response.get("result", {}).get("contents", [])
            if contents:
                return contents[0].get("text", contents[0])
            return None
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        await self.disconnect()
