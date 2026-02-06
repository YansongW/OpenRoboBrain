"""
OpenRoboBrain 三终端仿真启动脚本

一键启动三个终端窗口:
  1. CLI Chat          -- 自然语言交互
  2. ROS2 Monitor      -- 命令报文监控
  3. MuJoCo G1 Viewer  -- 机器人仿真可视化

运行: python scripts/start_sim.py

前置条件:
  - Ollama 已安装并运行 (ollama serve)
  - unitree_rl_gym 已克隆
  - pip install -r requirements-sim.txt
"""

import os
import subprocess
import sys
import time
from pathlib import Path


def check_ollama() -> bool:
    """检查 Ollama 是否运行"""
    try:
        import urllib.request
        req = urllib.request.Request("http://localhost:11434/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def check_unitree_rl_gym() -> str:
    """查找 unitree_rl_gym 路径"""
    env_path = os.environ.get("UNITREE_RL_GYM_PATH")
    if env_path and Path(env_path).exists():
        return env_path

    candidates = [
        Path.cwd() / "unitree_rl_gym",
        Path.cwd().parent / "unitree_rl_gym",
        Path.home() / "unitree_rl_gym",
    ]
    for p in candidates:
        if p.exists() and (p / "deploy").exists():
            return str(p)

    return ""


def main():
    print("=" * 55)
    print("  OpenRoboBrain MuJoCo G1 仿真 - 三终端启动")
    print("=" * 55)
    print()

    # 前置检查
    print("[1/3] 检查 Ollama...")
    if check_ollama():
        print("  OK: Ollama 正在运行")
    else:
        print("  警告: Ollama 未检测到")
        print("  系统将使用规则模式 (无 LLM)")
        print("  启动 Ollama: ollama serve")
    print()

    print("[2/3] 检查 unitree_rl_gym...")
    rl_gym_path = check_unitree_rl_gym()
    if rl_gym_path:
        print(f"  OK: {rl_gym_path}")
    else:
        print("  警告: unitree_rl_gym 未找到")
        print("  MuJoCo 终端将无法启动")
        print("  安装: git clone https://github.com/unitreerobotics/unitree_rl_gym.git")
    print()

    print("[3/3] 检查 Python 依赖...")
    missing = []
    for pkg in ["mujoco", "torch", "websockets"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"  警告: 缺少依赖: {', '.join(missing)}")
        print(f"  安装: pip install -r requirements-sim.txt")
    else:
        print("  OK: 所有依赖已安装")
    print()

    # 获取项目根目录
    project_root = Path(__file__).parent.parent
    python_exe = sys.executable

    # 构建启动命令
    print("启动三终端...")
    print("-" * 55)

    # 终端 1: CLI Chat
    cli_cmd = f'"{python_exe}" -m orb.cli -v'
    print(f"  [终端1] CLI Chat: {cli_cmd}")

    # 终端 2: ROS2 Monitor
    monitor_cmd = f'"{python_exe}" -m orb.tools.ros2_monitor'
    print(f"  [终端2] ROS2 Monitor: {monitor_cmd}")

    # 终端 3: MuJoCo G1
    sim_cmd = f'"{python_exe}" -m orb.sim.mujoco_g1'
    if rl_gym_path:
        sim_cmd += f' --rl-gym-path "{rl_gym_path}"'
    print(f"  [终端3] MuJoCo G1: {sim_cmd}")

    print()

    # Windows: 使用 start 命令打开新窗口
    if sys.platform == "win32":
        # 终端 2 先启动 (等待 CLI 的 WebSocket)
        subprocess.Popen(
            f'start "ROS2 Monitor" cmd /k "cd /d {project_root} && {monitor_cmd}"',
            shell=True,
        )
        time.sleep(0.5)

        # 终端 3 启动 MuJoCo
        if rl_gym_path and not missing:
            subprocess.Popen(
                f'start "MuJoCo G1" cmd /k "cd /d {project_root} && {sim_cmd}"',
                shell=True,
            )
        else:
            print("  [跳过] MuJoCo 终端 (缺少依赖或 unitree_rl_gym)")

        time.sleep(0.5)

        # 终端 1 最后启动 (在当前窗口或新窗口)
        subprocess.Popen(
            f'start "ORB CLI" cmd /k "cd /d {project_root} && {cli_cmd}"',
            shell=True,
        )
    else:
        # Linux/macOS: 尝试常见终端
        print("请手动在三个终端中分别运行以上命令")

    print()
    print("三终端已启动!")
    print("在 CLI 终端中输入自然语言指令与机器人交互。")
    print()
    print("使用流程:")
    print('  1. 在 CLI 终端输入: "去厨房"')
    print("  2. ROS2 Monitor 显示命令报文")
    print("  3. MuJoCo 窗口中 G1 开始行走")


if __name__ == "__main__":
    main()
