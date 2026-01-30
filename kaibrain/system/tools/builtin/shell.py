"""
Shell执行工具

提供安全的命令行执行能力。

借鉴 OpenClaw/Moltbot 的 exec 工具设计：
- 命令白名单/黑名单
- 超时控制
- 后台执行 (yieldMs, background)
- 资源限制
- 安全策略 (deny/allowlist/full)
"""

from __future__ import annotations

import asyncio
import os
import re
import shlex
import signal
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

from kaibrain.system.services.logger import LoggerMixin, get_logger

logger = get_logger(__name__)


class SecurityMode(Enum):
    """安全模式"""
    DENY = "deny"           # 拒绝所有危险命令
    ALLOWLIST = "allowlist" # 仅允许白名单命令
    FULL = "full"           # 允许所有命令（危险！）


@dataclass
class ShellSecurityConfig:
    """Shell 安全配置"""
    mode: SecurityMode = SecurityMode.DENY
    
    # 白名单命令（仅在 ALLOWLIST 模式下使用）
    allowed_commands: List[str] = field(default_factory=lambda: [
        "ls", "dir", "pwd", "cd", "cat", "head", "tail", "grep",
        "find", "echo", "date", "whoami", "hostname",
        "python", "python3", "pip", "pip3",
        "node", "npm", "npx",
        "git", "docker", "docker-compose",
        "ros2", "colcon",  # ROS2 相关
    ])
    
    # 黑名单命令（在 DENY 模式下拒绝）
    denied_commands: List[str] = field(default_factory=lambda: [
        "rm -rf /", "rm -rf /*", ":(){ :|:& };:",  # fork bomb
        "mkfs", "dd if=/dev/zero",
        "shutdown", "reboot", "poweroff", "halt",
        "> /dev/sda", "chmod -R 777 /",
        "curl | bash", "wget | sh",  # 管道执行
    ])
    
    # 黑名单模式（正则表达式）
    denied_patterns: List[str] = field(default_factory=lambda: [
        r"rm\s+-rf\s+/",
        r">\s*/dev/sd",
        r"mkfs\.",
        r"dd\s+if=/dev/zero",
        r"\|\s*(ba)?sh",  # 管道到 shell
        r"curl.*\|.*sh",
        r"wget.*\|.*sh",
    ])
    
    # 资源限制
    max_timeout: int = 1800          # 最大超时（秒）
    default_timeout: int = 60        # 默认超时
    max_output_size: int = 1024 * 1024  # 最大输出大小（1MB）
    
    # 后台执行
    yield_ms: int = 10000            # 自动后台化延迟（毫秒）
    max_background_processes: int = 10
    
    # 工作目录限制
    allowed_cwd_patterns: List[str] = field(default_factory=list)
    denied_cwd_patterns: List[str] = field(default_factory=lambda: [
        r"^/$",
        r"^/etc",
        r"^/sys",
        r"^/proc",
        r"^C:\\Windows",
    ])


