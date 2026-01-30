"""
工具基类定义

定义工具、工具调用和工具结果的数据结构。
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union, get_type_hints


@dataclass
class Tool:
    """
    工具定义
    
    兼容OpenAI function calling、Claude tool use和MCP格式。
    """
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema格式
    handler: Optional[Callable] = None  # 执行函数
    
    # MCP扩展
    mcp_server: Optional[str] = None  # 来源MCP Server
    annotations: Optional[Dict[str, Any]] = None  # 工具元数据
    
    # 额外配置
    is_async: bool = True  # 是否异步
    timeout: float = 30.0  # 执行超时
    require_confirmation: bool = False  # 是否需要确认
    
    def to_openai_format(self) -> dict:
        """转换为OpenAI function calling格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }
    
    def to_anthropic_format(self) -> dict:
        """转换为Claude tool use格式"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }
    
    def to_mcp_format(self) -> dict:
        """转换为MCP格式"""
        result = {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.parameters,
        }
        if self.annotations:
            result["annotations"] = self.annotations
        return result
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "mcp_server": self.mcp_server,
            "annotations": self.annotations,
        }
    
    @classmethod
    def from_function(
        cls,
        func: Callable,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> "Tool":
        """
        从函数创建工具
        
        自动从函数签名和docstring提取信息。
        
        Args:
            func: 函数
            name: 工具名称（可选，默认使用函数名）
            description: 描述（可选，默认使用docstring）
            
        Returns:
            Tool实例
        """
        tool_name = name or func.__name__
        tool_description = description or func.__doc__ or f"Execute {tool_name}"
        
        # 提取参数schema
        parameters = extract_parameters_schema(func)
        
        # 检查是否异步
        is_async = inspect.iscoroutinefunction(func)
        
        return cls(
            name=tool_name,
            description=tool_description.strip(),
            parameters=parameters,
            handler=func,
            is_async=is_async,
        )


@dataclass
class ToolCall:
    """工具调用请求"""
    id: str
    name: str
    arguments: Dict[str, Any]
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "arguments": self.arguments,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "ToolCall":
        """从字典创建"""
        return cls(
            id=data["id"],
            name=data["name"],
            arguments=data.get("arguments", {}),
        )


@dataclass
class ToolResult:
    """工具执行结果"""
    tool_call_id: str
    content: Any
    is_error: bool = False
    error_type: Optional[str] = None
    execution_time: Optional[float] = None
    
    def to_dict(self) -> dict:
        """转换为字典"""
        result = {
            "tool_call_id": self.tool_call_id,
            "content": self.content,
            "is_error": self.is_error,
        }
        if self.error_type:
            result["error_type"] = self.error_type
        if self.execution_time is not None:
            result["execution_time"] = self.execution_time
        return result
    
    def to_string(self) -> str:
        """转换为字符串（用于发送给LLM）"""
        import json
        
        if isinstance(self.content, str):
            return self.content
        try:
            return json.dumps(self.content, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            return str(self.content)


def extract_parameters_schema(func: Callable) -> Dict[str, Any]:
    """
    从函数签名提取JSON Schema格式的参数定义
    
    Args:
        func: 函数
        
    Returns:
        JSON Schema格式的参数定义
    """
    sig = inspect.signature(func)
    
    # 尝试获取类型注解
    try:
        hints = get_type_hints(func)
    except Exception:
        hints = {}
    
    properties = {}
    required = []
    
    for param_name, param in sig.parameters.items():
        # 跳过self和特殊参数
        if param_name in ("self", "cls", "args", "kwargs"):
            continue
        
        # 获取类型注解
        param_type = hints.get(param_name, Any)
        
        # 转换为JSON Schema类型
        json_type = python_type_to_json_schema(param_type)
        
        # 提取参数描述（从docstring）
        param_description = extract_param_description(func, param_name)
        
        properties[param_name] = {
            **json_type,
            "description": param_description or f"Parameter {param_name}",
        }
        
        # 检查是否必需
        if param.default is inspect.Parameter.empty:
            required.append(param_name)
    
    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


def python_type_to_json_schema(python_type) -> Dict[str, Any]:
    """
    将Python类型转换为JSON Schema类型
    
    Args:
        python_type: Python类型
        
    Returns:
        JSON Schema类型定义
    """
    import typing
    
    # 获取origin类型（用于泛型）
    origin = getattr(python_type, "__origin__", None)
    
    # 基本类型映射
    type_map = {
        str: {"type": "string"},
        int: {"type": "integer"},
        float: {"type": "number"},
        bool: {"type": "boolean"},
        list: {"type": "array"},
        dict: {"type": "object"},
        type(None): {"type": "null"},
    }
    
    if python_type in type_map:
        return type_map[python_type]
    
    # 处理Optional
    if origin is Union:
        args = getattr(python_type, "__args__", ())
        # Optional[X] 是 Union[X, None]
        non_none_args = [a for a in args if a is not type(None)]
        if len(non_none_args) == 1:
            return python_type_to_json_schema(non_none_args[0])
    
    # 处理List[X]
    if origin is list:
        args = getattr(python_type, "__args__", ())
        if args:
            return {
                "type": "array",
                "items": python_type_to_json_schema(args[0]),
            }
        return {"type": "array"}
    
    # 处理Dict[K, V]
    if origin is dict:
        return {"type": "object"}
    
    # 默认
    return {"type": "string"}


def extract_param_description(func: Callable, param_name: str) -> Optional[str]:
    """
    从函数docstring提取参数描述
    
    支持Google风格和Sphinx风格的docstring。
    
    Args:
        func: 函数
        param_name: 参数名
        
    Returns:
        参数描述
    """
    docstring = func.__doc__
    if not docstring:
        return None
    
    import re
    
    # Google风格: param_name: description
    # Sphinx风格: :param param_name: description
    patterns = [
        rf"{param_name}:\s*(.+?)(?:\n|$)",  # Google风格
        rf":param {param_name}:\s*(.+?)(?:\n|$)",  # Sphinx风格
        rf"Args:\s*.*?{param_name}:\s*(.+?)(?:\n|$)",  # Google风格（在Args块内）
    ]
    
    for pattern in patterns:
        match = re.search(pattern, docstring, re.DOTALL)
        if match:
            return match.group(1).strip()
    
    return None
