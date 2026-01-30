"""
内建工具模块

提供常用的内建工具，包括Shell、文件、HTTP等。
"""

from kaibrain.system.tools.builtin.shell import (
    shell_execute,
    shell_execute_background,
)
from kaibrain.system.tools.builtin.file import (
    read_file,
    write_file,
    append_file,
    list_directory,
    file_exists,
    delete_file,
    create_directory,
)
from kaibrain.system.tools.builtin.http import (
    http_get,
    http_post,
    http_request,
)

__all__ = [
    # Shell工具
    "shell_execute",
    "shell_execute_background",
    # 文件工具
    "read_file",
    "write_file",
    "append_file",
    "list_directory",
    "file_exists",
    "delete_file",
    "create_directory",
    # HTTP工具
    "http_get",
    "http_post",
    "http_request",
]


def register_all_builtin_tools(registry) -> int:
    """
    注册所有内建工具到注册表
    
    Args:
        registry: 工具注册表
        
    Returns:
        注册的工具数量
    """
    from kaibrain.system.tools.base import Tool
    
    tools = [
        # Shell工具
        Tool.from_function(shell_execute, name="shell_execute"),
        Tool.from_function(shell_execute_background, name="shell_execute_background"),
        # 文件工具
        Tool.from_function(read_file, name="read_file"),
        Tool.from_function(write_file, name="write_file"),
        Tool.from_function(append_file, name="append_file"),
        Tool.from_function(list_directory, name="list_directory"),
        Tool.from_function(file_exists, name="file_exists"),
        Tool.from_function(delete_file, name="delete_file"),
        Tool.from_function(create_directory, name="create_directory"),
        # HTTP工具
        Tool.from_function(http_get, name="http_get"),
        Tool.from_function(http_post, name="http_post"),
        Tool.from_function(http_request, name="http_request"),
    ]
    
    for tool in tools:
        category = _get_tool_category(tool.name)
        registry.register(tool, category=category)
    
    return len(tools)


def _get_tool_category(tool_name: str) -> str:
    """根据工具名确定分类"""
    if tool_name.startswith("shell"):
        return "builtin:shell"
    elif tool_name in ("read_file", "write_file", "append_file", "list_directory", 
                       "file_exists", "delete_file", "create_directory"):
        return "builtin:file"
    elif tool_name.startswith("http"):
        return "builtin:http"
    return "builtin"
