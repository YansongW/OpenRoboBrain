"""
原子动作库 (Atomic Actions Library)

管理ROS2 Action的创建和执行，提供底层原子动作供技能层调用。

原子动作是最小的可执行动作单元，由硬件层直接执行。
技能层(Skill Layer)通过编排多个原子动作来实现高层次技能。

原子动作分类：
- locomotion: 行进动作（爬行、跪姿爬行、直立行走、跑步等）
- manipulation: 操作动作（抓取、释放、推、拉、搅拌等）
- perception: 感知动作（观察、扫描、识别等）
- balance: 平衡动作（保持平衡、重心转移等）
- swimming: 游泳动作（划臂、蹬腿、呼吸等）
- climbing: 攀爬动作（抓握、上拉、踏步等）
- cognitive: 认知动作（分析、记忆、推理等）
- language: 语言动作（听、说、理解等）
- expression: 表情动作（手势、点头等）
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from kaibrain.system.services.logger import LoggerMixin

if TYPE_CHECKING:
    from kaibrain.middleware.cerebellum_pipeline.ros2_node import ROS2Node


# ============== 原子动作定义 ==============

class AtomicActionCategory(Enum):
    """原子动作分类"""
    LOCOMOTION = "locomotion"       # 行进
    MANIPULATION = "manipulation"   # 操作
    PERCEPTION = "perception"       # 感知
    BALANCE = "balance"             # 平衡
    SWIMMING = "swimming"           # 游泳
    CLIMBING = "climbing"           # 攀爬
    COGNITIVE = "cognitive"         # 认知
    LANGUAGE = "language"           # 语言
    EXPRESSION = "expression"       # 表情


# 原子动作定义表（供技能层调用）
ATOMIC_ACTIONS: Dict[str, Dict[str, Any]] = {
    # ===== 行进动作 =====
    "locomotion.crawl": {
        "name_cn": "爬行",
        "category": AtomicActionCategory.LOCOMOTION,
        "description": "四肢着地的爬行移动",
        "ros2_type": "locomotion_msgs/Crawl",
    },
    "locomotion.kneeling_crawl": {
        "name_cn": "跪姿爬行",
        "category": AtomicActionCategory.LOCOMOTION,
        "description": "双膝和双手着地的爬行",
        "ros2_type": "locomotion_msgs/KneelingCrawl",
    },
    "locomotion.upright_walk": {
        "name_cn": "直立行走",
        "category": AtomicActionCategory.LOCOMOTION,
        "description": "正常的双足直立行走",
        "ros2_type": "locomotion_msgs/UprightWalk",
    },
    "locomotion.run": {
        "name_cn": "跑步",
        "category": AtomicActionCategory.LOCOMOTION,
        "description": "快速的双足跑动",
        "ros2_type": "locomotion_msgs/Run",
    },
    "locomotion.crouch_walk": {
        "name_cn": "蹲行",
        "category": AtomicActionCategory.LOCOMOTION,
        "description": "蹲着移动",
        "ros2_type": "locomotion_msgs/CrouchWalk",
    },
    "locomotion.sidestep": {
        "name_cn": "侧步移动",
        "category": AtomicActionCategory.LOCOMOTION,
        "description": "横向侧步移动",
        "ros2_type": "locomotion_msgs/Sidestep",
    },
    "locomotion.backward_walk": {
        "name_cn": "倒退行走",
        "category": AtomicActionCategory.LOCOMOTION,
        "description": "向后退行",
        "ros2_type": "locomotion_msgs/BackwardWalk",
    },
    "locomotion.turn": {
        "name_cn": "转向",
        "category": AtomicActionCategory.LOCOMOTION,
        "description": "原地转向",
        "ros2_type": "locomotion_msgs/Turn",
    },
    "locomotion.stop": {
        "name_cn": "停止",
        "category": AtomicActionCategory.LOCOMOTION,
        "description": "停止移动",
        "ros2_type": "locomotion_msgs/Stop",
    },
    
    # ===== 操作动作 =====
    "manipulation.grasp": {
        "name_cn": "抓取",
        "category": AtomicActionCategory.MANIPULATION,
        "description": "抓取物体",
        "ros2_type": "manipulation_msgs/Grasp",
    },
    "manipulation.release": {
        "name_cn": "释放",
        "category": AtomicActionCategory.MANIPULATION,
        "description": "释放/放开物体",
        "ros2_type": "manipulation_msgs/Release",
    },
    "manipulation.place": {
        "name_cn": "放置",
        "category": AtomicActionCategory.MANIPULATION,
        "description": "将物体放置到指定位置",
        "ros2_type": "manipulation_msgs/Place",
    },
    "manipulation.push": {
        "name_cn": "推",
        "category": AtomicActionCategory.MANIPULATION,
        "description": "推动物体",
        "ros2_type": "manipulation_msgs/Push",
    },
    "manipulation.pull": {
        "name_cn": "拉",
        "category": AtomicActionCategory.MANIPULATION,
        "description": "拉动物体",
        "ros2_type": "manipulation_msgs/Pull",
    },
    "manipulation.pour": {
        "name_cn": "倾倒",
        "category": AtomicActionCategory.MANIPULATION,
        "description": "倾倒液体或颗粒",
        "ros2_type": "manipulation_msgs/Pour",
    },
    "manipulation.stir": {
        "name_cn": "搅拌",
        "category": AtomicActionCategory.MANIPULATION,
        "description": "搅拌物质",
        "ros2_type": "manipulation_msgs/Stir",
    },
    "manipulation.cut": {
        "name_cn": "切割",
        "category": AtomicActionCategory.MANIPULATION,
        "description": "切割物体",
        "ros2_type": "manipulation_msgs/Cut",
    },
    "manipulation.flip": {
        "name_cn": "翻转",
        "category": AtomicActionCategory.MANIPULATION,
        "description": "翻转物体",
        "ros2_type": "manipulation_msgs/Flip",
    },
    "manipulation.wipe": {
        "name_cn": "擦拭",
        "category": AtomicActionCategory.MANIPULATION,
        "description": "擦拭表面",
        "ros2_type": "manipulation_msgs/Wipe",
    },
    "manipulation.spray": {
        "name_cn": "喷洒",
        "category": AtomicActionCategory.MANIPULATION,
        "description": "喷洒液体",
        "ros2_type": "manipulation_msgs/Spray",
    },
    "manipulation.fold": {
        "name_cn": "折叠",
        "category": AtomicActionCategory.MANIPULATION,
        "description": "折叠物品",
        "ros2_type": "manipulation_msgs/Fold",
    },
    
    # ===== 感知动作 =====
    "perception.observe": {
        "name_cn": "观察",
        "category": AtomicActionCategory.PERCEPTION,
        "description": "视觉观察目标",
        "ros2_type": "perception_msgs/Observe",
    },
    "perception.scan_area": {
        "name_cn": "扫描区域",
        "category": AtomicActionCategory.PERCEPTION,
        "description": "扫描整个区域",
        "ros2_type": "perception_msgs/ScanArea",
    },
    "perception.scan_terrain": {
        "name_cn": "扫描地形",
        "category": AtomicActionCategory.PERCEPTION,
        "description": "扫描地面地形",
        "ros2_type": "perception_msgs/ScanTerrain",
    },
    "perception.detect_obstacle": {
        "name_cn": "检测障碍物",
        "category": AtomicActionCategory.PERCEPTION,
        "description": "检测前方障碍物",
        "ros2_type": "perception_msgs/DetectObstacle",
    },
    "perception.identify_object": {
        "name_cn": "识别物体",
        "category": AtomicActionCategory.PERCEPTION,
        "description": "识别物体类型",
        "ros2_type": "perception_msgs/IdentifyObject",
    },
    "perception.observe_face": {
        "name_cn": "观察面部",
        "category": AtomicActionCategory.PERCEPTION,
        "description": "观察人脸",
        "ros2_type": "perception_msgs/ObserveFace",
    },
    "perception.observe_person": {
        "name_cn": "观察人物",
        "category": AtomicActionCategory.PERCEPTION,
        "description": "观察人物整体",
        "ros2_type": "perception_msgs/ObservePerson",
    },
    "perception.track_gaze": {
        "name_cn": "追踪视线",
        "category": AtomicActionCategory.PERCEPTION,
        "description": "追踪对方视线方向",
        "ros2_type": "perception_msgs/TrackGaze",
    },
    "perception.smell": {
        "name_cn": "嗅闻",
        "category": AtomicActionCategory.PERCEPTION,
        "description": "嗅觉感知",
        "ros2_type": "perception_msgs/Smell",
    },
    "perception.focus": {
        "name_cn": "聚焦",
        "category": AtomicActionCategory.PERCEPTION,
        "description": "聚焦到特定目标",
        "ros2_type": "perception_msgs/Focus",
    },
    "perception.track": {
        "name_cn": "追踪",
        "category": AtomicActionCategory.PERCEPTION,
        "description": "追踪移动目标",
        "ros2_type": "perception_msgs/Track",
    },
    
    # ===== 平衡动作 =====
    "balance.maintain": {
        "name_cn": "保持平衡",
        "category": AtomicActionCategory.BALANCE,
        "description": "保持身体平衡",
        "ros2_type": "balance_msgs/Maintain",
    },
    "balance.recover": {
        "name_cn": "恢复平衡",
        "category": AtomicActionCategory.BALANCE,
        "description": "从失衡状态恢复",
        "ros2_type": "balance_msgs/Recover",
    },
    "balance.shift_weight": {
        "name_cn": "重心转移",
        "category": AtomicActionCategory.BALANCE,
        "description": "转移身体重心",
        "ros2_type": "balance_msgs/ShiftWeight",
    },
    "balance.float": {
        "name_cn": "漂浮",
        "category": AtomicActionCategory.BALANCE,
        "description": "水中漂浮",
        "ros2_type": "balance_msgs/Float",
    },
    "balance.tread": {
        "name_cn": "踩水",
        "category": AtomicActionCategory.BALANCE,
        "description": "水中踩水保持浮力",
        "ros2_type": "balance_msgs/Tread",
    },
    
    # ===== 游泳动作 =====
    "swimming.arm_stroke": {
        "name_cn": "划臂",
        "category": AtomicActionCategory.SWIMMING,
        "description": "游泳划臂动作",
        "ros2_type": "swimming_msgs/ArmStroke",
    },
    "swimming.leg_kick": {
        "name_cn": "蹬腿",
        "category": AtomicActionCategory.SWIMMING,
        "description": "游泳蹬腿动作",
        "ros2_type": "swimming_msgs/LegKick",
    },
    "swimming.breathing": {
        "name_cn": "换气",
        "category": AtomicActionCategory.SWIMMING,
        "description": "游泳换气动作",
        "ros2_type": "swimming_msgs/Breathing",
    },
    "swimming.turn": {
        "name_cn": "转身",
        "category": AtomicActionCategory.SWIMMING,
        "description": "游泳转身",
        "ros2_type": "swimming_msgs/Turn",
    },
    "swimming.dive": {
        "name_cn": "下潜",
        "category": AtomicActionCategory.SWIMMING,
        "description": "潜入水中",
        "ros2_type": "swimming_msgs/Dive",
    },
    "swimming.surface": {
        "name_cn": "上浮",
        "category": AtomicActionCategory.SWIMMING,
        "description": "浮出水面",
        "ros2_type": "swimming_msgs/Surface",
    },
    
    # ===== 攀爬动作 =====
    "climbing.grip": {
        "name_cn": "抓握",
        "category": AtomicActionCategory.CLIMBING,
        "description": "抓握攀爬点",
        "ros2_type": "climbing_msgs/Grip",
    },
    "climbing.pull_up": {
        "name_cn": "上拉",
        "category": AtomicActionCategory.CLIMBING,
        "description": "向上拉起身体",
        "ros2_type": "climbing_msgs/PullUp",
    },
    "climbing.step_up": {
        "name_cn": "踏步上行",
        "category": AtomicActionCategory.CLIMBING,
        "description": "踏上更高的位置",
        "ros2_type": "climbing_msgs/StepUp",
    },
    "climbing.find_hold": {
        "name_cn": "寻找抓点",
        "category": AtomicActionCategory.CLIMBING,
        "description": "寻找可抓握的点",
        "ros2_type": "climbing_msgs/FindHold",
    },
    "climbing.rest": {
        "name_cn": "休息",
        "category": AtomicActionCategory.CLIMBING,
        "description": "攀爬中休息",
        "ros2_type": "climbing_msgs/Rest",
    },
    
    # ===== 认知动作 =====
    "cognitive.analyze": {
        "name_cn": "分析",
        "category": AtomicActionCategory.COGNITIVE,
        "description": "分析信息",
        "ros2_type": "cognitive_msgs/Analyze",
    },
    "cognitive.memorize": {
        "name_cn": "记忆",
        "category": AtomicActionCategory.COGNITIVE,
        "description": "记忆信息",
        "ros2_type": "cognitive_msgs/Memorize",
    },
    "cognitive.recall": {
        "name_cn": "回忆",
        "category": AtomicActionCategory.COGNITIVE,
        "description": "回忆信息",
        "ros2_type": "cognitive_msgs/Recall",
    },
    "cognitive.associate": {
        "name_cn": "联想",
        "category": AtomicActionCategory.COGNITIVE,
        "description": "信息关联",
        "ros2_type": "cognitive_msgs/Associate",
    },
    "cognitive.generalize": {
        "name_cn": "泛化",
        "category": AtomicActionCategory.COGNITIVE,
        "description": "知识泛化",
        "ros2_type": "cognitive_msgs/Generalize",
    },
    "cognitive.compare": {
        "name_cn": "比较",
        "category": AtomicActionCategory.COGNITIVE,
        "description": "比较信息",
        "ros2_type": "cognitive_msgs/Compare",
    },
    "cognitive.infer": {
        "name_cn": "推断",
        "category": AtomicActionCategory.COGNITIVE,
        "description": "逻辑推断",
        "ros2_type": "cognitive_msgs/Infer",
    },
    "cognitive.evaluate": {
        "name_cn": "评估",
        "category": AtomicActionCategory.COGNITIVE,
        "description": "评估结果",
        "ros2_type": "cognitive_msgs/Evaluate",
    },
    "cognitive.synthesize": {
        "name_cn": "综合",
        "category": AtomicActionCategory.COGNITIVE,
        "description": "综合信息",
        "ros2_type": "cognitive_msgs/Synthesize",
    },
    "cognitive.decompose": {
        "name_cn": "分解",
        "category": AtomicActionCategory.COGNITIVE,
        "description": "分解问题",
        "ros2_type": "cognitive_msgs/Decompose",
    },
    "cognitive.prioritize": {
        "name_cn": "优先排序",
        "category": AtomicActionCategory.COGNITIVE,
        "description": "排列优先级",
        "ros2_type": "cognitive_msgs/Prioritize",
    },
    "cognitive.optimize": {
        "name_cn": "优化",
        "category": AtomicActionCategory.COGNITIVE,
        "description": "优化方案",
        "ros2_type": "cognitive_msgs/Optimize",
    },
    "cognitive.classify": {
        "name_cn": "分类",
        "category": AtomicActionCategory.COGNITIVE,
        "description": "信息分类",
        "ros2_type": "cognitive_msgs/Classify",
    },
    "cognitive.fuse_multimodal": {
        "name_cn": "多模态融合",
        "category": AtomicActionCategory.COGNITIVE,
        "description": "融合多模态信息",
        "ros2_type": "cognitive_msgs/FuseMultimodal",
    },
    
    # ===== 语言动作 =====
    "language.listen": {
        "name_cn": "倾听",
        "category": AtomicActionCategory.LANGUAGE,
        "description": "倾听语音",
        "ros2_type": "language_msgs/Listen",
    },
    "language.speak": {
        "name_cn": "说话",
        "category": AtomicActionCategory.LANGUAGE,
        "description": "语音输出",
        "ros2_type": "language_msgs/Speak",
    },
    "language.understand": {
        "name_cn": "理解",
        "category": AtomicActionCategory.LANGUAGE,
        "description": "语义理解",
        "ros2_type": "language_msgs/Understand",
    },
    "language.generate": {
        "name_cn": "生成",
        "category": AtomicActionCategory.LANGUAGE,
        "description": "生成回复",
        "ros2_type": "language_msgs/Generate",
    },
    
    # ===== 表情动作 =====
    "expression.gesture": {
        "name_cn": "手势",
        "category": AtomicActionCategory.EXPRESSION,
        "description": "做手势",
        "ros2_type": "expression_msgs/Gesture",
    },
    "expression.nod": {
        "name_cn": "点头",
        "category": AtomicActionCategory.EXPRESSION,
        "description": "点头示意",
        "ros2_type": "expression_msgs/Nod",
    },
}


def get_atomic_action(action_id: str) -> Optional[Dict[str, Any]]:
    """获取原子动作定义"""
    return ATOMIC_ACTIONS.get(action_id)


def list_atomic_actions(category: Optional[AtomicActionCategory] = None) -> List[str]:
    """列出原子动作"""
    if category is None:
        return list(ATOMIC_ACTIONS.keys())
    return [
        action_id
        for action_id, info in ATOMIC_ACTIONS.items()
        if info["category"] == category
    ]


# ============== Action状态和管理 ==============

class ActionState(Enum):
    """Action状态"""
    PENDING = "pending"
    ACTIVE = "active"
    PREEMPTING = "preempting"
    SUCCEEDED = "succeeded"
    ABORTED = "aborted"
    PREEMPTED = "preempted"


@dataclass
class ActionGoal:
    """Action目标"""
    goal_id: str
    action_name: str
    goal_data: Dict[str, Any] = field(default_factory=dict)
    state: ActionState = ActionState.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    result: Optional[Any] = None
    feedback: Optional[Any] = None


@dataclass
class ActionInfo:
    """Action信息"""
    name: str
    action_type: str
    role: str  # server, client
    created_at: datetime = field(default_factory=datetime.now)
    active_goals: int = 0
    completed_goals: int = 0


class ActionManager(LoggerMixin):
    """
    原子动作管理器
    
    管理原子动作的注册、执行和状态跟踪。
    原子动作通过ROS2 Action接口与硬件层通信。
    
    技能层通过此管理器调用原子动作来完成高层次技能。
    """
    
    @staticmethod
    def get_action_type(action_id: str) -> str:
        """获取原子动作的ROS2类型"""
        action_info = ATOMIC_ACTIONS.get(action_id)
        if action_info:
            return action_info.get("ros2_type", "action_msgs/GoalStatus")
        return "action_msgs/GoalStatus"
    
    def __init__(self, ros2_node: Optional[ROS2Node] = None):
        """
        初始化Action管理器
        
        Args:
            ros2_node: ROS2节点
        """
        self.ros2_node = ros2_node
        self._actions: Dict[str, ActionInfo] = {}
        self._goals: Dict[str, ActionGoal] = {}
        self._handlers: Dict[str, Callable] = {}
        self._feedback_callbacks: Dict[str, List[Callable]] = {}
        
    def register_action_server(
        self,
        action_name: str,
        handler: Callable,
        action_type: Optional[Any] = None,
    ) -> ActionInfo:
        """
        注册Action服务端
        
        Args:
            action_name: Action名称
            handler: 执行处理函数
            action_type: Action类型
            
        Returns:
            ActionInfo
        """
        self._handlers[action_name] = handler
        
        type_str = self.get_action_type(action_name)
        
        info = ActionInfo(
            name=action_name,
            action_type=type_str,
            role="server",
        )
        self._actions[action_name] = info
        
        self.logger.info(f"注册Action服务端: {action_name}")
        return info
        
    def register_action_client(
        self,
        action_name: str,
        action_type: Optional[Any] = None,
    ) -> ActionInfo:
        """
        注册Action客户端
        
        Args:
            action_name: Action名称
            action_type: Action类型
            
        Returns:
            ActionInfo
        """
        type_str = self.get_action_type(action_name)
        
        info = ActionInfo(
            name=action_name,
            action_type=type_str,
            role="client",
        )
        self._actions[action_name] = info
        
        self.logger.info(f"注册Action客户端: {action_name}")
        return info
        
    async def send_goal(
        self,
        action_name: str,
        goal_data: Dict[str, Any],
        feedback_callback: Optional[Callable] = None,
        timeout: Optional[float] = None,
    ) -> ActionGoal:
        """
        发送Goal
        
        Args:
            action_name: Action名称
            goal_data: Goal数据
            feedback_callback: 反馈回调
            timeout: 超时时间（None表示不等待完成）
            
        Returns:
            ActionGoal
        """
        import uuid
        goal_id = str(uuid.uuid4())
        
        goal = ActionGoal(
            goal_id=goal_id,
            action_name=action_name,
            goal_data=goal_data,
        )
        self._goals[goal_id] = goal
        
        # 注册反馈回调
        if feedback_callback:
            if action_name not in self._feedback_callbacks:
                self._feedback_callbacks[action_name] = []
            self._feedback_callbacks[action_name].append(feedback_callback)
            
        # 更新统计
        if action_name in self._actions:
            self._actions[action_name].active_goals += 1
            
        # 模拟执行（实际需要通过ROS2 Action客户端）
        goal.state = ActionState.ACTIVE
        goal.started_at = datetime.now()
        
        self.logger.info(f"发送Goal: {action_name} ({goal_id})")
        
        if timeout:
            # 等待完成
            try:
                await asyncio.wait_for(
                    self._wait_for_result(goal_id),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                self.logger.warning(f"Goal超时: {goal_id}")
                goal.state = ActionState.ABORTED
                
        return goal
        
    async def _wait_for_result(self, goal_id: str) -> None:
        """等待Goal完成"""
        while True:
            goal = self._goals.get(goal_id)
            if not goal:
                break
            if goal.state in [
                ActionState.SUCCEEDED,
                ActionState.ABORTED,
                ActionState.PREEMPTED,
            ]:
                break
            await asyncio.sleep(0.1)
            
    async def cancel_goal(self, goal_id: str) -> bool:
        """
        取消Goal
        
        Args:
            goal_id: Goal ID
            
        Returns:
            是否成功
        """
        goal = self._goals.get(goal_id)
        if not goal:
            return False
            
        if goal.state == ActionState.ACTIVE:
            goal.state = ActionState.PREEMPTING
            # TODO: 实际通过ROS2取消
            goal.state = ActionState.PREEMPTED
            goal.finished_at = datetime.now()
            
            self.logger.info(f"取消Goal: {goal_id}")
            return True
            
        return False
        
    def update_feedback(self, goal_id: str, feedback: Any) -> None:
        """更新反馈"""
        goal = self._goals.get(goal_id)
        if goal:
            goal.feedback = feedback
            
            # 调用回调
            callbacks = self._feedback_callbacks.get(goal.action_name, [])
            for callback in callbacks:
                try:
                    callback(goal_id, feedback)
                except Exception as e:
                    self.logger.error(f"反馈回调错误: {e}")
                    
    def set_result(
        self,
        goal_id: str,
        result: Any,
        success: bool = True,
    ) -> None:
        """设置结果"""
        goal = self._goals.get(goal_id)
        if goal:
            goal.result = result
            goal.state = ActionState.SUCCEEDED if success else ActionState.ABORTED
            goal.finished_at = datetime.now()
            
            # 更新统计
            action_name = goal.action_name
            if action_name in self._actions:
                self._actions[action_name].active_goals -= 1
                self._actions[action_name].completed_goals += 1
                
    def get_goal(self, goal_id: str) -> Optional[ActionGoal]:
        """获取Goal"""
        return self._goals.get(goal_id)
        
    def list_active_goals(self, action_name: Optional[str] = None) -> List[ActionGoal]:
        """列出活跃的Goal"""
        goals = [g for g in self._goals.values() if g.state == ActionState.ACTIVE]
        
        if action_name:
            goals = [g for g in goals if g.action_name == action_name]
            
        return goals
