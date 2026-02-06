"""
OpenRoboBrain 命令行界面

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

from orb.core import OpenRoboBrain, ProcessResult
from orb.system.services.logger import setup_logging, Layer


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


class ORBCLI:
    """
    OpenRoboBrain 命令行界面
    
    功能:
    - REPL交互循环
    - 显示chat响应和ROS2控制命令
    - /memory 查看记忆状态
    - /stats 显示系统统计
    - 支持verbose详细模式
    """
    
    def __init__(
        self,
        verbose: bool = False,
        mock_ros2: bool = True,
    ):
        self.verbose = verbose
        self.mock_ros2 = mock_ros2
        self.brain: Optional[OpenRoboBrain] = None
        self._running = False
    
    async def initialize(self) -> bool:
        """初始化OpenRoboBrain"""
        try:
            print(colorize("正在初始化 OpenRoboBrain...", Colors.CYAN))
            
            self.brain = OpenRoboBrain(mock_ros2=self.mock_ros2)
            await self.brain.initialize()
            await self.brain.start()
            
            mode = "LLM" if self.brain.llm_available else "规则"
            print(colorize(f"  OpenRoboBrain 初始化完成 (模式: {mode})", Colors.GREEN))
            return True
            
        except Exception as e:
            print(colorize(f"  初始化失败: {e}", Colors.RED))
            return False
    
    async def shutdown(self) -> None:
        """关闭OpenRoboBrain"""
        if self.brain:
            print(colorize("\n正在关闭 OpenRoboBrain...", Colors.CYAN))
            await self.brain.stop()
            print(colorize("  已安全关闭", Colors.GREEN))
    
    def print_banner(self) -> None:
        """打印欢迎横幅"""
        mode = "LLM" if (self.brain and self.brain.llm_available) else "规则"
        banner = f"""
{colorize("=" * 60, Colors.CYAN)}
{colorize("  OpenRoboBrain (ORB) - 机器人智能大脑系统", Colors.BRIGHT_CYAN + Colors.BOLD)}
{colorize("=" * 60, Colors.CYAN)}

  处理模式: {colorize(mode, Colors.GREEN if mode == "LLM" else Colors.YELLOW)}
  
  命令:
    {colorize("/help", Colors.YELLOW)}     - 显示帮助
    {colorize("/memory", Colors.YELLOW)}   - 查看记忆状态
    {colorize("/stats", Colors.YELLOW)}    - 系统统计信息
    {colorize("/verbose", Colors.YELLOW)}  - 切换详细模式 (当前: {colorize("开" if self.verbose else "关", Colors.GREEN if self.verbose else Colors.RED)})
    {colorize("/quit", Colors.YELLOW)}     - 退出程序

  直接输入自然语言与机器人交互。
{colorize("-" * 60, Colors.DIM)}
"""
        print(banner)
    
    def print_help(self) -> None:
        """打印帮助信息"""
        help_text = f"""
{colorize("OpenRoboBrain CLI 帮助", Colors.BRIGHT_CYAN + Colors.BOLD)}

{colorize("命令:", Colors.YELLOW)}
  /help      显示此帮助信息
  /memory    查看记忆系统状态和最近记忆
  /stats     显示系统统计（AgentLoop、Memory、Compaction）
  /status    显示运行状态
  /verbose   切换详细模式（显示trace_id、执行时间等）
  /clear     清空屏幕
  /quit      退出程序

{colorize("使用示例:", Colors.YELLOW)}
  > 帮我倒杯水
  > 去厨房拿一个苹果
  > 你好，你能做什么？
  > 停下来
