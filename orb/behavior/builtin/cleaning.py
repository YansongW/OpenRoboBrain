"""
清洁行为

组合感知、任务编排等能力完成清洁任务。
"""

from __future__ import annotations

from typing import Any, Dict, List

from orb.behavior.base import (
    Behavior,
    BehaviorConfig,
    BehaviorContext,
)


class CleaningBehavior(Behavior):
    """
    清洁行为
    
    能力组合：
    - 感知理解：场景理解、区域识别
    - 认知推理：区域划分、路径规划
    - 任务编排：协调执行
    - 通过 Bridge 发送指令给小脑控制移动和清洁
    """
    
    KEYWORDS = [
        "清洁", "打扫", "扫地", "拖地", "擦", "洗",
        "clean", "cleaning", "sweep", "mop", "wipe",
        "卫生", "整理", "收拾",
    ]
    
    def __init__(self):
        config = BehaviorConfig(
            name="cleaning",
            description="清洁行为 - 完成清洁任务的复合行为",
            version="1.0.0",
            required_capabilities=[
                "perception",      # 感知理解
                "reasoning",       # 认知推理
                "orchestration",   # 任务编排
            ],
            tags=["daily_life", "cleaning", "housework"],
            timeout_seconds=1800.0,  # 清洁可能需要较长时间
        )
        super().__init__(config)
    
    def can_handle(self, user_input: str) -> float:
        """评估是否可以处理"""
        input_lower = user_input.lower()
        
        matches = sum(1 for kw in self.KEYWORDS if kw in input_lower)
        
        if matches == 0:
            return 0.0
        elif matches == 1:
            return 0.6
        else:
            return 0.85
    
    async def execute(self, context: BehaviorContext) -> Dict[str, Any]:
        """
        执行清洁行为
        
        步骤：
        1. 场景理解（感知）
        2. 区域划分（推理）
        3. 路径规划（推理）
        4. 执行清洁（编排 + 小脑控制）
        """
        result = {
            "task": "cleaning",
            "steps": [],
            "status": "completed",
        }
        
        # 如果匹配到工作流，复用
        if context.workflow_matched:
            return {
                "task": "cleaning",
                "workflow_reused": True,
                "workflow_id": context.workflow_id,
                "status": "completed",
            }
        
        # 步骤1: 场景理解
        target_area = self._parse_target_area(context.user_input)
        result["target_area"] = target_area
        result["steps"].append({
            "step": 1,
            "action": "scene_understanding",
            "capability": "perception",
            "result": f"目标区域: {target_area}",
        })
        
        # 步骤2: 区域划分
        zones = self._divide_zones(target_area)
        result["zones"] = zones
        result["steps"].append({
            "step": 2,
            "action": "zone_division",
            "capability": "reasoning",
            "result": f"划分为 {len(zones)} 个区域",
        })
        
        # 步骤3: 路径规划
        path = self._plan_path(zones)
        result["path"] = path
        result["steps"].append({
            "step": 3,
            "action": "path_planning",
            "capability": "reasoning",
            "result": f"规划路径: {len(path)} 个节点",
        })
        
        # 步骤4: 执行清洁
        result["steps"].append({
            "step": 4,
            "action": "execute_cleaning",
            "capability": "orchestration",
            "result": "清洁完成（模拟）",
            "note": "实际执行需要通过 Bridge 发送指令给小脑",
        })
        
        return result
    
    def _parse_target_area(self, user_input: str) -> str:
        """解析目标区域"""
        areas = ["客厅", "卧室", "厨房", "卫生间", "阳台", "全屋"]
        
        for area in areas:
            if area in user_input:
                return area
        
        return "全屋"
    
    def _divide_zones(self, area: str) -> List[Dict[str, Any]]:
        """区域划分"""
        # 简单模拟
        return [
            {"zone_id": 1, "name": f"{area}-区域1", "priority": 1},
            {"zone_id": 2, "name": f"{area}-区域2", "priority": 2},
            {"zone_id": 3, "name": f"{area}-区域3", "priority": 3},
        ]
    
    def _plan_path(self, zones: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """路径规划"""
        return [
            {"from": "起点", "to": zones[0]["name"], "action": "移动"},
            {"from": zones[0]["name"], "to": zones[1]["name"], "action": "清洁+移动"},
            {"from": zones[1]["name"], "to": zones[2]["name"], "action": "清洁+移动"},
            {"from": zones[2]["name"], "to": "起点", "action": "清洁+返回"},
        ]
