"""
MuJoCo G1 仿真终端

基于 unitree_rl_gym 的 deploy_mujoco.py 改造，
通过 WebSocket 接收 OpenRoboBrain 的 BrainCommand，
将高级命令映射为速度指令驱动 G1 行走策略。

前置条件:
  1. pip install mujoco torch numpy pyyaml websockets
  2. git clone https://github.com/unitreerobotics/unitree_rl_gym.git
  3. 设置环境变量 UNITREE_RL_GYM_PATH 或使用 --rl-gym-path 参数

运行: python -m orb.sim.mujoco_g1

基于 unitree_rl_gym (BSD 3-Clause License)
原始作者: Unitree Robotics
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np


# ANSI 颜色
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    CYAN = "\033[36m"
    RED = "\033[31m"
    BRIGHT_CYAN = "\033[96m"


# ============== 命令映射 ==============

# BrainCommand command_type -> 默认 velocity [vx, vy, wz]
# 这是 fallback 值，实际速度优先从 parameters 中提取
COMMAND_VELOCITY_MAP = {
    # 移动类 — 命令触发 policy 切换
    "forward":     [0.8, 0.0, 0.0],    # 前进
    "backward":    [-0.5, 0.0, 0.0],   # 后退
    "turn_left":   [0.2, 0.0, 0.8],    # 左转（边走边转）
    "turn_right":  [0.2, 0.0, -0.8],   # 右转
    "stop":        [0.0, 0.0, 0.0],    # 停止
    "navigate":    [0.8, 0.0, 0.0],    # 导航（默认前进）
    "move":        [0.8, 0.0, 0.0],    # 通用移动
    # 组合运动 — 同时前进+转弯
    "circle_left": [0.5, 0.0, 0.6],    # 左弧线/左圆圈
    "circle_right":[0.5, 0.0, -0.6],   # 右弧线/右圆圈
    "spin_left":   [0.0, 0.0, 1.5],    # 原地左旋
    "spin_right":  [0.0, 0.0, -1.5],   # 原地右旋
    # 任务类 — 到达后停止移动
    "grasp":       [0.0, 0.0, 0.0],
    "place":       [0.0, 0.0, 0.0],
    "pour":        [0.0, 0.0, 0.0],
    "patrol":      [0.4, 0.0, 0.2],    # 巡逻
    "clean":       [0.3, 0.0, 0.3],    # 清扫
}

# 速度描述词映射 — 从 parameters.speed 提取
SPEED_MULTIPLIER = {
    "very_slow": 0.3,
    "slow": 0.5,
    "normal": 1.0,
    "fast": 1.5,
    "very_fast": 2.0,
}


def get_gravity_orientation(quaternion):
    """从四元数计算重力方向 (来自 unitree_rl_gym)"""
    qw, qx, qy, qz = quaternion[0], quaternion[1], quaternion[2], quaternion[3]
    gx = 2 * (-qz * qx + qw * qy)
    gy = -2 * (qz * qy + qw * qx)
    gz = 1 - 2 * (qw * qw + qz * qz)
    return np.array([gx, gy, gz])


def pd_control(target_q, q, kp, target_dq, dq, kd):
    """PD 控制器 (来自 unitree_rl_gym)"""
    return (target_q - q) * kp + (target_dq - dq) * kd


# 各动作类型的默认持续时间（秒）
DEFAULT_DURATION = {
    "forward":    3.0,
    "backward":   2.5,
    "turn_left":  2.0,
    "turn_right": 2.0,
    "navigate":   4.0,
    "move":       3.0,
    "patrol":     5.0,
    "clean":      4.0,
    "stop":       0.0,   # 立即生效，无持续
    "circle_left":4.0,
    "circle_right":4.0,
    "spin_left":  5.0,
    "spin_right": 5.0,
    "grasp":      2.0,
    "place":      2.0,
    "pour":       3.0,
}


class WebSocketCommandReceiver:
    """
    WebSocket 命令接收器 (在后台线程运行)

    连接到 OpenRoboBrain 的命令广播器，
    将接收到的 BrainCommand 转换为速度指令。

    支持命令队列：多条命令按序执行，每条持续指定时间后自动切换下一条。
    stop 命令为紧急中断，清空队列并立即停止。
    """

    def __init__(self, host: str = "localhost", port: int = 8765):
        self._host = host
        self._port = port
        # 当前执行的速度
        self._current_cmd = np.array([0.0, 0.0, 0.0], dtype=np.float32)
        self._lock = threading.Lock()
        self._connected = False
        self._running = False
        self._last_command_type = "idle"
        self._command_count = 0
        # 命令队列: [(velocity_array, duration_seconds, cmd_type_label), ...]
        self._queue: List = []
        self._current_end_time: float = 0.0  # 当前命令结束的时间戳

    @property
    def current_cmd(self) -> np.ndarray:
        """获取当前速度指令（由主循环每帧调用）"""
        with self._lock:
            now = time.time()
            # 当前命令已到期，切换到下一条
            if self._current_end_time > 0 and now >= self._current_end_time:
                if self._queue:
                    vel, dur, label = self._queue.pop(0)
                    self._current_cmd = vel
                    self._current_end_time = now + dur if dur > 0 else 0.0
                    self._last_command_type = label
                    ts = datetime.now().strftime("%H:%M:%S")
                    print(
                        f"{C.DIM}[{ts}]{C.RESET} "
                        f"{C.YELLOW}NEXT{C.RESET}: {C.BOLD}{label.upper()}{C.RESET} "
                        f"-> vel=[{vel[0]:.2f}, {vel[1]:.2f}, {vel[2]:.2f}] "
                        f"({dur:.1f}s)"
                    )
                else:
                    # 队列执行完毕，自动停止
                    self._current_cmd = np.array([0.0, 0.0, 0.0], dtype=np.float32)
                    self._current_end_time = 0.0
                    self._last_command_type = "idle"
                    ts = datetime.now().strftime("%H:%M:%S")
                    print(
                        f"{C.DIM}[{ts}]{C.RESET} "
                        f"{C.GREEN}DONE{C.RESET}: 序列执行完毕，自动停止"
                    )
            return self._current_cmd.copy()

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def last_command_type(self) -> str:
        return self._last_command_type

    def start_background(self):
        """在后台线程启动 WebSocket 客户端"""
        self._running = True
        thread = threading.Thread(target=self._run_loop, daemon=True)
        thread.start()

    def stop(self):
        self._running = False

    def _run_loop(self):
        """后台事件循环"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._connect_loop())

    async def _connect_loop(self):
        """持续连接循环"""
        try:
            import websockets
        except ImportError:
            print(f"{C.RED}websockets 未安装{C.RESET}")
            return

        uri = f"ws://{self._host}:{self._port}"

        while self._running:
            try:
                async with websockets.connect(uri) as ws:
                    self._connected = True
                    print(f"{C.GREEN}WebSocket 已连接: {uri}{C.RESET}")

                    async for message in ws:
                        if not self._running:
                            break
                        self._process_message(message)

            except ConnectionRefusedError:
                self._connected = False
                if self._running:
                    await asyncio.sleep(2)
            except Exception as e:
                self._connected = False
                if self._running:
                    await asyncio.sleep(2)

    def _resolve_velocity(self, cmd_type: str, params: dict) -> list:
        """从命令类型和参数解析出速度向量"""
        base_vel = list(COMMAND_VELOCITY_MAP.get(cmd_type, [0.0, 0.0, 0.0]))

        # 精确速度参数覆盖
        if "vx" in params:
            base_vel[0] = float(params["vx"])
        if "vy" in params:
            base_vel[1] = float(params["vy"])
        if "wz" in params:
            base_vel[2] = float(params["wz"])

        # speed 描述词或数值乘数
        speed_param = params.get("speed", None)
        if speed_param is not None:
            if isinstance(speed_param, str):
                multiplier = SPEED_MULTIPLIER.get(speed_param, 1.0)
            else:
                multiplier = float(speed_param) if float(speed_param) > 0 else 1.0
            base_vel[0] *= multiplier
            base_vel[2] *= multiplier

        # 方向参数
        direction = params.get("direction", "")
        if direction == "left":
            base_vel[2] = abs(base_vel[2]) if base_vel[2] != 0 else 0.6
        elif direction == "right":
            base_vel[2] = -abs(base_vel[2]) if base_vel[2] != 0 else -0.6

        return base_vel

    def _process_message(self, raw: str):
        """
        处理 WebSocket 消息

        单条命令 → 立即执行（替换当前动作）
        多条命令同批到达 → 第一条立即执行，后续入队列按序执行
        stop 命令 → 清空队列，立即停止
        """
        try:
            data = json.loads(raw)
            if data.get("type") != "brain_command":
                return

            command = data.get("command", {})
            cmd_type = command.get("command_type", "")
            params = command.get("parameters", {})

            vel = self._resolve_velocity(cmd_type, params)

            # 持续时间: 优先从参数读取，否则使用默认值
            try:
                duration = float(params.get("duration", DEFAULT_DURATION.get(cmd_type, 3.0)))
            except (TypeError, ValueError):
                duration = DEFAULT_DURATION.get(cmd_type, 3.0)

            ts = datetime.now().strftime("%H:%M:%S")
            self._command_count += 1

            with self._lock:
                if cmd_type == "stop":
                    # 紧急停止：清空队列，立即停止
                    self._queue.clear()
                    self._current_cmd = np.array([0.0, 0.0, 0.0], dtype=np.float32)
                    self._current_end_time = 0.0
                    self._last_command_type = "stop"
                    print(
                        f"{C.DIM}[{ts}]{C.RESET} "
                        f"{C.RED}STOP{C.RESET}: 紧急停止，队列已清空"
                    )
                elif self._current_end_time == 0.0 and not self._queue:
                    # 当前空闲，立即执行
                    self._current_cmd = np.array(vel, dtype=np.float32)
                    self._current_end_time = time.time() + duration if duration > 0 else 0.0
                    self._last_command_type = cmd_type
                    print(
                        f"{C.DIM}[{ts}]{C.RESET} "
                        f"{C.CYAN}EXEC{C.RESET}: {C.BOLD}{cmd_type.upper()}{C.RESET} "
                        f"-> vel=[{vel[0]:.2f}, {vel[1]:.2f}, {vel[2]:.2f}] "
                        f"({duration:.1f}s)"
                    )
                else:
                    # 当前忙碌，入队列等待
                    self._queue.append((
                        np.array(vel, dtype=np.float32),
                        duration,
                        cmd_type,
                    ))
                    queue_len = len(self._queue)
                    print(
                        f"{C.DIM}[{ts}]{C.RESET} "
                        f"{C.YELLOW}QUEUE[{queue_len}]{C.RESET}: {cmd_type.upper()} "
                        f"-> vel=[{vel[0]:.2f}, {vel[1]:.2f}, {vel[2]:.2f}] "
                        f"({duration:.1f}s)"
                    )

        except Exception as e:
            pass


