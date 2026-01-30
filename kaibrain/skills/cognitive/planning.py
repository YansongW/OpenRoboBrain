"""
规划技能

实现规划相关的能力，包括任务规划、路径规划、资源规划等。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from kaibrain.skills.base import (
    BaseSkill,
    SkillCategory,
    SkillContext,
    SkillResult,
    SkillState,
)


class PlanningType(Enum):
    """规划类型"""
    TASK = "task"               # 任务规划
    PATH = "path"               # 路径规划
    RESOURCE = "resource"       # 资源规划
    SCHEDULE = "schedule"       # 时间规划
    CONTINGENCY = "contingency" # 应急规划


@dataclass
class PlanStep:
    """规划步骤"""
    step_id: int
    action: str
    description: str
    duration: float = 0.0  # 预估时长
    dependencies: List[int] = field(default_factory=list)
    resources: List[str] = field(default_factory=list)


@dataclass
class Plan:
    """规划结果"""
    goal: str
    steps: List[PlanStep]
    total_duration: float
    resources_needed: List[str]


class PlanningSkill(BaseSkill):
    """
    规划技能
    
    能够制定各种类型的规划。
    """
    
    def __init__(
        self,
        action_manager: Optional[Any] = None,
        **kwargs: Any,
    ):
        super().__init__(
            name="planning",
            name_cn="规划",
            category=SkillCategory.COGNITIVE,
            description="制定各种类型的规划，包括任务规划、路径规划等",
            action_manager=action_manager,
        )
        
    def get_required_actions(self) -> List[str]:
        """获取规划技能所需的原子动作"""
        return [
            # 认知原子动作
            "cognitive.analyze",
            "cognitive.decompose",
            "cognitive.prioritize",
            "cognitive.optimize",
            "cognitive.evaluate",
        ]
        
    async def execute(self, context: SkillContext) -> SkillResult:
        """
        执行规划技能
        
        Args:
            context: 执行上下文，包含:
                - goal: 目标
                - planning_type: 规划类型
                - constraints: 约束条件
                - resources: 可用资源
        """
        params = context.parameters
        actions_executed = []
        
        try:
            goal = params.get("goal", "")
            planning_type = params.get("planning_type", PlanningType.TASK)
            constraints = params.get("constraints", {})
            resources = params.get("resources", [])
            
            if isinstance(planning_type, str):
                planning_type = PlanningType(planning_type)
                
            self.logger.info(
                f"开始规划: 类型={planning_type.value}, "
                f"目标={goal}"
            )
            
            # 1. 分析目标
            actions_executed.append("分析目标")
            goal_analysis = await self._analyze_goal(goal)
            
            # 2. 分解任务
            actions_executed.append("分解任务")
            sub_goals = await self._decompose_goal(goal_analysis)
            
            # 3. 生成规划
            actions_executed.append(f"生成{planning_type.value}规划")
            plan = await self._generate_plan(
                sub_goals,
                planning_type,
                constraints,
                resources,
            )
            
            # 4. 优化规划
            actions_executed.append("优化规划")
            optimized_plan = await self._optimize_plan(plan)
            
            return SkillResult(
                success=True,
                state=SkillState.COMPLETED,
                result_data={
                    "goal": goal,
                    "planning_type": planning_type.value,
                    "steps_count": len(optimized_plan.steps),
                    "total_duration": optimized_plan.total_duration,
                    "plan": self._plan_to_dict(optimized_plan),
                },
                started_at=context.started_at,
                actions_executed=actions_executed,
            )
            
        except Exception as e:
            return SkillResult(
                success=False,
                state=SkillState.FAILED,
                error_message=str(e),
                started_at=context.started_at,
                actions_executed=actions_executed,
            )
            
    async def _analyze_goal(self, goal: str) -> Dict[str, Any]:
        """分析目标"""
        return {
            "goal": goal,
            "type": "complex",
            "priority": "high",
        }
        
    async def _decompose_goal(
        self,
        goal_analysis: Dict[str, Any],
    ) -> List[str]:
        """分解目标为子目标"""
        return ["子目标1", "子目标2", "子目标3"]
        
    async def _generate_plan(
        self,
        sub_goals: List[str],
        planning_type: PlanningType,
        constraints: Dict[str, Any],
        resources: List[str],
    ) -> Plan:
        """生成规划"""
        steps = [
            PlanStep(
                step_id=i + 1,
                action=f"action_{i+1}",
                description=sub_goal,
                duration=10.0,
                dependencies=[i] if i > 0 else [],
            )
            for i, sub_goal in enumerate(sub_goals)
        ]
        
        return Plan(
            goal=sub_goals[0] if sub_goals else "",
            steps=steps,
            total_duration=sum(s.duration for s in steps),
            resources_needed=resources,
        )
        
    async def _optimize_plan(self, plan: Plan) -> Plan:
        """优化规划"""
        return plan
        
    def _plan_to_dict(self, plan: Plan) -> Dict[str, Any]:
        """将规划转换为字典"""
        return {
            "goal": plan.goal,
            "steps": [
                {
                    "step_id": s.step_id,
                    "action": s.action,
                    "description": s.description,
                    "duration": s.duration,
                }
                for s in plan.steps
            ],
            "total_duration": plan.total_duration,
            "resources_needed": plan.resources_needed,
        }
