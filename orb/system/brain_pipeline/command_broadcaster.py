"""
命令广播器 (Command Broadcaster)

通过 WebSocket 将 BrainCommand 广播给外部订阅者
（ROS2 监控终端、MuJoCo 仿真终端等）。

端点: ws://localhost:8765
消息格式: {"type": "brain_command", "command": {...}, "timestamp": "..."}
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from orb.system.services.logger import LoggerMixin


class CommandBroadcaster(LoggerMixin):
    """
    命令广播器

    启动 WebSocket 服务器，将 BrainCommand 广播给所有连接的客户端。
    """

    def __init__(self, host: str = "localhost", port: int = 8765):
        self._host = host
        self._port = port
        self._clients: Set = set()
        self._server = None
        self._running = False
        self._message_count = 0

    @property
    def client_count(self) -> int:
        return len(self._clients)

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        """启动 WebSocket 服务器"""
        try:
            import websockets
        except ImportError:
            self.logger.warning(
                "websockets 未安装，命令广播器不可用。"
                "安装: pip install websockets"
            )
            return

        try:
            self._server = await websockets.serve(
                self._handle_client,
                self._host,
                self._port,
            )
            self._running = True
            self.logger.info(
                f"命令广播器已启动: ws://{self._host}:{self._port}"
            )
        except OSError as e:
            self.logger.warning(f"命令广播器启动失败 (端口 {self._port} 可能被占用): {e}")

    async def stop(self) -> None:
        """停止 WebSocket 服务器"""
        self._running = False
        # 关闭所有客户端连接
        if self._clients:
            await asyncio.gather(
                *[client.close() for client in self._clients],
                return_exceptions=True,
            )
            self._clients.clear()
        # 关闭服务器
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        self.logger.info("命令广播器已停止")

    async def _handle_client(self, websocket, path=None) -> None:
        """处理客户端连接"""
        self._clients.add(websocket)
        client_addr = websocket.remote_address
        self.logger.info(f"客户端连接: {client_addr} (共 {len(self._clients)} 个)")

        try:
            # 发送欢迎消息
            await websocket.send(json.dumps({
                "type": "welcome",
                "message": "OpenRoboBrain Command Broadcaster",
                "timestamp": datetime.now().isoformat(),
            }))
            # 保持连接直到断开
            async for message in websocket:
                # 客户端可以发送 ping/命令，暂时忽略
                pass
        except Exception:
            pass
        finally:
            self._clients.discard(websocket)
            self.logger.info(f"客户端断开: {client_addr} (剩余 {len(self._clients)} 个)")

    async def broadcast_command(self, command_data: Dict[str, Any]) -> int:
        """
        广播 BrainCommand 给所有客户端

        Args:
            command_data: BrainCommand 的字典表示

        Returns:
            成功发送的客户端数量
        """
        if not self._clients:
            return 0

        message = json.dumps({
            "type": "brain_command",
            "command": command_data,
            "timestamp": datetime.now().isoformat(),
            "seq": self._message_count,
        }, ensure_ascii=False)

        self._message_count += 1

        # 并行发送给所有客户端
        disconnected = set()
        sent_count = 0

        for client in self._clients.copy():
            try:
                await client.send(message)
                sent_count += 1
            except Exception:
                disconnected.add(client)

        # 清理断开的客户端
        self._clients -= disconnected

        return sent_count

    async def broadcast_status(self, status: Dict[str, Any]) -> None:
        """广播系统状态"""
        if not self._clients:
            return

        message = json.dumps({
            "type": "system_status",
            "status": status,
            "timestamp": datetime.now().isoformat(),
        }, ensure_ascii=False)

        disconnected = set()
        for client in self._clients.copy():
            try:
                await client.send(message)
            except Exception:
                disconnected.add(client)
        self._clients -= disconnected

    def get_stats(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "host": self._host,
            "port": self._port,
            "connected_clients": len(self._clients),
            "total_messages": self._message_count,
        }


# 全局单例
_broadcaster: Optional[CommandBroadcaster] = None


def get_broadcaster(host: str = "localhost", port: int = 8765) -> CommandBroadcaster:
    """获取全局广播器实例"""
    global _broadcaster
    if _broadcaster is None:
        _broadcaster = CommandBroadcaster(host=host, port=port)
    return _broadcaster