class ShellExecutor(LoggerMixin):
    """
    安全的 Shell 执行器
    
    提供命令执行的安全控制和资源管理。
    """
    
    def __init__(self, config: Optional[ShellSecurityConfig] = None):
        """
        初始化 Shell 执行器
        
        Args:
            config: 安全配置
        """
        self._config = config or ShellSecurityConfig()
        self._background_processes: Dict[int, asyncio.subprocess.Process] = {}
        self._execution_count = 0
        self._denied_count = 0
        
    @property
    def config(self) -> ShellSecurityConfig:
        """安全配置"""
        return self._config
        
    @config.setter
    def config(self, value: ShellSecurityConfig) -> None:
        """设置安全配置"""
        self._config = value
        
    def _extract_command_name(self, command: str) -> str:
        """提取命令名"""
        # 处理管道和重定向
        parts = command.split("|")[0].split("&&")[0].split(";")[0]
        parts = parts.strip().split()
        if parts:
            # 处理 sudo/env 等前缀
            cmd = parts[0]
            if cmd in ["sudo", "env", "nohup", "nice"]:
                if len(parts) > 1:
                    return parts[1]
            return cmd
        return ""
        
    def _check_command_safety(self, command: str) -> tuple[bool, str]:
        """
        检查命令安全性
        
        Args:
            command: 命令
            
        Returns:
            (是否安全, 原因)
        """
        command_lower = command.lower().strip()
        
        # 检查黑名单命令
        for denied in self._config.denied_commands:
            if denied.lower() in command_lower:
                return False, f"命令包含危险内容: {denied}"
                
        # 检查黑名单模式
        for pattern in self._config.denied_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                return False, f"命令匹配危险模式: {pattern}"
                
        # DENY 模式：检查命令名
        if self._config.mode == SecurityMode.DENY:
            return True, ""
            
        # ALLOWLIST 模式：检查白名单
        if self._config.mode == SecurityMode.ALLOWLIST:
            cmd_name = self._extract_command_name(command)
            if cmd_name not in self._config.allowed_commands:
                return False, f"命令 '{cmd_name}' 不在白名单中"
            return True, ""
            
        # FULL 模式：允许所有
        return True, ""
        
    def _check_cwd_safety(self, cwd: Optional[str]) -> tuple[bool, str]:
        """
        检查工作目录安全性
        
        Args:
            cwd: 工作目录
            
        Returns:
            (是否安全, 原因)
        """
        if not cwd:
            return True, ""
            
        # 检查拒绝的目录
        for pattern in self._config.denied_cwd_patterns:
            if re.match(pattern, cwd, re.IGNORECASE):
                return False, f"工作目录被禁止: {cwd}"
                
        # 检查允许的目录（如果配置了）
        if self._config.allowed_cwd_patterns:
            for pattern in self._config.allowed_cwd_patterns:
                if re.match(pattern, cwd, re.IGNORECASE):
                    return True, ""
            return False, f"工作目录不在允许列表中: {cwd}"
            
        return True, ""
        
    async def execute(
        self,
        command: str,
        timeout: Optional[int] = None,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        background: bool = False,
        yield_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        执行 Shell 命令
        
        Args:
            command: 命令
            timeout: 超时时间（秒）
            cwd: 工作目录
            env: 环境变量
            background: 是否后台执行
            yield_ms: 自动后台化延迟（毫秒）
            
        Returns:
            执行结果
        """
        self._execution_count += 1
        
        # 安全检查
        is_safe, reason = self._check_command_safety(command)
        if not is_safe:
            self._denied_count += 1
            self.logger.warning(f"命令被拒绝: {command} - {reason}")
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Security: {reason}",
                "success": False,
                "denied": True,
            }
            
        cwd_safe, cwd_reason = self._check_cwd_safety(cwd)
        if not cwd_safe:
            self._denied_count += 1
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Security: {cwd_reason}",
                "success": False,
                "denied": True,
            }
            
        # 确定超时
        actual_timeout = min(
            timeout or self._config.default_timeout,
            self._config.max_timeout,
        )
        
        # 后台执行
        if background:
            return await self._execute_background(command, cwd, env)
            
        # 自动后台化
        actual_yield_ms = yield_ms if yield_ms is not None else self._config.yield_ms
        
        return await self._execute_foreground(
            command, actual_timeout, cwd, env, actual_yield_ms
        )
        
    async def _execute_foreground(
        self,
        command: str,
        timeout: int,
        cwd: Optional[str],
        env: Optional[Dict[str, str]],
        yield_ms: int,
    ) -> Dict[str, Any]:
        """前台执行命令"""
        # 合并环境变量
        exec_env = os.environ.copy()
        if env:
            exec_env.update(env)
            
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=exec_env,
            )
            
            # 使用 yield_ms 作为初始等待时间
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=yield_ms / 1000.0,
                )
                
                # 命令在 yield_ms 内完成
                stdout_text = stdout.decode("utf-8", errors="replace")
                stderr_text = stderr.decode("utf-8", errors="replace")
                
                # 截断过长的输出
                if len(stdout_text) > self._config.max_output_size:
                    stdout_text = stdout_text[:self._config.max_output_size] + "\n... (输出被截断)"
                if len(stderr_text) > self._config.max_output_size:
                    stderr_text = stderr_text[:self._config.max_output_size] + "\n... (输出被截断)"
                
                return {
                    "exit_code": proc.returncode,
                    "stdout": stdout_text.strip(),
                    "stderr": stderr_text.strip(),
                    "success": proc.returncode == 0,
                    "pid": proc.pid,
                }
                
            except asyncio.TimeoutError:
                # 命令未在 yield_ms 内完成，移到后台
                self._background_processes[proc.pid] = proc
                self.logger.info(f"命令移到后台执行: pid={proc.pid}")
                
                return {
                    "exit_code": None,
                    "stdout": "",
                    "stderr": "",
                    "success": True,
                    "pid": proc.pid,
                    "background": True,
                    "message": f"命令已移到后台执行 (pid: {proc.pid})",
                }
                
        except Exception as e:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
                "success": False,
            }
            
    async def _execute_background(
        self,
        command: str,
        cwd: Optional[str],
        env: Optional[Dict[str, str]],
    ) -> Dict[str, Any]:
        """后台执行命令"""
        # 检查后台进程数量限制
        if len(self._background_processes) >= self._config.max_background_processes:
            # 清理已完成的进程
            await self._cleanup_background_processes()
            
            if len(self._background_processes) >= self._config.max_background_processes:
                return {
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": f"后台进程数量已达上限 ({self._config.max_background_processes})",
                    "success": False,
                }
                
        exec_env = os.environ.copy()
        if env:
            exec_env.update(env)
            
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                cwd=cwd,
                env=exec_env,
                start_new_session=True,
            )
            
            self._background_processes[proc.pid] = proc
            
            return {
                "pid": proc.pid,
                "command": command,
                "success": True,
                "background": True,
            }
            
        except Exception as e:
            return {
                "pid": None,
                "command": command,
                "success": False,
                "error": str(e),
            }
            
    async def _cleanup_background_processes(self) -> int:
        """清理已完成的后台进程"""
        completed = []
        for pid, proc in self._background_processes.items():
            if proc.returncode is not None:
                completed.append(pid)
                
        for pid in completed:
            del self._background_processes[pid]
            
        return len(completed)
        
    async def kill_background(self, pid: int) -> bool:
        """
        终止后台进程
        
        Args:
            pid: 进程 ID
            
        Returns:
            是否成功
        """
        if pid in self._background_processes:
            proc = self._background_processes[pid]
            try:
                proc.terminate()
                await asyncio.sleep(0.5)
                if proc.returncode is None:
                    proc.kill()
                del self._background_processes[pid]
                return True
            except Exception as e:
                self.logger.error(f"终止进程失败: {e}")
        return False
        
    def list_background_processes(self) -> List[Dict[str, Any]]:
        """列出所有后台进程"""
        processes = []
        for pid, proc in self._background_processes.items():
            processes.append({
                "pid": pid,
                "running": proc.returncode is None,
                "returncode": proc.returncode,
            })
        return processes
        
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "execution_count": self._execution_count,
            "denied_count": self._denied_count,
            "background_processes": len(self._background_processes),
            "security_mode": self._config.mode.value,
        }


# 全局执行器实例
_default_executor: Optional[ShellExecutor] = None


def get_default_executor() -> ShellExecutor:
    """获取默认 Shell 执行器"""
    global _default_executor
    if _default_executor is None:
        _default_executor = ShellExecutor()
    return _default_executor


def set_default_executor(executor: ShellExecutor) -> None:
    """设置默认 Shell 执行器"""
    global _default_executor
    _default_executor = executor


# ============== 便捷函数 ==============

async def shell_execute(
    command: str,
    timeout: int = 30,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    background: bool = False,
    yield_ms: Optional[int] = None,
) -> Dict[str, Any]:
    """
    执行Shell命令并等待结果（使用安全执行器）
    
    Args:
        command: 要执行的命令
        timeout: 超时时间（秒），默认30秒
        cwd: 工作目录（可选）
        env: 环境变量（可选，会与当前环境合并）
        background: 是否后台执行
        yield_ms: 自动后台化延迟（毫秒）
        
    Returns:
        包含exit_code、stdout、stderr的字典
        
    Examples:
        >>> result = await shell_execute("echo hello")
        >>> print(result["stdout"])
        hello
    """
    executor = get_default_executor()
    return await executor.execute(
        command=command,
        timeout=timeout,
        cwd=cwd,
        env=env,
        background=background,
        yield_ms=yield_ms,
    )


async def shell_execute_background(
    command: str,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    在后台执行Shell命令（不等待结果）
    
    Args:
        command: 要执行的命令
        cwd: 工作目录（可选）
        env: 环境变量（可选）
        
    Returns:
        包含pid的字典
        
    Examples:
        >>> result = await shell_execute_background("sleep 100")
        >>> print(result["pid"])
        12345
    """
    executor = get_default_executor()
    return await executor.execute(
        command=command,
        cwd=cwd,
        env=env,
        background=True,
    )


async def shell_which(program: str) -> Optional[str]:
    """
    查找程序路径（类似which命令）
    
    Args:
        program: 程序名
        
    Returns:
        程序路径或None
    """
    if sys.platform == "win32":
        result = await shell_execute(f"where {program}", timeout=5)
    else:
        result = await shell_execute(f"which {program}", timeout=5)
    
    if result.get("success") and result.get("stdout"):
        return result["stdout"].split("\n")[0].strip()
    return None


async def shell_kill_background(pid: int) -> bool:
    """
    终止后台进程
    
    Args:
        pid: 进程 ID
        
    Returns:
        是否成功
    """
    executor = get_default_executor()
    return await executor.kill_background(pid)


def shell_list_background() -> List[Dict[str, Any]]:
    """
    列出所有后台进程
    
    Returns:
        后台进程列表
    """
    executor = get_default_executor()
    return executor.list_background_processes()


def shell_get_stats() -> Dict[str, Any]:
    """
    获取 Shell 执行统计
    
    Returns:
        统计信息
    """
    executor = get_default_executor()
    return executor.get_stats()


def create_shell_executor(
    mode: str = "deny",
    allowed_commands: Optional[List[str]] = None,
    denied_commands: Optional[List[str]] = None,
    denied_patterns: Optional[List[str]] = None,
    max_timeout: int = 1800,
    default_timeout: int = 60,
    yield_ms: int = 10000,
) -> ShellExecutor:
    """
    创建 Shell 执行器
    
    Args:
        mode: 安全模式 ("deny", "allowlist", "full")
        allowed_commands: 白名单命令
        denied_commands: 黑名单命令
        denied_patterns: 黑名单模式
        max_timeout: 最大超时
        default_timeout: 默认超时
        yield_ms: 自动后台化延迟
        
    Returns:
        ShellExecutor 实例
    """
    config = ShellSecurityConfig(
        mode=SecurityMode(mode),
        max_timeout=max_timeout,
        default_timeout=default_timeout,
        yield_ms=yield_ms,
    )
    
    if allowed_commands:
        config.allowed_commands = allowed_commands
    if denied_commands:
        config.denied_commands.extend(denied_commands)
    if denied_patterns:
        config.denied_patterns.extend(denied_patterns)
        
    return ShellExecutor(config)
