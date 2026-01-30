"""
技能层 (Skill Layer)

对外暴露的语义化技能接口。技能是高层次的、有语义的能力，
如烹饪、学习、跑步、清洁等，由多个原子动作组合而成。

技能分类：
- daily_life: 日常生活技能（烹饪、清洁、整理）
- movement: 运动技能（行进、游泳、攀爬）
- cognitive: 认知技能（学习、推理、规划）
- social: 社交技能（对话、情感识别）

技能与原子动作的关系：
- 技能是高层语义化能力，面向应用
- 原子动作是底层执行单元，位于中间件层
- 技能通过编排多个原子动作来完成复杂任务

Agent 技能系统 (借鉴 OpenClaw/Moltbot):
- SKILL.md 格式的技能文件
- 优先级加载 (workspace > local > bundled)
- Gating 机制
- 热加载支持
"""

from kaibrain.skills.base import (
    BaseSkill,
    SkillLevel,
    SkillCategory,
    SkillState,
    SkillInfo,
    SkillContext,
    SkillResult,
)
from kaibrain.skills.registry import SkillRegistry
from kaibrain.skills.loader import (
    SkillLoader,
    SkillParser,
    AgentSkill,
    SkillMetadata,
    SkillRequirements,
    SkillSource,
    create_skill_loader,
    parse_skill_file,
)
from kaibrain.skills.watcher import (
    SkillWatcher,
    SkillWatcherManager,
    FileChange,
    FileChangeType,
    create_skill_watcher,
    create_skill_manager,
)

__all__ = [
    # 基础技能类
    "BaseSkill",
    "SkillLevel",
    "SkillCategory",
    "SkillState",
    "SkillInfo",
    "SkillContext",
    "SkillResult",
    "SkillRegistry",
    # Agent 技能系统
    "SkillLoader",
    "SkillParser",
    "AgentSkill",
    "SkillMetadata",
    "SkillRequirements",
    "SkillSource",
    "create_skill_loader",
    "parse_skill_file",
    # 热加载
    "SkillWatcher",
    "SkillWatcherManager",
    "FileChange",
    "FileChangeType",
    "create_skill_watcher",
    "create_skill_manager",
]
