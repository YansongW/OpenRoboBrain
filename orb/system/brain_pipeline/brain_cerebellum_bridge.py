"""
大脑-小脑桥接器 (Brain-Cerebellum Bridge)

大脑管道和小脑管道之间的同步机制。

核心设计原则：
1. 大脑（Brain）和小脑（Cerebellum）是完全解耦的
2. 大脑使用 WebSocket JSON（非实时，高层次）
3. 小脑使用 ROS2 DDS（实时，低层次）
4. 桥接器负责两者之间的状态同步

同步内容：
- 命令下发：Brain -> Cerebellum（高层指令转换为运动控制）
- 状态反馈：Cerebellum -> Brain（传感器数据、执行状态）
- 异常处理：双向紧急停止

消息转换：
- Brain 使用语义化命令（"移动到位置A"）
- Cerebellum 使用运动控制指令（速度、加速度、轨迹）
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING
from uuid import uuid4

from orb.system.services.logger import LoggerMixin, get_logger

if TYPE_CHECKING:
    from orb.system.brain_pipeline.websocket_server import (
        BrainWebSocketServer,
        WSMessage,
        WSMessageType,
    )
    from orb.middleware.cerebellum_pipeline.ros2_node import ROS2Node

logger = get_logger(__name__)


class SyncDirection(Enum):
    """同步方向"""
    BRAIN_TO_CEREBELLUM = "brain_to_cerebellum"
    CEREBELLUM_TO_BRAIN = "cerebellum_to_brain"
    BIDIRECTIONAL = "bidirectional"


class CommandPriority(Enum):
    """命令优先级"""
    EMERGENCY = 0       # 紧急（立即执行，中断其他）
    HIGH = 1            # 高（尽快执行）
    NORMAL = 2          # 普通
    LOW = 3             # 低（空闲时执行）
    BACKGROUND = 4      # 后台


class ExecutionStatus(Enum):
    """执行状态"""
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass
class BrainCommand:
    """
    大脑命令（语义化）
    
    从大脑管道发出的高层次指令。
    """
    command_id: str = field(default_factory=lambda: str(uuid4()))
    command_type: str = ""          # 命令类型: move, grasp, navigate, etc.
    parameters: Dict[str, Any] = field(default_factory=dict)
    priority: CommandPriority = CommandPriority.NORMAL
    source_agent: str = ""          # 发起 Agent
    timeout_seconds: float = 60.0   # 超时时间
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "commandId": self.command_id,
            "commandType": self.command_type,
            "parameters": self.parameters,
            "priority": self.priority.value,
            "sourceAgent": self.source_agent,
            "timeoutSeconds": self.timeout_seconds,
            "createdAt": self.created_at,
            "metadata": self.metadata,
        }


@dataclass
class CerebellumAction:
    """
    小脑动作（运动控制）
    
    转换后发送到小脑管道的低层次控制指令。
    """
    action_id: str = field(default_factory=lambda: str(uuid4()))
    parent_command_id: str = ""     # 关联的大脑命令
    action_type: str = ""           # ROS2 action 类型
    ros2_topic: str = ""            # 目标 ROS2 话题
    ros2_payload: Dict[str, Any] = field(default_factory=dict)
    sequence_index: int = 0         # 动作序列索引
    timeout_ms: int = 5000          # 超时（毫秒，小脑级别）
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_ros2_message(self) -> Dict[str, Any]:
        """转换为 ROS2 消息格式"""
        return {
            "header": {
                "action_id": self.action_id,
                "command_id": self.parent_command_id,
                "timestamp": self.created_at,
            },
            "action_type": self.action_type,
            **self.ros2_payload,
        }


@dataclass
class CerebellumFeedback:
    """
    小脑反馈
    
    从小脑管道返回的状态和传感器数据。
    """
    feedback_id: str = field(default_factory=lambda: str(uuid4()))
    action_id: str = ""             # 关联的动作
    command_id: str = ""            # 关联的命令
    status: ExecutionStatus = ExecutionStatus.PENDING
    progress: float = 0.0           # 进度 0-1
    sensor_data: Dict[str, Any] = field(default_factory=dict)
    error_code: Optional[int] = None
    error_message: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "feedbackId": self.feedback_id,
            "actionId": self.action_id,
            "commandId": self.command_id,
            "status": self.status.value,
            "progress": self.progress,
            "sensorData": self.sensor_data,
            "errorCode": self.error_code,
            "errorMessage": self.error_message,
            "timestamp": self.timestamp,
        }


class CommandTranslator(ABC):
    """
    命令转换器基类
    
    将大脑语义化命令转换为小脑运动控制指令。
    """
    
    @abstractmethod
    def can_translate(self, command: BrainCommand) -> bool:
        """是否可以转换此命令"""
        pass
        
    @abstractmethod
    def translate(self, command: BrainCommand) -> List[CerebellumAction]:
        """转换命令为动作序列"""
        pass


class MoveCommandTranslator(CommandTranslator):
    """移动命令转换器"""
    
    def can_translate(self, command: BrainCommand) -> bool:
        return command.command_type in ["move", "move_to", "navigate"]
        
    def translate(self, command: BrainCommand) -> List[CerebellumAction]:
        params = command.parameters
        
        # 提取目标位置
        target_position = params.get("target_position", params.get("position", {}))
        velocity = params.get("velocity", 0.5)
        
        return [CerebellumAction(
            parent_command_id=command.command_id,
            action_type="nav2_navigate_to_pose",
            ros2_topic="/navigate_to_pose",
            ros2_payload={
                "pose": {
                    "position": target_position,
                    "orientation": params.get("orientation", {"w": 1.0}),
                },
                "behavior_tree": params.get("behavior_tree", ""),
            },
            timeout_ms=int(command.timeout_seconds * 1000),
        )]


class GraspCommandTranslator(CommandTranslator):
    """抓取命令转换器"""
    
    def can_translate(self, command: BrainCommand) -> bool:
        return command.command_type in ["grasp", "pick", "grab"]
        
    def translate(self, command: BrainCommand) -> List[CerebellumAction]:
        params = command.parameters
        actions = []
        
        # 分解为多个动作
        # 1. 移动手臂到预抓取位置
        actions.append(CerebellumAction(
            parent_command_id=command.command_id,
            action_type="moveit_move",
            ros2_topic="/move_group",
            ros2_payload={
                "target_pose": params.get("approach_pose", {}),
                "planning_group": "arm",
            },
            sequence_index=0,
        ))
        
        # 2. 打开夹爪
        actions.append(CerebellumAction(
            parent_command_id=command.command_id,
            action_type="gripper_control",
            ros2_topic="/gripper/command",
            ros2_payload={
                "command": "open",
                "width": params.get("gripper_width", 0.1),
            },
            sequence_index=1,
        ))
        
        # 3. 移动到抓取位置
        actions.append(CerebellumAction(
            parent_command_id=command.command_id,
            action_type="moveit_move",
            ros2_topic="/move_group",
            ros2_payload={
                "target_pose": params.get("grasp_pose", {}),
                "planning_group": "arm",
            },
            sequence_index=2,
        ))
        
        # 4. 关闭夹爪
        actions.append(CerebellumAction(
            parent_command_id=command.command_id,
            action_type="gripper_control",
            ros2_topic="/gripper/command",
            ros2_payload={
                "command": "close",
                "force": params.get("grasp_force", 10.0),
            },
            sequence_index=3,
        ))
        
        return actions


class BrainCerebellumBridge(LoggerMixin):
    """
    大脑-小脑桥接器
    
    负责：
    1. 命令下发：Brain -> Cerebellum
    2. 状态反馈：Cerebellum -> Brain
    3. 状态同步
    4. 异常处理
    """
    
    def __init__(
        self,
        brain_server: Optional["BrainWebSocketServer"] = None,
        cerebellum_node: Optional["ROS2Node"] = None,
        mock_mode: bool = True,
    ):
        """
        初始化桥接器
        
        Args:
            brain_server: 大脑 WebSocket 服务器
            cerebellum_node: 小脑 ROS2 节点
            mock_mode: 是否使用模拟模式（不连接真实ROS2）
        """
        self._brain_server = brain_server
        self._cerebellum_node = cerebellum_node
        self._mock_mode = mock_mode
        
        self._running = False
        
        # 命令转换器
        self._translators: List[CommandTranslator] = [
            MoveCommandTranslator(),
            GraspCommandTranslator(),
        ]
        
        # 命令追踪
        self._pending_commands: Dict[str, BrainCommand] = {}
        self._command_actions: Dict[str, List[CerebellumAction]] = {}
        self._action_status: Dict[str, ExecutionStatus] = {}
        
        # 同步状态
        self._brain_state: Dict[str, Any] = {}
        self._cerebellum_state: Dict[str, Any] = {}
        self._last_sync: Optional[str] = None
        
        # 回调
        self._command_callbacks: Dict[str, asyncio.Future] = {}
        
    @property
    def is_running(self) -> bool:
        return self._running
        
    def set_brain_server(self, server: "BrainWebSocketServer") -> None:
        """设置大脑服务器"""
        self._brain_server = server
        
    def set_cerebellum_node(self, node: "ROS2Node") -> None:
        """设置小脑节点"""
        self._cerebellum_node = node
        
    def register_translator(self, translator: CommandTranslator) -> None:
        """注册命令转换器"""
        self._translators.append(translator)
        
    async def initialize(self) -> bool:
        """初始化桥接器"""
        self.logger.info("初始化 Brain-Cerebellum 桥接器...")
        
        # 注册大脑消息处理器
        if self._brain_server:
            from orb.system.brain_pipeline.websocket_server import WSMessageType
            self._brain_server.register_handler(
                WSMessageType.SYNC_COMMAND,
                self._handle_brain_command,
            )
            
        # 注册小脑消息回调
        if self._cerebellum_node:
            self._cerebellum_node.create_subscriber(
                "/OpenRoboBrain/feedback",
                dict,  # 使用通用类型
                self._handle_cerebellum_feedback,
            )
            
        self._running = True
        self.logger.info("Brain-Cerebellum 桥接器初始化完成")
        return True
        
    async def shutdown(self) -> None:
        """关闭桥接器"""
        self._running = False
        
        # 取消所有等待的命令
        for future in self._command_callbacks.values():
            if not future.done():
                future.cancel()
                
        self._pending_commands.clear()
        self._command_callbacks.clear()
        
        self.logger.info("Brain-Cerebellum 桥接器已关闭")
        
    async def send_command(
        self,
        command: BrainCommand,
        wait_for_completion: bool = False,
        timeout: Optional[float] = None,
    ) -> Optional[CerebellumFeedback]:
        """
        发送命令到小脑
        
        Args:
            command: 大脑命令
            wait_for_completion: 是否等待完成
            timeout: 超时时间
            
        Returns:
            执行反馈
        """
        self.logger.info(f"发送命令: {command.command_type} (mock={self._mock_mode})")
        
        # 模拟模式 - 直接返回成功
        if self._mock_mode:
            self.logger.debug(f"[Mock] 模拟执行命令: {command.command_type}")
            self.logger.debug(f"[Mock] 命令参数: {command.parameters}")
            
            # 保存命令（用于追踪）
            self._pending_commands[command.command_id] = command
            
            return CerebellumFeedback(
                command_id=command.command_id,
                status=ExecutionStatus.COMPLETED,
                progress=1.0,
                sensor_data={"mock": True},
            )
        
        # 真实模式 - 转换并发送
        # 转换命令
        actions = self._translate_command(command)
        if not actions:
            self.logger.warning(f"无法转换命令: {command.command_type}")
            return CerebellumFeedback(
                command_id=command.command_id,
                status=ExecutionStatus.FAILED,
                error_message=f"Unknown command type: {command.command_type}",
            )
            
        # 保存命令
        self._pending_commands[command.command_id] = command
        self._command_actions[command.command_id] = actions
        
        # 发送到小脑
        for action in actions:
            await self._send_to_cerebellum(action)
            self._action_status[action.action_id] = ExecutionStatus.EXECUTING
            
        # 等待完成
        if wait_for_completion:
            return await self._wait_for_command(
                command.command_id,
                timeout or command.timeout_seconds,
            )
            
        return CerebellumFeedback(
            command_id=command.command_id,
            status=ExecutionStatus.EXECUTING,
        )
        
    def _translate_command(self, command: BrainCommand) -> List[CerebellumAction]:
        """转换命令"""
        for translator in self._translators:
            if translator.can_translate(command):
                return translator.translate(command)
        return []
        
    async def _send_to_cerebellum(self, action: CerebellumAction) -> bool:
        """发送动作到小脑"""
        if not self._cerebellum_node:
            self.logger.warning("小脑节点未初始化")
            return False
            
        ros2_message = action.to_ros2_message()
        return await self._cerebellum_node.publish(
            action.ros2_topic,
            ros2_message,
        )
        
    async def _wait_for_command(
        self,
        command_id: str,
        timeout: float,
    ) -> CerebellumFeedback:
        """等待命令完成"""
        future: asyncio.Future = asyncio.Future()
        self._command_callbacks[command_id] = future
        
        try:
            feedback = await asyncio.wait_for(future, timeout=timeout)
            return feedback
        except asyncio.TimeoutError:
            return CerebellumFeedback(
                command_id=command_id,
                status=ExecutionStatus.TIMEOUT,
                error_message=f"Command timeout after {timeout}s",
            )
        finally:
            self._command_callbacks.pop(command_id, None)
            
    async def _handle_brain_command(self, message: "WSMessage", client) -> None:
        """处理来自大脑的命令"""
        payload = message.payload
        
        command = BrainCommand(
            command_type=payload.get("commandType", ""),
            parameters=payload.get("parameters", {}),
            priority=CommandPriority(payload.get("priority", 2)),
            source_agent=message.source,
            timeout_seconds=payload.get("timeoutSeconds", 60.0),
            metadata=payload.get("metadata", {}),
        )
        
        # 异步执行
        asyncio.create_task(self._execute_command(command, message.source))
        
    async def _execute_command(self, command: BrainCommand, source_agent: str) -> None:
        """执行命令并发送反馈"""
        feedback = await self.send_command(command, wait_for_completion=True)
        
        # 发送反馈到大脑
        if self._brain_server:
            from orb.system.brain_pipeline.websocket_server import (
                WSMessage,
                WSMessageType,
            )
            await self._brain_server.send_to_agent(
                source_agent,
                WSMessage(
                    type=WSMessageType.SYNC_FEEDBACK,
                    source="bridge",
                    target=source_agent,
                    payload=feedback.to_dict(),
                ),
            )
            
    def _handle_cerebellum_feedback(self, ros2_message: Dict[str, Any]) -> None:
        """处理来自小脑的反馈"""
        action_id = ros2_message.get("header", {}).get("action_id", "")
        command_id = ros2_message.get("header", {}).get("command_id", "")
        
        # 更新动作状态
        status_str = ros2_message.get("status", "executing")
        status = ExecutionStatus(status_str) if status_str else ExecutionStatus.EXECUTING
        self._action_status[action_id] = status
        
        # 检查命令是否完成
        if command_id in self._command_actions:
            actions = self._command_actions[command_id]
            all_completed = all(
                self._action_status.get(a.action_id) == ExecutionStatus.COMPLETED
                for a in actions
            )
            any_failed = any(
                self._action_status.get(a.action_id) in [
                    ExecutionStatus.FAILED,
                    ExecutionStatus.TIMEOUT,
                    ExecutionStatus.CANCELLED,
                ]
                for a in actions
            )
            
            if all_completed or any_failed:
                feedback = CerebellumFeedback(
                    action_id=action_id,
                    command_id=command_id,
                    status=ExecutionStatus.COMPLETED if all_completed else ExecutionStatus.FAILED,
                    sensor_data=ros2_message.get("sensor_data", {}),
                )
                
                # 触发回调
                if command_id in self._command_callbacks:
                    future = self._command_callbacks[command_id]
                    if not future.done():
                        future.set_result(feedback)
                        
    async def emergency_stop(self) -> bool:
        """
        紧急停止
        
        向小脑发送紧急停止命令，同时通知大脑。
        """
        self.logger.warning("触发紧急停止!")
        
        # 发送到小脑
        if self._cerebellum_node:
            await self._cerebellum_node.publish(
                "/emergency_stop",
                {"command": "STOP", "timestamp": datetime.now().isoformat()},
            )
            
        # 通知大脑
        if self._brain_server:
            from orb.system.brain_pipeline.websocket_server import (
                WSMessage,
                WSMessageType,
            )
            await self._brain_server.broadcast(WSMessage(
                type=WSMessageType.EVENT_LIFECYCLE,
                source="bridge",
                payload={
                    "event": "emergency_stop",
                    "timestamp": datetime.now().isoformat(),
                },
            ))
            
        # 取消所有等待的命令
        for command_id, future in list(self._command_callbacks.items()):
            if not future.done():
                future.set_result(CerebellumFeedback(
                    command_id=command_id,
                    status=ExecutionStatus.CANCELLED,
                    error_message="Emergency stop triggered",
                ))
                
        return True
        
    def get_sync_state(self) -> Dict[str, Any]:
        """获取同步状态"""
        return {
            "running": self._running,
            "brain_connected": self._brain_server is not None and self._brain_server.is_running,
            "cerebellum_connected": self._cerebellum_node is not None,
            "pending_commands": len(self._pending_commands),
            "last_sync": self._last_sync,
            "brain_state": self._brain_state,
            "cerebellum_state": self._cerebellum_state,
        }
        
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        status_counts = {}
        for status in ExecutionStatus:
            status_counts[status.value] = sum(
                1 for s in self._action_status.values() if s == status
            )
            
        return {
            "running": self._running,
            "translators_count": len(self._translators),
            "pending_commands": len(self._pending_commands),
            "total_actions": len(self._action_status),
            "status_counts": status_counts,
        }


# ============== 便捷函数 ==============

def create_bridge(
    brain_server: Optional["BrainWebSocketServer"] = None,
    cerebellum_node: Optional["ROS2Node"] = None,
) -> BrainCerebellumBridge:
    """创建桥接器"""
    return BrainCerebellumBridge(
        brain_server=brain_server,
        cerebellum_node=cerebellum_node,
    )
