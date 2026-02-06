"""
ROS2 报文监控终端

连接 OpenRoboBrain 的 WebSocket 命令广播器，
以 ROS2 Topic 格式实时显示 BrainCommand。

运行: python -m orb.tools.ros2_monitor
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from typing import Optional


# ANSI 颜色
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_CYAN = "\033[96m"


# 命令类型到 ROS2 Topic 的映射
COMMAND_TO_TOPIC = {
    "navigate": "/brain/cmd_vel",
    "move": "/brain/cmd_vel",
    "stop": "/brain/emergency_stop",
    "grasp": "/brain/manipulation",
    "place": "/brain/manipulation",
    "pour": "/brain/manipulation",
    "turn": "/brain/cmd_vel",
    "patrol": "/brain/navigation/goal",
    "clean": "/brain/task/clean",
}


def format_command(command: dict) -> str:
    """将 BrainCommand 格式化为 ROS2 Topic 风格"""
    cmd_type = command.get("command_type", "unknown")
    params = command.get("parameters", {})
    priority = command.get("priority", "NORMAL")
    source = command.get("source_agent", "OpenRoboBrain")
    cmd_id = command.get("command_id", "")[:8]

    topic = COMMAND_TO_TOPIC.get(cmd_type, f"/brain/{cmd_type}")

    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]

    lines = []
    lines.append(f"{C.DIM}[{ts}]{C.RESET} {C.BRIGHT_CYAN}{C.BOLD}{topic}{C.RESET}")
    lines.append(f"  {C.YELLOW}command_type{C.RESET}: {C.BOLD}{cmd_type}{C.RESET}")

    if params:
        lines.append(f"  {C.YELLOW}parameters{C.RESET}:")
        for k, v in params.items():
            lines.append(f"    {C.DIM}{k}{C.RESET}: {v}")

    priority_color = C.RED if priority in ("EMERGENCY", "HIGH") else C.DIM
    lines.append(f"  {C.YELLOW}priority{C.RESET}: {priority_color}{priority}{C.RESET}")
    lines.append(f"  {C.YELLOW}source{C.RESET}: {source}")

    if cmd_id:
        lines.append(f"  {C.DIM}id: {cmd_id}...{C.RESET}")

    lines.append("")
    return "\n".join(lines)


def print_banner():
    print(f"""
{C.CYAN}{'=' * 55}{C.RESET}
{C.BRIGHT_CYAN}{C.BOLD}  OpenRoboBrain ROS2 Message Monitor{C.RESET}
{C.CYAN}{'=' * 55}{C.RESET}
  Listening on: {C.GREEN}ws://localhost:8765{C.RESET}
  Format: ROS2 Topic style
  Press {C.YELLOW}Ctrl+C{C.RESET} to exit
{C.DIM}{'-' * 55}{C.RESET}
""")


async def monitor(host: str = "localhost", port: int = 8765):
    """主监控循环"""
    try:
        import websockets
    except ImportError:
        print(f"{C.RED}错误: websockets 未安装{C.RESET}")
        print(f"安装: pip install websockets")
        return

    print_banner()

    uri = f"ws://{host}:{port}"
    msg_count = 0

    while True:
        try:
            print(f"{C.DIM}正在连接 {uri}...{C.RESET}")
            async with websockets.connect(uri) as ws:
                print(f"{C.GREEN}已连接!{C.RESET} 等待命令...\n")

                async for message in ws:
                    try:
                        data = json.loads(message)
                        msg_type = data.get("type", "")

                        if msg_type == "welcome":
                            print(f"{C.DIM}[服务器] {data.get('message', '')}{C.RESET}\n")

                        elif msg_type == "brain_command":
                            command = data.get("command", {})
                            msg_count += 1
                            seq = data.get("seq", "?")
                            print(f"{C.DIM}--- #{msg_count} (seq={seq}) ---{C.RESET}")
                            print(format_command(command))

                        elif msg_type == "system_status":
                            status = data.get("status", {})
                            print(f"{C.DIM}[系统状态] {json.dumps(status, ensure_ascii=False)}{C.RESET}\n")

                    except json.JSONDecodeError:
                        print(f"{C.DIM}[RAW] {message[:200]}{C.RESET}")

        except ConnectionRefusedError:
            print(f"{C.YELLOW}连接被拒绝，{3}秒后重试...{C.RESET}")
            print(f"{C.DIM}请确保 OpenRoboBrain CLI 已启动{C.RESET}")
            await asyncio.sleep(3)
        except Exception as e:
            print(f"{C.YELLOW}连接断开: {e}，{3}秒后重连...{C.RESET}")
            await asyncio.sleep(3)


def main():
    """入口"""
    import argparse
    parser = argparse.ArgumentParser(description="OpenRoboBrain ROS2 Message Monitor")
    parser.add_argument("--host", default="localhost", help="WebSocket 主机")
    parser.add_argument("--port", type=int, default=8765, help="WebSocket 端口")
    args = parser.parse_args()

    try:
        asyncio.run(monitor(args.host, args.port))
    except KeyboardInterrupt:
        print(f"\n{C.CYAN}监控已退出{C.RESET}")


if __name__ == "__main__":
    main()