"""
        print(help_text)

    def print_memory(self) -> None:
        """打印记忆系统状态"""
        if not self.brain or not self.brain.memory_stream:
            print(colorize("记忆系统未初始化", Colors.RED))
            return
        
        stream = self.brain.memory_stream
        stats = stream.get_stats()
        
        print(f"\n{colorize('记忆系统状态', Colors.BRIGHT_CYAN + Colors.BOLD)}")
        print(colorize("-" * 40, Colors.DIM))
        print(f"  总记忆数:     {stats['total_memories']}")
        print(f"  活跃记忆:     {stats['active_memories']}")
        print(f"  平均重要性:   {stats['avg_importance']:.1f}/10")
        print(f"  平均强度:     {stats['avg_strength']:.1f}")
        print(f"  总添加:       {stats['total_added']}")
        print(f"  总检索:       {stats['total_retrieved']}")
        
        # 类型统计
        type_counts = stats.get('type_counts', {})
        if any(v > 0 for v in type_counts.values()):
            print(f"\n  {colorize('按类型:', Colors.YELLOW)}")
            for t, c in type_counts.items():
                if c > 0:
                    print(f"    {t}: {c}")
        
        # 最近记忆
        memories = stream.get_all()
        if memories:
            recent = sorted(memories, key=lambda m: m.created_at, reverse=True)[:5]
            print(f"\n  {colorize('最近 5 条记忆:', Colors.YELLOW)}")
            for mem in recent:
                ts = datetime.fromtimestamp(mem.created_at).strftime("%H:%M:%S")
                imp_bar = colorize("*" * int(mem.importance), Colors.BRIGHT_YELLOW)
                print(f"    [{ts}] {mem.description[:60]} {imp_bar}")
        
        print()

    def print_stats(self) -> None:
        """打印系统统计信息"""
        if not self.brain:
            print(colorize("系统未初始化", Colors.RED))
            return
        
        print(f"\n{colorize('系统统计', Colors.BRIGHT_CYAN + Colors.BOLD)}")
        print(colorize("-" * 40, Colors.DIM))
        
        # 基础状态
        mode = "LLM" if self.brain.llm_available else "规则"
        print(f"  运行状态: {colorize('运行中' if self.brain.is_running else '已停止', Colors.GREEN if self.brain.is_running else Colors.RED)}")
        print(f"  处理模式: {colorize(mode, Colors.GREEN if mode == 'LLM' else Colors.YELLOW)}")
        print(f"  ROS2模式: {colorize('模拟' if self.mock_ros2 else '真实', Colors.YELLOW if self.mock_ros2 else Colors.GREEN)}")
        
        # LLM 信息
        if self.brain.llm_available and self.brain.llm:
            print(f"  LLM 模型: {colorize(self.brain.llm.model, Colors.BRIGHT_CYAN)}")
        
        # AgentLoop 统计
        if self.brain.agent_loop:
            loop_stats = self.brain.agent_loop.get_stats()
            print(f"\n  {colorize('AgentLoop:', Colors.YELLOW)}")
            print(f"    总运行次数: {loop_stats['total_runs']}")
            print(f"    成功次数:   {loop_stats['success_runs']}")
            print(f"    总 tokens:  {loop_stats['total_tokens']}")
        
        # Memory 统计
        if self.brain.memory_stream:
            mem_stats = self.brain.memory_stream.get_stats()
            print(f"\n  {colorize('Memory:', Colors.YELLOW)}")
            print(f"    记忆总数: {mem_stats['total_memories']}")
            print(f"    检索次数: {mem_stats['total_retrieved']}")
        
        # 行为执行器统计
        if self.brain.behavior_executor:
            try:
                be_stats = self.brain.behavior_executor.get_stats_dict()
                print(f"\n  {colorize('BehaviorExecutor:', Colors.YELLOW)}")
                print(f"    总执行: {be_stats.get('total_executions', 0)}")
                print(f"    成功率: {be_stats.get('success_rate', 0):.1%}")
            except Exception:
                pass
        
        print()
    
    def print_status(self) -> None:
        """打印简要状态"""
        self.print_stats()
    
    def display_result(self, result: ProcessResult) -> None:
        """显示处理结果"""
        print()
        
        # 详细模式：显示trace_id、执行时间、模式
        if self.verbose:
            print(colorize(
                f"[Trace: {result.trace_id}] "
                f"[模式: {result.mode}] "
                f"[耗时: {result.execution_time_ms:.1f}ms]",
                Colors.DIM,
            ))
            if result.metadata:
                if "tokens_used" in result.metadata:
                    print(colorize(f"[Tokens: {result.metadata['tokens_used']}]", Colors.DIM))
            print()
        
        # 显示错误
        if not result.success:
            print(colorize(f"  错误: {result.error}", Colors.RED))
            return
        
        # 显示chat响应
        if result.chat_response:
            print(colorize("  OpenRoboBrain:", Colors.BRIGHT_GREEN + Colors.BOLD))
            print(f"   {result.chat_response}")
            print()
        
        # 显示ROS2命令
        if result.ros2_commands:
            print(colorize("  ROS2 控制命令:", Colors.BRIGHT_YELLOW + Colors.BOLD))
            for i, cmd in enumerate(result.ros2_commands, 1):
                if hasattr(cmd, 'command_type'):
                    cmd_type = cmd.command_type
                    params = cmd.parameters if hasattr(cmd, 'parameters') else {}
                elif isinstance(cmd, dict):
                    cmd_type = cmd.get("command_type", "unknown")
                    params = cmd.get("parameters", {})
                else:
                    cmd_type = str(cmd)
                    params = {}
                
                print(colorize(f"   [{i}] ", Colors.YELLOW) + 
                      colorize(cmd_type, Colors.BRIGHT_CYAN))
                
                if params:
                    for key, value in (params.items() if isinstance(params, dict) else []):
                        print(colorize(f"       {key}: ", Colors.DIM) + 
                              colorize(str(value), Colors.WHITE))
            print()
    
    async def process_input(self, user_input: str) -> bool:
        """处理用户输入，返回是否继续运行"""
        user_input = user_input.strip()
        
        if not user_input:
            return True
        
        # 处理命令
        if user_input.startswith("/"):
            cmd = user_input.lower().split()[0]
            
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
            
            elif cmd in ("/memory", "/mem", "/m"):
                self.print_memory()
                return True
            
            elif cmd in ("/stats",):
                self.print_stats()
                return True
            
            elif cmd in ("/clear", "/cls"):
                print("\033[2J\033[H")
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
            print(colorize("处理中...", Colors.DIM), end="\r")
            result = await self.brain.process(user_input)
            print(" " * 20, end="\r")
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
        if not await self.initialize():
            return
        
        self._running = True
        self.print_banner()
        
        try:
            while self._running:
                try:
                    prompt = colorize("> ", Colors.BRIGHT_GREEN + Colors.BOLD)
                    user_input = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: input(prompt)
                    )
                    self._running = await self.process_input(user_input)
                    
                except KeyboardInterrupt:
                    print(colorize("\n使用 /quit 退出，或按 Ctrl+C 再次退出", Colors.YELLOW))
                    try:
                        await asyncio.sleep(0.5)
                    except KeyboardInterrupt:
                        print()
                        break
                except EOFError:
                    break
                    
        finally:
            await self.shutdown()


async def main_async(args: argparse.Namespace) -> int:
    """异步主函数"""
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logging(level=log_level, use_enhanced_format=args.verbose)
    
    cli = ORBCLI(
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
    """主函数"""
    parser = argparse.ArgumentParser(
        description="OpenRoboBrain (ORB) - 机器人智能大脑系统 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s                    # 启动CLI（默认模拟ROS2）
  %(prog)s -v                 # 启动CLI，详细模式
  %(prog)s --real-ros2        # 启动CLI，连接真实ROS2
  %(prog)s -e "帮我倒杯水"     # 执行单条命令
        """,
    )
    
    parser.add_argument("-v", "--verbose", action="store_true", help="显示详细信息")
    parser.add_argument("--real-ros2", action="store_true", help="连接真实ROS2")
    parser.add_argument("-e", "--execute", type=str, metavar="COMMAND", help="执行单条命令后退出")
    
    args = parser.parse_args()
    
    if args.execute:
        return asyncio.run(execute_single(args))
    
    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print(colorize("\n再见！", Colors.CYAN))
        return 0


async def execute_single(args: argparse.Namespace) -> int:
    """执行单条命令"""
    log_level = "DEBUG" if args.verbose else "WARNING"
    setup_logging(level=log_level, use_enhanced_format=args.verbose)
    
    cli = ORBCLI(verbose=args.verbose, mock_ros2=not args.real_ros2)
    
    try:
        if not await cli.initialize():
            return 1
        
        result = await cli.brain.process(args.execute)
        cli.display_result(result)
        await cli.shutdown()
        
        return 0 if result.success else 1
        
    except Exception as e:
        print(colorize(f"执行错误: {e}", Colors.RED))
        return 1


if __name__ == "__main__":
    sys.exit(main())