def find_rl_gym_path() -> Optional[Path]:
    """查找 unitree_rl_gym 路径"""
    # 1. 环境变量
    env_path = os.environ.get("UNITREE_RL_GYM_PATH")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p

    # 2. 常见位置
    candidates = [
        Path.cwd() / "unitree_rl_gym",
        Path.cwd().parent / "unitree_rl_gym",
        Path.home() / "unitree_rl_gym",
    ]
    for p in candidates:
        if p.exists() and (p / "deploy").exists():
            return p

    return None


def run_simulation(
    rl_gym_path: Path,
    config_name: str = "g1.yaml",
    ws_host: str = "localhost",
    ws_port: int = 8765,
    duration: float = 300.0,
):
    """
    运行 MuJoCo G1 仿真

    基于 unitree_rl_gym 的 deploy_mujoco.py 改造。
    """
    import mujoco
    import mujoco.viewer
    import torch
    import yaml

    # 加载配置
    config_path = rl_gym_path / "deploy" / "deploy_mujoco" / "configs" / config_name
    if not config_path.exists():
        print(f"{C.RED}配置文件不存在: {config_path}{C.RESET}")
        return

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    # 解析路径
    rl_gym_str = str(rl_gym_path)
    policy_path = config["policy_path"].replace("{LEGGED_GYM_ROOT_DIR}", rl_gym_str)
    xml_path = config["xml_path"].replace("{LEGGED_GYM_ROOT_DIR}", rl_gym_str)

    if not Path(policy_path).exists():
        print(f"{C.RED}策略文件不存在: {policy_path}{C.RESET}")
        print(f"请确认 unitree_rl_gym/deploy/pre_train/g1/ 目录下有 motion.pt")
        return

    if not Path(xml_path).exists():
        print(f"{C.RED}模型文件不存在: {xml_path}{C.RESET}")
        return

    # 加载参数
    simulation_dt = config["simulation_dt"]
    control_decimation = config["control_decimation"]
    kps = np.array(config["kps"], dtype=np.float32)
    kds = np.array(config["kds"], dtype=np.float32)
    default_angles = np.array(config["default_angles"], dtype=np.float32)
    ang_vel_scale = config["ang_vel_scale"]
    dof_pos_scale = config["dof_pos_scale"]
    dof_vel_scale = config["dof_vel_scale"]
    action_scale = config["action_scale"]
    cmd_scale = np.array(config["cmd_scale"], dtype=np.float32)
    num_actions = config["num_actions"]
    num_obs = config["num_obs"]
    # 初始化变量
    action = np.zeros(num_actions, dtype=np.float32)
    target_dof_pos = default_angles.copy()
    obs = np.zeros(num_obs, dtype=np.float32)
    counter = 0

    # 加载 MuJoCo 模型
    print(f"{C.CYAN}加载 G1 模型: {xml_path}{C.RESET}")
    m = mujoco.MjModel.from_xml_path(str(xml_path))
    d = mujoco.MjData(m)
    m.opt.timestep = simulation_dt

    # 加载策略
    print(f"{C.CYAN}加载策略: {policy_path}{C.RESET}")
    policy = torch.jit.load(policy_path)
    print(f"{C.GREEN}策略加载成功{C.RESET}")

    # 启动 WebSocket 接收器 (机器人默认站定，等待指令)
    receiver = WebSocketCommandReceiver(ws_host, ws_port)
    receiver.start_background()
    print(f"  初始状态: 站定等待指令")

    print(f"\n{C.BRIGHT_CYAN}{C.BOLD}MuJoCo G1 仿真已启动{C.RESET}")
    print(f"  WebSocket: ws://{ws_host}:{ws_port}")
    print(f"  仿真时长: {duration}s")
    print(f"  按 {C.YELLOW}ESC{C.RESET} 或关闭窗口退出\n")

    # 主仿真循环
    with mujoco.viewer.launch_passive(m, d) as viewer:
        start = time.time()
        while viewer.is_running() and time.time() - start < duration:
            step_start = time.time()

            # PD 控制
            tau = pd_control(
                target_dof_pos, d.qpos[7:], kps,
                np.zeros_like(kds), d.qvel[6:], kds,
            )
            d.ctrl[:] = tau

            # MuJoCo 步进
            mujoco.mj_step(m, d)
            counter += 1

            if counter % control_decimation == 0:
                # 获取当前速度指令 (来自 WebSocket 或默认)
                cmd = receiver.current_cmd

                # 构建观测
                qj = d.qpos[7:]
                dqj = d.qvel[6:]
                quat = d.qpos[3:7]
                omega = d.qvel[3:6]

                qj_scaled = (qj - default_angles) * dof_pos_scale
                dqj_scaled = dqj * dof_vel_scale
                gravity_orientation = get_gravity_orientation(quat)
                omega_scaled = omega * ang_vel_scale

                # 步态时钟
                period = 0.8
                count = counter * simulation_dt
                phase = count % period / period
                sin_phase = np.sin(2 * np.pi * phase)
                cos_phase = np.cos(2 * np.pi * phase)

                # 组装观测向量
                obs[:3] = omega_scaled
                obs[3:6] = gravity_orientation
                obs[6:9] = cmd * cmd_scale
                obs[9:9 + num_actions] = qj_scaled
                obs[9 + num_actions:9 + 2 * num_actions] = dqj_scaled
                obs[9 + 2 * num_actions:9 + 3 * num_actions] = action
                obs[9 + 3 * num_actions:9 + 3 * num_actions + 2] = np.array(
                    [sin_phase, cos_phase]
                )

                # 策略推理
                obs_tensor = torch.from_numpy(obs).unsqueeze(0)
                action = policy(obs_tensor).detach().numpy().squeeze()

                # 转换为目标关节角
                target_dof_pos = action * action_scale + default_angles

            # 同步渲染
            viewer.sync()

            # 简单时间控制
            time_until_next = m.opt.timestep - (time.time() - step_start)
            if time_until_next > 0:
                time.sleep(time_until_next)

    receiver.stop()
    print(f"\n{C.CYAN}仿真结束{C.RESET}")


