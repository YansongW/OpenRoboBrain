"""
文件操作工具

提供文件读写、目录操作等能力。
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Union

# 尝试使用异步文件操作
try:
    import aiofiles
    HAS_AIOFILES = True
except ImportError:
    HAS_AIOFILES = False


async def read_file(
    path: str,
    encoding: str = "utf-8",
    max_size: int = 10 * 1024 * 1024,  # 10MB
) -> str:
    """
    读取文件内容
    
    Args:
        path: 文件路径
        encoding: 编码格式，默认utf-8
        max_size: 最大读取大小（字节），默认10MB
        
    Returns:
        文件内容
        
    Raises:
        FileNotFoundError: 文件不存在
        ValueError: 文件过大
    """
    file_path = Path(path)
    
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    
    file_size = file_path.stat().st_size
    if file_size > max_size:
        raise ValueError(f"File too large: {file_size} bytes (max: {max_size})")
    
    if HAS_AIOFILES:
        async with aiofiles.open(path, "r", encoding=encoding) as f:
            return await f.read()
    else:
        with open(path, "r", encoding=encoding) as f:
            return f.read()


async def write_file(
    path: str,
    content: str,
    encoding: str = "utf-8",
    create_dirs: bool = True,
) -> Dict:
    """
    写入文件内容（覆盖）
    
    Args:
        path: 文件路径
        content: 要写入的内容
        encoding: 编码格式，默认utf-8
        create_dirs: 是否自动创建父目录
        
    Returns:
        包含success和path的字典
    """
    file_path = Path(path)
    
    if create_dirs:
        file_path.parent.mkdir(parents=True, exist_ok=True)
    
    if HAS_AIOFILES:
        async with aiofiles.open(path, "w", encoding=encoding) as f:
            await f.write(content)
    else:
        with open(path, "w", encoding=encoding) as f:
            f.write(content)
    
    return {
        "success": True,
        "path": str(file_path.absolute()),
        "size": len(content.encode(encoding)),
    }


async def append_file(
    path: str,
    content: str,
    encoding: str = "utf-8",
    create_if_not_exists: bool = True,
) -> Dict:
    """
    追加内容到文件
    
    Args:
        path: 文件路径
        content: 要追加的内容
        encoding: 编码格式
        create_if_not_exists: 文件不存在时是否创建
        
    Returns:
        包含success和path的字典
    """
    file_path = Path(path)
    
    if not file_path.exists() and not create_if_not_exists:
        raise FileNotFoundError(f"File not found: {path}")
    
    if create_if_not_exists:
        file_path.parent.mkdir(parents=True, exist_ok=True)
    
    if HAS_AIOFILES:
        async with aiofiles.open(path, "a", encoding=encoding) as f:
            await f.write(content)
    else:
        with open(path, "a", encoding=encoding) as f:
            f.write(content)
    
    return {
        "success": True,
        "path": str(file_path.absolute()),
        "appended_size": len(content.encode(encoding)),
    }


async def list_directory(
    path: str,
    pattern: Optional[str] = None,
    include_hidden: bool = False,
    recursive: bool = False,
) -> List[Dict]:
    """
    列出目录内容
    
    Args:
        path: 目录路径
        pattern: 匹配模式（如 "*.py"）
        include_hidden: 是否包含隐藏文件
        recursive: 是否递归列出
        
    Returns:
        文件/目录信息列表
    """
    dir_path = Path(path)
    
    if not dir_path.exists():
        raise FileNotFoundError(f"Directory not found: {path}")
    
    if not dir_path.is_dir():
        raise NotADirectoryError(f"Not a directory: {path}")
    
    results = []
    
    if recursive:
        if pattern:
            items = dir_path.rglob(pattern)
        else:
            items = dir_path.rglob("*")
    else:
        if pattern:
            items = dir_path.glob(pattern)
        else:
            items = dir_path.iterdir()
    
    for item in items:
        # 跳过隐藏文件
        if not include_hidden and item.name.startswith("."):
            continue
        
        try:
            stat = item.stat()
            results.append({
                "name": item.name,
                "path": str(item.absolute()),
                "type": "directory" if item.is_dir() else "file",
                "size": stat.st_size if item.is_file() else None,
                "modified": stat.st_mtime,
            })
        except (PermissionError, OSError):
            # 跳过无权限的文件
            continue
    
    return results


async def file_exists(path: str) -> Dict:
    """
    检查文件或目录是否存在
    
    Args:
        path: 文件/目录路径
        
    Returns:
        包含exists、is_file、is_dir的字典
    """
    file_path = Path(path)
    
    return {
        "exists": file_path.exists(),
        "is_file": file_path.is_file(),
        "is_dir": file_path.is_dir(),
        "path": str(file_path.absolute()) if file_path.exists() else path,
    }


async def delete_file(
    path: str,
    recursive: bool = False,
) -> Dict:
    """
    删除文件或目录
    
    Args:
        path: 文件/目录路径
        recursive: 是否递归删除（用于目录）
        
    Returns:
        包含success的字典
        
    Warning:
        此操作不可逆，请谨慎使用
    """
    file_path = Path(path)
    
    if not file_path.exists():
        return {
            "success": False,
            "error": f"Path not found: {path}",
        }
    
    try:
        if file_path.is_file():
            file_path.unlink()
        elif file_path.is_dir():
            if recursive:
                shutil.rmtree(str(file_path))
            else:
                file_path.rmdir()  # 只能删除空目录
        
        return {
            "success": True,
            "deleted": str(file_path.absolute()),
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


async def create_directory(
    path: str,
    parents: bool = True,
    exist_ok: bool = True,
) -> Dict:
    """
    创建目录
    
    Args:
        path: 目录路径
        parents: 是否创建父目录
        exist_ok: 目录已存在时是否报错
        
    Returns:
        包含success和path的字典
    """
    dir_path = Path(path)
    
    try:
        dir_path.mkdir(parents=parents, exist_ok=exist_ok)
        return {
            "success": True,
            "path": str(dir_path.absolute()),
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


async def copy_file(
    src: str,
    dst: str,
    overwrite: bool = False,
) -> Dict:
    """
    复制文件
    
    Args:
        src: 源文件路径
        dst: 目标路径
        overwrite: 是否覆盖已存在的文件
        
    Returns:
        包含success的字典
    """
    src_path = Path(src)
    dst_path = Path(dst)
    
    if not src_path.exists():
        return {
            "success": False,
            "error": f"Source not found: {src}",
        }
    
    if dst_path.exists() and not overwrite:
        return {
            "success": False,
            "error": f"Destination already exists: {dst}",
        }
    
    try:
        # 创建目标目录
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        
        if src_path.is_file():
            shutil.copy2(str(src_path), str(dst_path))
        else:
            shutil.copytree(str(src_path), str(dst_path))
        
        return {
            "success": True,
            "src": str(src_path.absolute()),
            "dst": str(dst_path.absolute()),
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


async def move_file(
    src: str,
    dst: str,
    overwrite: bool = False,
) -> Dict:
    """
    移动文件或目录
    
    Args:
        src: 源路径
        dst: 目标路径
        overwrite: 是否覆盖
        
    Returns:
        包含success的字典
    """
    src_path = Path(src)
    dst_path = Path(dst)
    
    if not src_path.exists():
        return {
            "success": False,
            "error": f"Source not found: {src}",
        }
    
    if dst_path.exists() and not overwrite:
        return {
            "success": False,
            "error": f"Destination already exists: {dst}",
        }
    
    try:
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_path), str(dst_path))
        
        return {
            "success": True,
            "src": str(src_path),
            "dst": str(dst_path.absolute()),
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }
