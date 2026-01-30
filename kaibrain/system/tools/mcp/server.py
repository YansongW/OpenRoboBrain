"""
MCP服务端

将KaiBrain能力暴露为MCP Server，供外部系统调用。
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from kaibrain.system.services.logger import LoggerMixin, get_logger

if TYPE_CHECKING:
    from kaibrain.core import KaiBrain

logger = get_logger(__name__)


class KaiBrainMCPServer(LoggerMixin):
    """
    KaiBrain MCP Server
    
    将KaiBrain的技能和资源暴露为MCP Server，
    使外部系统（如Cursor、Claude等）可以调用。
    """
    
    def __init__(
        self,
        kaibrain: Optional["KaiBrain"] = None,
        name: str = "KaiBrain",
        version: str = "0.1.0",
    ):
        """
        初始化MCP Server
        
        Args:
            kaibrain: KaiBrain实例（可选）
            name: Server名称
            version: Server版本
        """
        self.kaibrain = kaibrain
        self.name = name
        self.version = version
        
        self._tools: Dict[str, dict] = {}
        self._resources: Dict[str, dict] = {}
        self._prompts: Dict[str, dict] = {}
        
        self._mcp = None
        self._running = False
        
        # 注册默认工具
        self._register_default_tools()
    
    def _register_default_tools(self) -> None:
        """注册默认工具"""
        # 如果有KaiBrain实例，注册相关工具
        if self.kaibrain:
            self.register_tool(
                name="execute_skill",
                description="执行KaiBrain技能",
                parameters={
                    "type": "object",
                    "properties": {
                        "skill_name": {
                            "type": "string",
                            "description": "技能名称",
                        },
                        "parameters": {
                            "type": "object",
                            "description": "技能参数",
                        },
                    },
                    "required": ["skill_name"],
                },
                handler=self._handle_execute_skill,
            )
            
            self.register_tool(
                name="get_robot_status",
                description="获取机器人当前状态",
                parameters={
                    "type": "object",
                    "properties": {},
                },
                handler=self._handle_get_status,
            )
            
            self.register_tool(
                name="list_skills",
                description="列出所有可用技能",
                parameters={
                    "type": "object",
                    "properties": {},
                },
                handler=self._handle_list_skills,
            )
    
    def register_tool(
        self,
        name: str,
        description: str,
        parameters: dict,
        handler: Callable,
    ) -> None:
        """
        注册工具
        
        Args:
            name: 工具名称
            description: 工具描述
            parameters: 参数JSON Schema
            handler: 处理函数
        """
        self._tools[name] = {
            "name": name,
            "description": description,
            "inputSchema": parameters,
            "handler": handler,
        }
        self.logger.debug(f"Registered MCP tool: {name}")
    
    def register_resource(
        self,
        uri: str,
        name: str,
        description: str = "",
        mime_type: str = "text/plain",
        handler: Optional[Callable] = None,
    ) -> None:
        """
        注册资源
        
        Args:
            uri: 资源URI
            name: 资源名称
            description: 资源描述
            mime_type: MIME类型
            handler: 读取处理函数
        """
        self._resources[uri] = {
            "uri": uri,
            "name": name,
            "description": description,
            "mimeType": mime_type,
            "handler": handler,
        }
        self.logger.debug(f"Registered MCP resource: {uri}")
    
    def register_prompt(
        self,
        name: str,
        description: str,
        arguments: Optional[List[dict]] = None,
        handler: Optional[Callable] = None,
    ) -> None:
        """
        注册提示模板
        
        Args:
            name: 模板名称
            description: 模板描述
            arguments: 参数定义
            handler: 生成处理函数
        """
        self._prompts[name] = {
            "name": name,
            "description": description,
            "arguments": arguments or [],
            "handler": handler,
        }
        self.logger.debug(f"Registered MCP prompt: {name}")
    
    async def _handle_execute_skill(
        self,
        skill_name: str,
        parameters: Optional[dict] = None,
    ) -> dict:
        """处理技能执行请求"""
        if not self.kaibrain:
            return {"error": "KaiBrain not initialized"}
        
        try:
            # 这里需要实现技能执行逻辑
            # 暂时返回占位响应
            return {
                "success": True,
                "skill": skill_name,
                "message": f"Skill '{skill_name}' executed",
            }
        except Exception as e:
            return {"error": str(e)}
    
    async def _handle_get_status(self) -> dict:
        """获取机器人状态"""
        if not self.kaibrain:
            return {"error": "KaiBrain not initialized"}
        
        return {
            "running": self.kaibrain._running if hasattr(self.kaibrain, "_running") else False,
            "name": "KaiBrain",
            "version": self.version,
        }
    
    async def _handle_list_skills(self) -> List[str]:
        """列出可用技能"""
        if not self.kaibrain:
            return []
        
        # 这里需要从KaiBrain获取技能列表
        return ["cooking", "cleaning", "navigation"]
    
    async def run(self, transport: str = "stdio") -> None:
        """
        启动MCP Server
        
        Args:
            transport: 传输方式 ("stdio", "sse")
        """
        try:
            from mcp.server import Server
            from mcp.server.stdio import stdio_server
        except ImportError:
            self.logger.error(
                "MCP SDK not installed. Install with: pip install mcp"
            )
            raise ImportError("MCP SDK required for server mode")
        
        # 创建MCP Server
        self._mcp = Server(self.name)
        
        # 注册工具处理器
        @self._mcp.list_tools()
        async def list_tools():
            return [
                {
                    "name": tool["name"],
                    "description": tool["description"],
                    "inputSchema": tool["inputSchema"],
                }
                for tool in self._tools.values()
            ]
        
        @self._mcp.call_tool()
        async def call_tool(name: str, arguments: dict):
            if name not in self._tools:
                raise ValueError(f"Unknown tool: {name}")
            
            tool = self._tools[name]
            handler = tool["handler"]
            
            if asyncio.iscoroutinefunction(handler):
                result = await handler(**arguments)
            else:
                result = handler(**arguments)
            
            return [{"type": "text", "text": str(result)}]
        
        # 注册资源处理器
        @self._mcp.list_resources()
        async def list_resources():
            return [
                {
                    "uri": res["uri"],
                    "name": res["name"],
                    "description": res["description"],
                    "mimeType": res["mimeType"],
                }
                for res in self._resources.values()
            ]
        
        @self._mcp.read_resource()
        async def read_resource(uri: str):
            if uri not in self._resources:
                raise ValueError(f"Unknown resource: {uri}")
            
            resource = self._resources[uri]
            handler = resource.get("handler")
            
            if handler:
                if asyncio.iscoroutinefunction(handler):
                    content = await handler()
                else:
                    content = handler()
            else:
                content = ""
            
            return [{"type": "text", "text": str(content)}]
        
        # 启动服务
        self._running = True
        self.logger.info(f"Starting MCP server ({transport})...")
        
        if transport == "stdio":
            async with stdio_server() as (read_stream, write_stream):
                await self._mcp.run(
                    read_stream,
                    write_stream,
                    self._mcp.create_initialization_options(),
                )
        else:
            raise ValueError(f"Unsupported transport: {transport}")
    
    async def stop(self) -> None:
        """停止MCP Server"""
        self._running = False
        self.logger.info("MCP server stopped")
    
    def tool(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ):
        """
        工具注册装饰器
        
        Examples:
            @server.tool()
            async def my_tool(param: str) -> str:
                '''工具描述'''
                return "result"
        """
        def decorator(func: Callable):
            tool_name = name or func.__name__
            tool_description = description or func.__doc__ or ""
            
            # 从函数签名提取参数schema
            import inspect
            sig = inspect.signature(func)
            
            properties = {}
            required = []
            
            for param_name, param in sig.parameters.items():
                if param_name in ("self", "cls"):
                    continue
                
                properties[param_name] = {
                    "type": "string",
                    "description": f"Parameter {param_name}",
                }
                
                if param.default is inspect.Parameter.empty:
                    required.append(param_name)
            
            parameters = {
                "type": "object",
                "properties": properties,
                "required": required,
            }
            
            self.register_tool(
                name=tool_name,
                description=tool_description.strip(),
                parameters=parameters,
                handler=func,
            )
            
            return func
        
        return decorator
    
    def resource(self, uri: str, name: Optional[str] = None):
        """
        资源注册装饰器
        
        Examples:
            @server.resource("robot://status")
            def get_status() -> dict:
                return {"status": "ok"}
        """
        def decorator(func: Callable):
            resource_name = name or func.__name__
            resource_description = func.__doc__ or ""
            
            self.register_resource(
                uri=uri,
                name=resource_name,
                description=resource_description.strip(),
                handler=func,
            )
            
            return func
        
        return decorator