def print_banner():
    print(f"""
{C.CYAN}{'=' * 55}{C.RESET}
{C.BRIGHT_CYAN}{C.BOLD}  OpenRoboBrain MuJoCo G1 Simulator{C.RESET}
{C.CYAN}{'=' * 55}{C.RESET}
  Robot: Unitree G1 (29-DOF Humanoid)
  Policy: unitree_rl_gym pre-trained locomotion
  Control: WebSocket <- OpenRoboBrain BrainCommand
{C.DIM}{'-' * 55}{C.RESET}
""")


def main():
    parser = argparse.ArgumentParser(
        description="OpenRoboBrain MuJoCo G1 Simulator"
    )
    parser.add_argument(
        "--rl-gym-path", type=str, default=None,
        help="unitree_rl_gym 仓库路径",
    )
    parser.add_argument(
        "--config", type=str, default="g1.yaml",
        help="部署配置文件名 (在 deploy/deploy_mujoco/configs/ 下)",
    )
    parser.add_argument("--ws-host", default="localhost", help="WebSocket 主机")
    parser.add_argument("--ws-port", type=int, default=8765, help="WebSocket 端口")
    parser.add_argument(
        "--duration", type=float, default=300.0,
        help="仿真时长 (秒)",
    )
    args = parser.parse_args()

    print_banner()

    # 查找 unitree_rl_gym 路径
    if args.rl_gym_path:
        rl_gym_path = Path(args.rl_gym_path)
    else:
        rl_gym_path = find_rl_gym_path()

    if not rl_gym_path or not rl_gym_path.exists():
        print(f"{C.RED}未找到 unitree_rl_gym 仓库{C.RESET}")
        print(f"\n请执行以下步骤:")
        print(f"  1. git clone https://github.com/unitreerobotics/unitree_rl_gym.git")
        print(f"  2. 设置环境变量: set UNITREE_RL_GYM_PATH=<路径>")
        print(f"  3. 或使用参数: --rl-gym-path <路径>")
        return

    print(f"  unitree_rl_gym: {C.GREEN}{rl_gym_path}{C.RESET}")

    # 添加到 Python path (unitree_rl_gym 的 deploy_mujoco 可能需要)
    sys.path.insert(0, str(rl_gym_path))

    try:
        run_simulation(
            rl_gym_path=rl_gym_path,
            config_name=args.config,
            ws_host=args.ws_host,
            ws_port=args.ws_port,
            duration=args.duration,
        )
    except ImportError as e:
        print(f"\n{C.RED}缺少依赖: {e}{C.RESET}")
        print(f"安装: pip install -r requirements-sim.txt")
    except Exception as e:
        print(f"\n{C.RED}仿真错误: {e}{C.RESET}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
