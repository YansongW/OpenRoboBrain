"""
OpenRoboBrain 核心入口

提供系统的统一入口和生命周期管理。
支持用户自然语言输入，异步返回对话(chat)和ROS2控制消息。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from uuid import uuid4

from orb.system.services.config_center import ConfigCenter
from orb.system.services.logger import get_logger

if TYPE_CHECKING:
    from orb.agent.super.super_agent import SuperAgent
    from orb.system.brain_pipeline.message_bus import MessageBus
    from orb.system.brain_pipeline.brain_cerebellum_bridge import (
        BrainCerebellumBridge,
        BrainCommand,
    )
    from orb.behavior.executor import BehaviorExecutor
    from orb.behavior.base import BehaviorResult

logger = get_logger(__name__)


@dataclass
class ProcessResult:
    """
    处理结果
    
    包含对话响应和ROS2命令，实现双输出。
    """
    trace_id: str                              # 请求追踪ID
    chat_response: str                         # 对话输出
    ros2_commands: List["BrainCommand"] = field(default_factory=list)  # ROS2命令列表
    behavior_name: str = ""                    # 执行的行为名称
    behavior_result: Optional["BehaviorResult"] = None  # 行为执行结果
    success: bool = True                       # 是否成功
    error: Optional[str] = None                # 错误信息
    execution_time_ms: float = 0.0             # 执行时间(毫秒)
    metadata: Dict[str, Any] = field(default_factory=dict)  # 元数据
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "trace_id": self.trace_id,
            "chat_response": self.chat_response,
            "ros2_commands": [cmd.to_dict() if hasattr(cmd, 'to_dict') else str(cmd) for cmd in self.ros2_commands],
            "behavior_name": self.behavior_name,
            "success": self.success,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "metadata": self.metadata,
        }


class OpenRoboBrain:
    """
    OpenRoboBrain 系统主类
    
    负责整个系统的初始化、启动和关闭。
    提供统一的process()入口，接收自然语言输入，返回对话和ROS2命令。
    """
    
    def __init__(
        self,
        config_path: Optional[str] = None,
        mock_ros2: bool = True,
    ):
        """
        初始化 OpenRoboBrain 系统
        
        Args:
            config_path: 配置文件路径，默认使用 configs/system.yaml
            mock_ros2: 是否使用模拟ROS2（默认True，开发调试用）
        """
        self.config_path = config_path or "configs/system.yaml"
        self.mock_ros2 = mock_ros2
        self.config: Optional[ConfigCenter] = None
        self._message_bus: Optional[MessageBus] = None
        self._super_agent: Optional[SuperAgent] = None
        self._behavior_executor: Optional["BehaviorExecutor"] = None
        self._bridge: Optional["BrainCerebellumBridge"] = None
        self._running = False
        
    async def initialize(self) -> None:
        """初始化系统所有组件"""
        logger.info("正在初始化 OpenRoboBrain 系统...")
        
        # 1. 加载配置
        self.config = ConfigCenter(self.config_path)
        await self.config.load()
        logger.info("配置加载完成")
        
        # 2. 初始化系统层 - 大脑管道
        from orb.system.brain_pipeline.message_bus import MessageBus
        self._message_bus = MessageBus(self.config)
        await self._message_bus.initialize()
        logger.info("大脑管道初始化完成")
        
        # 3. 初始化Agent层 - Super Agent
        from orb.agent.super.super_agent import SuperAgent
        self._super_agent = SuperAgent(self._message_bus, self.config)
        await self._super_agent.initialize()
        logger.info("Super Agent 初始化完成")
        
        # 4. 初始化行为层 - BehaviorExecutor
        from orb.behavior.executor import BehaviorExecutor
        from orb.behavior.registry import get_registry
        self._behavior_executor = BehaviorExecutor(registry=get_registry())
        logger.info("行为执行器初始化完成")
        
        # 5. 初始化桥接层 - Brain-Cerebellum Bridge
        from orb.system.brain_pipeline.brain_cerebellum_bridge import (
            BrainCerebellumBridge,
        )
        self._bridge = BrainCerebellumBridge(mock_mode=self.mock_ros2)
        await self._bridge.initialize()
        mode_str = "模拟模式" if self.mock_ros2 else "真实模式"
        logger.info(f"大脑-小脑桥接器初始化完成 ({mode_str})")
        
        logger.info("OpenRoboBrain 系统初始化完成")
        
    async def start(self) -> None:
        """启动系统"""
        if self._running:
            logger.warning("系统已在运行中")
            return
            
        logger.info("正在启动 OpenRoboBrain 系统...")
        self._running = True
        
        # 启动 Super Agent
        if self._super_agent:
            await self._super_agent.start()
            
        logger.info("OpenRoboBrain 系统启动完成")
        
    async def stop(self) -> None:
        """停止系统"""
        if not self._running:
            return
            
        logger.info("正在停止 OpenRoboBrain 系统...")
        self._running = False
        
        # 停止桥接器
        if self._bridge:
            await self._bridge.shutdown()
            
        # 停止 Super Agent
        if self._super_agent:
            await self._super_agent.stop()
            
        # 关闭大脑管道
        if self._message_bus:
            await self._message_bus.shutdown()
            
        logger.info("OpenRoboBrain 系统已停止")
    
    async def process(
        self,
        user_input: str,
        parameters: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
    ) -> ProcessResult:
        """
        处理用户输入
        
        接收自然语言输入，异步返回对话(chat)和ROS2控制消息。
        
        Args:
            user_input: 用户自然语言输入
            parameters: 额外参数
            trace_id: 追踪ID（可选，自动生成）
            
        Returns:
            ProcessResult: 包含chat_response和ros2_commands
        """
        # 生成trace_id
        trace_id = trace_id or f"trace-{uuid4().hex[:8]}"
        start_time = datetime.now()
        
        logger.info(f"[{trace_id}] 收到用户输入: {user_input[:100]}...")
        
        # 初始化结果
        result = ProcessResult(
            trace_id=trace_id,
            chat_response="",
            ros2_commands=[],
        )
        
        try:
            # 检查系统是否运行
            if not self._running:
                raise RuntimeError("OpenRoboBrain系统未启动")
            
            # 通过行为执行器处理
            if self._behavior_executor:
                from orb.behavior.base import BehaviorStatus
                
                logger.info(f"[{trace_id}] 执行行为匹配...")
                behavior_result = await self._behavior_executor.auto_execute(
                    user_input=user_input,
                    parameters=parameters,
                    trace_id=trace_id,
                )
                
                result.behavior_name = behavior_result.behavior_name
                result.behavior_result = behavior_result
                
                if behavior_result.status == BehaviorStatus.COMPLETED:
                    logger.info(f"[{trace_id}] 行为 '{behavior_result.behavior_name}' 执行完成")
                    
                    # 从行为结果中提取chat_response和ros2_commands
                    behavior_data = behavior_result.result or {}
                    
                    # 提取对话响应
                    result.chat_response = behavior_data.get(
                        "chat_response", 
                        f"已完成{behavior_result.behavior_name}任务"
                    )
                    
                    # 提取ROS2命令
                    ros2_cmds = behavior_data.get("ros2_commands", [])
                    if ros2_cmds:
                        from orb.system.brain_pipeline.brain_cerebellum_bridge import BrainCommand
                        for cmd_data in ros2_cmds:
                            if isinstance(cmd_data, dict):
                                cmd = BrainCommand(
                                    command_type=cmd_data.get("command_type", ""),
                                    parameters=cmd_data.get("parameters", {}),
                                    source_agent="OpenRoboBrain",
                                )
                                result.ros2_commands.append(cmd)
                                
                                # 通过Bridge发送命令
                                if self._bridge:
                                    logger.info(f"[{trace_id}] 发送ROS2命令: {cmd.command_type}")
                                    await self._bridge.send_command(cmd)
                    
                    result.success = True
                else:
                    result.success = False
                    result.error = behavior_result.error or "行为执行失败"
                    result.chat_response = f"抱歉，执行失败: {result.error}"
                    logger.warning(f"[{trace_id}] 行为执行失败: {result.error}")
            else:
                # 如果没有行为执行器，返回默认响应
                result.chat_response = "系统正在初始化中，请稍后再试"
                result.success = False
                result.error = "行为执行器未初始化"
                
        except Exception as e:
            logger.error(f"[{trace_id}] 处理失败: {e}")
            result.success = False
            result.error = str(e)
            result.chat_response = f"处理请求时发生错误: {e}"
            
        finally:
            # 计算执行时间
            end_time = datetime.now()
            result.execution_time_ms = (end_time - start_time).total_seconds() * 1000
            logger.info(f"[{trace_id}] 处理完成，耗时: {result.execution_time_ms:.2f}ms")
        
        return result
        
    async def run(self) -> None:
        """运行系统（阻塞直到收到停止信号）"""
        await self.initialize()
        await self.start()
        
        try:
            # 保持运行直到收到停止信号
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()
            
    @property
    def message_bus(self) -> Optional["MessageBus"]:
        """获取大脑管道消息总线"""
        return self._message_bus
        
    @property
    def super_agent(self) -> Optional["SuperAgent"]:
        """获取 Super Agent"""
        return self._super_agent
    
    @property
    def behavior_executor(self) -> Optional["BehaviorExecutor"]:
        """获取行为执行器"""
        return self._behavior_executor
    
    @property
    def bridge(self) -> Optional["BrainCerebellumBridge"]:
        """获取大脑-小脑桥接器"""
        return self._bridge
    
    @property
    def is_running(self) -> bool:
        """系统是否正在运行"""
        return self._running
