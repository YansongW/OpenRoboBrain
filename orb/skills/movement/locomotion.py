"""
行进技能

实现各种行进方式，包括直立行走、跑步、爬行等。
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from orb.skills.base import (
    BaseSkill,
    SkillCategory,
    SkillContext,
    SkillResult,
    SkillState,
)


class LocomotionMode(Enum):
    """行进模式"""
    UPRIGHT_WALK = "upright_walk"       # 直立行走
    RUNNING = "running"                  # 跑步
    JOGGING = "jogging"                  # 慢跑
    CRAWLING = "crawling"                # 爬行
    KNEELING_CRAWL = "kneeling_crawl"   # 跪姿爬行
    CROUCHING = "crouching"              # 蹲行
    BACKWARD_WALK = "backward_walk"      # 倒退行走
    SIDESTEP = "sidestep"                # 侧步移动


class TerrainType(Enum):
    """地形类型"""
    FLAT = "flat"               # 平地
    STAIRS = "stairs"           # 楼梯
    SLOPE = "slope"             # 斜坡
    ROUGH = "rough"             # 崎岖地面
    NARROW = "narrow"           # 狭窄通道
    SLIPPERY = "slippery"       # 湿滑地面


class LocomotionSkill(BaseSkill):
    """
    行进技能
    
    能够根据环境和目标自适应选择行进方式。
    """
    
    def __init__(
        self,
        action_manager: Optional[Any] = None,
        **kwargs: Any,
    ):
        super().__init__(
            name="locomotion",
            name_cn="行进",
            category=SkillCategory.MOVEMENT,
            description="根据环境和目标自适应选择行进方式，包括行走、跑步、爬行等",
            action_manager=action_manager,
        )
        self._current_mode: LocomotionMode = LocomotionMode.UPRIGHT_WALK
        
    def get_required_actions(self) -> List[str]:
        """获取行进技能所需的原子动作"""
        return [
            # 行进原子动作
            "locomotion.upright_walk",
            "locomotion.run",
            "locomotion.crawl",
            "locomotion.kneeling_crawl",
            "locomotion.crouch_walk",
            "locomotion.sidestep",
            "locomotion.backward_walk",
            "locomotion.turn",
            "locomotion.stop",
            # 平衡动作
            "balance.maintain",
            "balance.recover",
            # 感知动作
            "perception.scan_terrain",
            "perception.detect_obstacle",
        ]
        
    async def execute(self, context: SkillContext) -> SkillResult:
        """
        执行行进技能
        
        Args:
            context: 执行上下文，包含:
                - target_position: 目标位置 (x, y, z)
                - mode: 行进模式（可选，默认自动选择）
                - speed: 速度 (0.0-1.0)
                - terrain: 地形类型
        """
        params = context.parameters
        actions_executed = []
        
        try:
            target_position = params.get("target_position")
            mode = params.get("mode")
            speed = params.get("speed", 0.5)
            terrain = params.get("terrain", TerrainType.FLAT)
            
            if isinstance(terrain, str):
                terrain = TerrainType(terrain)
            if isinstance(mode, str):
                mode = LocomotionMode(mode)
                
            # 1. 扫描地形
            actions_executed.append("扫描地形")
            detected_terrain = await self._scan_terrain()
            
            # 2. 选择行进模式
            if mode is None:
                mode = self._select_mode(terrain or detected_terrain, speed)
            self._current_mode = mode
            actions_executed.append(f"选择模式: {mode.value}")
            
            self.logger.info(
                f"开始行进: 模式={mode.value}, "
                f"速度={speed}, 目标={target_position}"
            )
            
            # 3. 执行行进
            distance_traveled = 0.0
            while not await self._reached_target(target_position):
                # 动态调整
                obstacle = await self._detect_obstacle()
                if obstacle:
                    actions_executed.append(f"避障: {obstacle}")
                    await self._avoid_obstacle(obstacle)
                    
                # 执行一步
                step_distance = await self._take_step(mode, speed)
                distance_traveled += step_distance
                
                # 检查是否需要切换模式
                new_mode = await self._check_mode_switch(terrain)
                if new_mode != mode:
                    mode = new_mode
                    self._current_mode = mode
                    actions_executed.append(f"切换模式: {mode.value}")
                    
            actions_executed.append("到达目标")
            
            return SkillResult(
                success=True,
                state=SkillState.COMPLETED,
                result_data={
                    "mode_used": mode.value,
                    "distance_traveled": distance_traveled,
                    "final_position": target_position,
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
            
    def _select_mode(
        self,
        terrain: TerrainType,
        speed: float,
    ) -> LocomotionMode:
        """根据地形和速度选择行进模式"""
        # 地形适配
        terrain_modes = {
            TerrainType.FLAT: LocomotionMode.UPRIGHT_WALK,
            TerrainType.STAIRS: LocomotionMode.UPRIGHT_WALK,
            TerrainType.SLOPE: LocomotionMode.CROUCHING,
            TerrainType.ROUGH: LocomotionMode.CRAWLING,
            TerrainType.NARROW: LocomotionMode.SIDESTEP,
            TerrainType.SLIPPERY: LocomotionMode.CROUCHING,
        }
        
        base_mode = terrain_modes.get(terrain, LocomotionMode.UPRIGHT_WALK)
        
        # 速度适配
        if speed > 0.7 and terrain == TerrainType.FLAT:
            return LocomotionMode.RUNNING
        elif speed > 0.5 and terrain == TerrainType.FLAT:
            return LocomotionMode.JOGGING
            
        return base_mode
        
    async def _scan_terrain(self) -> TerrainType:
        """扫描地形"""
        # 调用感知系统
        return TerrainType.FLAT
        
    async def _detect_obstacle(self) -> Optional[str]:
        """检测障碍物"""
        return None
        
    async def _avoid_obstacle(self, obstacle: str) -> None:
        """避障"""
        self.logger.debug(f"避开障碍物: {obstacle}")
        
    async def _reached_target(self, target: Any) -> bool:
        """检查是否到达目标"""
        # 简化实现，实际需要计算位置
        return True
        
    async def _take_step(self, mode: LocomotionMode, speed: float) -> float:
        """执行一步，返回移动距离"""
        # 不同模式的步幅
        step_sizes = {
            LocomotionMode.UPRIGHT_WALK: 0.6,
            LocomotionMode.RUNNING: 1.2,
            LocomotionMode.JOGGING: 0.8,
            LocomotionMode.CRAWLING: 0.3,
            LocomotionMode.KNEELING_CRAWL: 0.25,
            LocomotionMode.CROUCHING: 0.4,
        }
        return step_sizes.get(mode, 0.5) * speed
        
    async def _check_mode_switch(self, terrain: TerrainType) -> LocomotionMode:
        """检查是否需要切换模式"""
        return self._current_mode
