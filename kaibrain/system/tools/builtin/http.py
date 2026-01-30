"""
HTTP请求工具

提供HTTP请求能力。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Union


async def http_get(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, str]] = None,
    timeout: int = 30,
) -> Dict:
    """
    发送HTTP GET请求
    
    Args:
        url: 请求URL
        headers: 请求头（可选）
        params: URL参数（可选）
        timeout: 超时时间（秒）
        
    Returns:
        包含status_code、headers、body的字典
        
    Examples:
        >>> result = await http_get("https://api.example.com/data")
        >>> print(result["body"])
    """
    return await http_request(
        method="GET",
        url=url,
        headers=headers,
        params=params,
        timeout=timeout,
    )


async def http_post(
    url: str,
    data: Optional[Union[Dict, str]] = None,
    json_data: Optional[Dict] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 30,
) -> Dict:
    """
    发送HTTP POST请求
    
    Args:
        url: 请求URL
        data: 表单数据或原始数据
        json_data: JSON数据（会自动设置Content-Type）
        headers: 请求头（可选）
        timeout: 超时时间（秒）
        
    Returns:
        包含status_code、headers、body的字典
    """
    return await http_request(
        method="POST",
        url=url,
        data=data,
        json_data=json_data,
        headers=headers,
        timeout=timeout,
    )


async def http_request(
    method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, str]] = None,
    data: Optional[Union[Dict, str]] = None,
    json_data: Optional[Dict] = None,
    timeout: int = 30,
    follow_redirects: bool = True,
) -> Dict:
    """
    发送HTTP请求
    
    Args:
        method: 请求方法 (GET, POST, PUT, DELETE, etc.)
        url: 请求URL
        headers: 请求头（可选）
        params: URL参数（可选）
        data: 请求体数据（可选）
        json_data: JSON数据（可选，会自动序列化）
        timeout: 超时时间（秒）
        follow_redirects: 是否跟随重定向
        
    Returns:
        包含status_code、headers、body、success的字典
    """
    try:
        import httpx
    except ImportError:
        try:
            import aiohttp
            return await _http_request_aiohttp(
                method=method,
                url=url,
                headers=headers,
                params=params,
                data=data,
                json_data=json_data,
                timeout=timeout,
            )
        except ImportError:
            return {
                "success": False,
                "error": "Neither httpx nor aiohttp is installed. Install with: pip install httpx",
                "status_code": None,
            }
    
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=follow_redirects,
        ) as client:
            # 构建请求参数
            request_kwargs = {
                "method": method.upper(),
                "url": url,
            }
            
            if headers:
                request_kwargs["headers"] = headers
            if params:
                request_kwargs["params"] = params
            if json_data:
                request_kwargs["json"] = json_data
            elif data:
                request_kwargs["data"] = data
            
            response = await client.request(**request_kwargs)
            
            # 尝试解析JSON响应
            body = response.text
            try:
                body_json = response.json()
                body = body_json
            except (json.JSONDecodeError, Exception):
                pass
            
            return {
                "success": True,
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": body,
                "url": str(response.url),
            }
            
    except httpx.TimeoutException:
        return {
            "success": False,
            "error": f"Request timed out after {timeout} seconds",
            "status_code": None,
        }
    except httpx.RequestError as e:
        return {
            "success": False,
            "error": f"Request error: {str(e)}",
            "status_code": None,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
            "status_code": None,
        }


async def _http_request_aiohttp(
    method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, str]] = None,
    data: Optional[Union[Dict, str]] = None,
    json_data: Optional[Dict] = None,
    timeout: int = 30,
) -> Dict:
    """使用aiohttp发送请求（备选方案）"""
    import aiohttp
    
    try:
        timeout_obj = aiohttp.ClientTimeout(total=timeout)
        
        async with aiohttp.ClientSession(timeout=timeout_obj) as session:
            request_kwargs = {
                "method": method.upper(),
                "url": url,
            }
            
            if headers:
                request_kwargs["headers"] = headers
            if params:
                request_kwargs["params"] = params
            if json_data:
                request_kwargs["json"] = json_data
            elif data:
                request_kwargs["data"] = data
            
            async with session.request(**request_kwargs) as response:
                body = await response.text()
                
                # 尝试解析JSON
                try:
                    body = await response.json()
                except (json.JSONDecodeError, aiohttp.ContentTypeError):
                    pass
                
                return {
                    "success": True,
                    "status_code": response.status,
                    "headers": dict(response.headers),
                    "body": body,
                    "url": str(response.url),
                }
                
    except aiohttp.ClientTimeout:
        return {
            "success": False,
            "error": f"Request timed out after {timeout} seconds",
            "status_code": None,
        }
    except aiohttp.ClientError as e:
        return {
            "success": False,
            "error": f"Request error: {str(e)}",
            "status_code": None,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
            "status_code": None,
        }


async def download_file(
    url: str,
    save_path: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 300,
    chunk_size: int = 8192,
) -> Dict:
    """
    下载文件
    
    Args:
        url: 文件URL
        save_path: 保存路径
        headers: 请求头（可选）
        timeout: 超时时间（秒）
        chunk_size: 分块大小
        
    Returns:
        包含success、path、size的字典
    """
    try:
        import httpx
    except ImportError:
        return {
            "success": False,
            "error": "httpx not installed. Install with: pip install httpx",
        }
    
    from pathlib import Path
    
    try:
        save_file = Path(save_path)
        save_file.parent.mkdir(parents=True, exist_ok=True)
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("GET", url, headers=headers) as response:
                response.raise_for_status()
                
                total_size = 0
                with open(save_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size):
                        f.write(chunk)
                        total_size += len(chunk)
        
        return {
            "success": True,
            "path": str(save_file.absolute()),
            "size": total_size,
            "url": url,
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }
