"""
KaiBrain 命令行界面

提供REPL交互界面，支持自然语言输入，
异步显示chat响应和ROS2控制命令。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import datetime
from typing import Optional

from kaibrain.core import KaiBrain, ProcessResult
from kaibrain.system.services.logger import setup_logging, Layer


# ANSI颜色代码
class Colors:
    """终端颜色"""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    
    # 前景色
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    
    # 高亮
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"


def colorize(text: str, color: str) -> str:
    """给文本添加颜色"""
    return f"{color}{text}{Colors.RESET}"


class KaiBrainCLI:
    """
    KaiBrain 命令行界面
    
    功能：
    - REPL交互循环
    - 显示chat响应
    - 显示ROS2控制命令
    - 支持verbose详细模式
    """
    
    def __init__(
        self,
        verbose: bool = False,
        mock_ros2: bool = True,
    ):
        """
        初始化CLI
        
        Args:
            verbose: 是否显示详细信息
            mock_ros2: 是否使用模拟ROS2
        """
        self.verbose = verbose
        self.mock_ros2 = mock_ros2
        self.brain: Optional[KaiBrain] = None
        self._running = False
    
    async def initialize(self) -> bool:
        """
        初始化KaiBrain
        
        Returns:
            是否成功
        """
        try:
            print(colorize("正在初始化 KaiBrain...", Colors.CYAN))
            
            # 创建并初始化KaiBrain
            self.brain = KaiBrain(mock_ros2=self.mock_ros2)
            await self.brain.initialize()
            
            print(colorize("✓ KaiBrain 初始化完成", Colors.GREEN))
            return True
            
        except Exception as e:
            print(colorize(f"✗ 初始化失败: {e}", Colors.RED))
            return False
    
    async def shutdown(self) -> None:
        """关闭KaiBrain"""
        if self.brain:
            print(colorize("\n正在关闭 KaiBrain...", Colors.CYAN))
            await self.brain.stop()
            print(colorize("✓ 已安全关闭", Colors.GREEN))
    
    def print_banner(self) -> None:
        """打印欢迎横幅"""
        banner = f"""
{colorize("=" * 60, Colors.CYAN)}
{colorize("  KaiBrain - 机器人智能大脑系统", Colors.BRIGHT_CYAN + Colors.BOLD)}
{colorize("=" * 60, Colors.CYAN)}

  命令：
    {colorize("/help", Colors.YELLOW)}     - 显示帮助
    {colorize("/verbose", Colors.YELLOW)}  - 切换详细模式 (当前: {colorize("开" if self.verbose else "关", Colors.GREEN if self.verbose else Colors.RED)})
    {colorize("/status", Colors.YELLOW)}   - 显示系统状态
    {colorize("/quit", Colors.YELLOW)}     - 退出程序

  直接输入自然语言与机器人交互。
{colorize("-" * 60, Colors.DIM)}
"""
        print(banner)
    
    def print_help(self) -> None:
        """打印帮助信息"""
        help_text = f"""
{colorize("KaiBrain CLI 帮助", Colors.BRIGHT_CYAN + Colors.BOLD)}

{colorize("命令:", Colors.YELLOW)}
  /help      显示此帮助信息
  /verbose   切换详细模式（显示trace_id、执行时间等）
  /status    显示系统状态
  /clear     清空屏幕
  /quit      退出程序

{colorize("使用示例:", Colors.YELLOW)}
  > 帮我倒杯水
  > 去厨房拿一个苹果
  > 你好，你能做什么？
  > 停下来
"""
        print(help_text)
    
    def print_status(self) -> None:
        """打印系统状态"""
        if not self.brain:
            print(colorize("系统未初始化", Colors.RED))
            return
        
        status = f"""
{colorize("系统状态", Colors.BRIGHT_CYAN + Colors.BOLD)}
{colorize("-" * 40, Colors.DIM)}
  运行状态: {colorize("运行中" if self.brain.is_running else "已停止", Colors.GREEN if self.brain.is_running else Colors.RED)}
  ROS2模式: {colorize("模拟" if self.mock_ros2 else "真实", Colors.YELLOW if self.mock_ros2 else Colors.GREEN)}
  详细模式: {colorize("开启" if self.verbose else "关闭", Colors.GREEN if self.verbose else Colors.DIM)}
"""
        
        # 行为执行器统计
        if self.brain.behavior_executor:
            stats = self.brain.behavior_executor.get_stats_dict()
            status += f"""
{colorize("行为执行器统计:", Colors.YELLOW)}
  总执行次数: {stats.get('total_executions', 0)}
  成功次数:   {stats.get('successful_executions', 0)}
  失败次数:   {stats.get('failed_executions', 0)}
  成功率:     {stats.get('success_rate', 0):.1%}
  平均耗时:   {stats.get('average_duration_ms', 0):.1f}ms
"""
        
        print(status)
    
    def display_result(self, result: ProcessResult) -> None:
        """
        显示处理结果
        
        Args:
            result: 处理结果
        """
        print()
        
        # 详细模式：显示trace_id和执行时间
        if self.verbose:
            print(colorize(f"[Trace: {result.trace_id}]", Colors.DIM))
            print(colorize(f"[耗时: {result.execution_time_ms:.1f}ms]", Colors.DIM))
            if result.behavior_result:
                print(colorize(
                    f"[行为: {result.behavior_result.behavior_name}]",
                    Colors.DIM
                ))
            print()
        
        # 显示错误（如果有）
        if not result.success:
            print(colorize(f"✗ 错误: {result.error}", Colors.RED))
            return
        
        # 显示chat响应
        if result.chat_response:
            print(colorize("🤖 KaiBrain:", Colors.BRIGHT_GREEN + Colors.BOLD))
            print(f"   {result.chat_response}")
            print()
        
        # 显示ROS2命令
        if result.ros2_commands:
            print(colorize("📡 ROS2 控制命令:", Colors.BRIGHT_YELLOW + Colors.BOLD))
            for i, cmd in enumerate(result.ros2_commands, 1):
                cmd_type = cmd.get("command_type", "unknown")
                params = cmd.get("parameters", {})
                
                # 格式化命令显示
                print(colorize(f"   [{i}] ", Colors.YELLOW) + 
                      colorize(cmd_type, Colors.BRIGHT_CYAN))
                
                if params:
                    for key, value in params.items():
                        print(colorize(f"       └─ {key}: ", Colors.DIM) + 
                              colorize(str(value), Colors.WHITE))
            print()
        elif self.verbose:
            print(colorize("   (无ROS2命令)", Colors.DIM))
            print()
        
        # 详细模式：显示更多行为结果细节
        if self.verbose and result.behavior_result:
            br = result.behavior_result
            if br.data:
                # 显示额外数据
                if "intent" in br.data:
                    print(colorize(f"[意图: {br.data['intent']}]", Colors.DIM))
                if "reasoning_steps" in br.data:
                    steps = br.data["reasoning_steps"]
                    if steps:
                        print(colorize("[推理步骤]:", Colors.DIM))
                        for step in steps:
                            print(colorize(f"  - {step}", Colors.DIM))
                if "confidence" in br.data:
                    print(colorize(f"[置信度: {br.data['confidence']:.2f}]", Colors.DIM))
            print()
    
    async def process_input(self, user_input: str) -> bool:
        """
        处理用户输入
        
        Args:
            user_input: 用户输入
            
        Returns:
            是否继续运行
        """
        user_input = user_input.strip()
        
        if not user_input:
            return True
        
        # 处理命令
        if user_input.startswith("/"):
            cmd = user_input.lower()
            
            if cmd in ("/quit", "/exit", "/q"):
                return False
            
            elif cmd in ("/help", "/h", "/?"):
                self.print_help()
                return True
            
            elif cmd in ("/verbose", "/v"):
                self.verbose = not self.verbose
                mode = colorize("开启", Colors.GREEN) if self.verbose else colorize("关闭", Colors.RED)
                print(f"详细模式已{mode}")
                return True
            
            elif cmd in ("/status", "/s"):
                self.print_status()
                return True
            
            elif cmd in ("/clear", "/cls"):
                print("\033[2J\033[H")  # 清屏
                self.print_banner()
                return True
            
            else:
                print(colorize(f"未知命令: {user_input}", Colors.YELLOW))
                print("输入 /help 查看可用命令")
                return True
        
        # 处理自然语言输入
        if not self.brain:
            print(colorize("系统未初始化", Colors.RED))
            return True
        
        try:
            # 显示处理中提示
            print(colorize("处理中...", Colors.DIM), end="\r")
            
            # 调用KaiBrain处理
            result = await self.brain.process(user_input)
            
            # 清除"处理中"提示
            print(" " * 20, end="\r")
            
            # 显示结果
            self.display_result(result)
            
        except KeyboardInterrupt:
            print(colorize("\n已取消", Colors.YELLOW))
        except Exception as e:
            print(colorize(f"处理错误: {e}", Colors.RED))
            if self.verbose:
                import traceback
                traceback.print_exc()
        
        return True
    
    async def run(self) -> None:
        """运行REPL循环"""
        # 初始化
        if not await self.initialize():
            return
        
        self._running = True
        self.print_banner()
        
        try:
            while self._running:
                try:
                    # 显示提示符
                    prompt = colorize("> ", Colors.BRIGHT_GREEN + Colors.BOLD)
                    
                    # 读取输入（同步读取，但在事件循环中运行）
                    user_input = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: input(prompt)
                    )
                    
                    # 处理输入
                    self._running = await self.process_input(user_input)
                    
                except KeyboardInterrupt:
                    print(colorize("\n使用 /quit 退出，或按 Ctrl+C 再次退出", Colors.YELLOW))
                    try:
                        await asyncio.sleep(0.5)
                    except KeyboardInterrupt:
                        print()
                        break
                except EOFError:
                    # 处理EOF（如管道输入结束）
                    break
                    
        finally:
            await self.shutdown()


async def main_async(args: argparse.Namespace) -> int:
    """
    异步主函数
    
    Args:
        args: 命令行参数
        
    Returns:
        退出码
    """
    # 设置日志
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logging(level=log_level, use_enhanced_format=args.verbose)
    
    # 创建并运行CLI
    cli = KaiBrainCLI(
        verbose=args.verbose,
        mock_ros2=not args.real_ros2,
    )
    
    try:
        await cli.run()
        return 0
    except Exception as e:
        print(colorize(f"运行错误: {e}", Colors.RED))
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


def main() -> int:
    """
    主函数
    
    Returns:
        退出码
    """
    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description="KaiBrain - 机器人智能大脑系统 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s                    # 启动CLI（默认模拟ROS2）
  %(prog)s -v                 # 启动CLI，详细模式
  %(prog)s --real-ros2        # 启动CLI，连接真实ROS2
  %(prog)s -e "帮我倒杯水"     # 执行单条命令

更多信息请访问: https://github.com/your-repo/kaibrain
        """,
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="显示详细信息（trace_id、执行时间等）",
    )
    
    parser.add_argument(
        "--real-ros2",
        action="store_true",
        help="连接真实ROS2（默认使用模拟模式）",
    )
    
    parser.add_argument(
        "-e", "--execute",
        type=str,
        metavar="COMMAND",
        help="执行单条命令后退出",
    )
    
    args = parser.parse_args()
    
    # 如果指定了单条命令
    if args.execute:
        return asyncio.run(execute_single(args))
    
    # 运行REPL
    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print(colorize("\n再见！", Colors.CYAN))
        return 0


async def execute_single(args: argparse.Namespace) -> int:
    """
    执行单条命令
    
    Args:
        args: 命令行参数
        
    Returns:
        退出码
    """
    # 设置日志
    log_level = "DEBUG" if args.verbose else "WARNING"
    setup_logging(level=log_level, use_enhanced_format=args.verbose)
    
    cli = KaiBrainCLI(
        verbose=args.verbose,
        mock_ros2=not args.real_ros2,
    )
    
    try:
        # 初始化
        if not await cli.initialize():
            return 1
        
        # 执行命令
        result = await cli.brain.process(args.execute)
        
        # 显示结果
        cli.display_result(result)
        
        # 关闭
        await cli.shutdown()
        
        return 0 if result.success else 1
        
    except Exception as e:
        print(colorize(f"执行错误: {e}", Colors.RED))
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
