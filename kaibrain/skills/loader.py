"""
SKILL.md 解析器和加载器

借鉴 OpenClaw/Moltbot 的 AgentSkills 设计，支持：
- YAML frontmatter + Markdown 格式的技能文件
- 优先级加载 (workspace > local > bundled)
- Gating 机制 (requires.bins, requires.env, requires.config, os)
- 技能热加载
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import yaml

from kaibrain.system.services.logger import LoggerMixin, get_logger

logger = get_logger(__name__)


class SkillSource(Enum):
    """技能来源"""
    WORKSPACE = "workspace"  # 工作空间 (最高优先级)
    LOCAL = "local"          # 本地用户目录
    BUNDLED = "bundled"      # 内置


@dataclass
class SkillRequirements:
    """技能加载要求"""
    bins: List[str] = field(default_factory=list)   # 需要的可执行文件
    env: List[str] = field(default_factory=list)    # 需要的环境变量
    config: List[str] = field(default_factory=list) # 需要的配置项
    os: List[str] = field(default_factory=list)     # 限定的操作系统
    
    def check(self) -> tuple[bool, str]:
        """
        检查要求是否满足
        
        Returns:
            (是否满足, 原因)
        """
        import sys
        import platform
        
        # 检查操作系统
        if self.os:
            current_os = platform.system().lower()
            os_aliases = {
                "windows": ["windows", "win32", "win"],
                "linux": ["linux", "linux2"],
                "darwin": ["darwin", "macos", "osx", "mac"],
            }
            
            matched = False
            for os_name in self.os:
                os_name_lower = os_name.lower()
                for canonical, aliases in os_aliases.items():
                    if os_name_lower in aliases and current_os.lower() == canonical:
                        matched = True
                        break
                if matched:
                    break
                    
            if not matched:
                return False, f"操作系统不匹配: 需要 {self.os}, 当前 {current_os}"
        
        # 检查可执行文件
        for bin_name in self.bins:
            if not shutil.which(bin_name):
                return False, f"未找到可执行文件: {bin_name}"
                
        # 检查环境变量
        for env_name in self.env:
            if env_name not in os.environ:
                return False, f"缺少环境变量: {env_name}"
                
        # 检查配置项（需要配置中心支持）
        # TODO: 与 ConfigCenter 集成
        
        return True, ""


@dataclass
class SkillMetadata:
    """技能元数据 (从 YAML frontmatter 解析)"""
    name: str
    description: str = ""
    version: str = "1.0.0"
    author: str = ""
    tags: List[str] = field(default_factory=list)
    requires: SkillRequirements = field(default_factory=SkillRequirements)
    tools: List[str] = field(default_factory=list)  # 相关工具
    priority: int = 0  # 优先级 (用于排序)
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SkillMetadata:
        """从字典创建"""
        requires_data = data.get("metadata", {}).get("kaibrain", {}).get("requires", {})
        # 兼容 moltbot 格式
        if not requires_data:
            requires_data = data.get("metadata", {}).get("moltbot", {}).get("requires", {})
            
        requires = SkillRequirements(
            bins=requires_data.get("bins", []),
            env=requires_data.get("env", []),
            config=requires_data.get("config", []),
            os=requires_data.get("os", []),
        )
        
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            author=data.get("author", ""),
            tags=data.get("tags", []),
            requires=requires,
            tools=data.get("tools", []),
            priority=data.get("priority", 0),
            enabled=data.get("enabled", True),
            metadata=data.get("metadata", {}),
        )


@dataclass
class AgentSkill:
    """Agent 技能 (从 SKILL.md 加载)"""
    id: str                         # 技能 ID (通常是文件名)
    path: Path                      # 文件路径
    source: SkillSource             # 来源
    metadata: SkillMetadata         # 元数据
    instructions: str               # 技能指令 (Markdown 正文)
    loaded_at: str = ""             # 加载时间
    
    @property
    def name(self) -> str:
        """技能名称"""
        return self.metadata.name or self.id
        
    @property
    def description(self) -> str:
        """技能描述"""
        return self.metadata.description
        
    def can_load(self) -> tuple[bool, str]:
        """
        检查技能是否可以加载
        
        Returns:
            (可以加载, 原因)
        """
        if not self.metadata.enabled:
            return False, "技能已禁用"
            
        return self.metadata.requires.check()
        
    def to_prompt(self) -> str:
        """
        转换为 prompt 格式
        
        Returns:
            用于注入 LLM 的 prompt
        """
        lines = [f"## Skill: {self.name}"]
        
        if self.description:
            lines.append(f"\n{self.description}")
            
        if self.metadata.tools:
            lines.append(f"\nRelated tools: {', '.join(self.metadata.tools)}")
            
        lines.append(f"\n### Instructions\n\n{self.instructions}")
        
        return "\n".join(lines)


class SkillParser(LoggerMixin):
    """
    SKILL.md 文件解析器
    
    解析 YAML frontmatter + Markdown 格式的技能文件。
    """
    
    # YAML frontmatter 正则
    FRONTMATTER_PATTERN = re.compile(
        r'^---\s*\n(.*?)\n---\s*\n',
        re.DOTALL
    )
    
    def parse(self, content: str, skill_id: str = "") -> tuple[SkillMetadata, str]:
        """
        解析 SKILL.md 内容
        
        Args:
            content: 文件内容
            skill_id: 技能 ID
            
        Returns:
            (元数据, 指令正文)
        """
        metadata = SkillMetadata(name=skill_id)
        instructions = content
        
        # 尝试解析 YAML frontmatter
        match = self.FRONTMATTER_PATTERN.match(content)
        if match:
            try:
                yaml_content = match.group(1)
                yaml_data = yaml.safe_load(yaml_content) or {}
                metadata = SkillMetadata.from_dict(yaml_data)
                if not metadata.name:
                    metadata.name = skill_id
                    
                # 提取正文
                instructions = content[match.end():].strip()
                
            except yaml.YAMLError as e:
                self.logger.warning(f"解析 YAML frontmatter 失败: {e}")
                
        return metadata, instructions
        
    def parse_file(self, path: Path) -> Optional[AgentSkill]:
        """
        解析 SKILL.md 文件
        
        Args:
            path: 文件路径
            
        Returns:
            AgentSkill 或 None
        """
        if not path.exists():
            return None
            
        try:
            content = path.read_text(encoding="utf-8")
            skill_id = path.stem  # 使用文件名作为 ID
            
            metadata, instructions = self.parse(content, skill_id)
            
            # 确定来源
            source = self._determine_source(path)
            
            from datetime import datetime
            return AgentSkill(
                id=skill_id,
                path=path,
                source=source,
                metadata=metadata,
                instructions=instructions,
                loaded_at=datetime.now().isoformat(),
            )
            
        except Exception as e:
            self.logger.error(f"解析技能文件失败 {path}: {e}")
            return None
            
    def _determine_source(self, path: Path) -> SkillSource:
        """确定技能来源"""
        path_str = str(path).lower()
        
        # 检查是否在工作空间
        cwd = os.getcwd().lower()
        if path_str.startswith(cwd):
            return SkillSource.WORKSPACE
            
        # 检查是否在用户目录
        home = os.path.expanduser("~").lower()
        if path_str.startswith(os.path.join(home, ".kaibrain")):
            return SkillSource.LOCAL
            
        return SkillSource.BUNDLED


class SkillLoader(LoggerMixin):
    """
    技能加载器
    
    支持从多个位置加载技能，按优先级合并：
    1. workspace/skills/ (最高)
    2. ~/.kaibrain/skills/
    3. bundled skills (最低)
    """
    
    def __init__(
        self,
        workspace_dir: Optional[Path] = None,
        local_dir: Optional[Path] = None,
        bundled_dir: Optional[Path] = None,
    ):
        """
        初始化技能加载器
        
        Args:
            workspace_dir: 工作空间技能目录
            local_dir: 本地技能目录 (默认 ~/.kaibrain/skills)
            bundled_dir: 内置技能目录
        """
        self._workspace_dir = workspace_dir
        self._local_dir = local_dir or Path.home() / ".kaibrain" / "skills"
        self._bundled_dir = bundled_dir
        
        self._parser = SkillParser()
        self._skills: Dict[str, AgentSkill] = {}
        self._load_errors: Dict[str, str] = {}
        
    @property
    def skills(self) -> Dict[str, AgentSkill]:
        """已加载的技能"""
        return self._skills.copy()
        
    @property
    def skill_count(self) -> int:
        """技能数量"""
        return len(self._skills)
        
    def set_workspace_dir(self, path: Path) -> None:
        """设置工作空间目录"""
        self._workspace_dir = path
        
    def load_all(self) -> int:
        """
        加载所有技能
        
        按优先级从低到高加载，高优先级覆盖低优先级。
        
        Returns:
            加载的技能数量
        """
        self._skills.clear()
        self._load_errors.clear()
        
        # 按优先级顺序加载 (低 -> 高)
        for skill_dir, source in [
            (self._bundled_dir, SkillSource.BUNDLED),
            (self._local_dir, SkillSource.LOCAL),
            (self._workspace_dir, SkillSource.WORKSPACE),
        ]:
            if skill_dir and skill_dir.exists():
                self._load_from_dir(skill_dir, source)
                
        self.logger.info(f"加载了 {len(self._skills)} 个技能")
        return len(self._skills)
        
    def _load_from_dir(self, directory: Path, source: SkillSource) -> int:
        """从目录加载技能"""
        count = 0
        
        for skill_file in directory.glob("**/*.md"):
            # 跳过非 SKILL.md 文件
            if skill_file.name.upper() != "SKILL.MD":
                continue
                
            skill = self._parser.parse_file(skill_file)
            if skill:
                skill.source = source
                
                # 检查是否可以加载
                can_load, reason = skill.can_load()
                if can_load:
                    self._skills[skill.id] = skill
                    count += 1
                else:
                    self._load_errors[skill.id] = reason
                    self.logger.debug(f"跳过技能 {skill.id}: {reason}")
                    
        return count
        
    def load_skill(self, path: Path) -> Optional[AgentSkill]:
        """
        加载单个技能
        
        Args:
            path: 技能文件路径
            
        Returns:
            AgentSkill 或 None
        """
        skill = self._parser.parse_file(path)
        if skill:
            can_load, reason = skill.can_load()
            if can_load:
                self._skills[skill.id] = skill
                return skill
            else:
                self._load_errors[skill.id] = reason
                self.logger.warning(f"无法加载技能 {skill.id}: {reason}")
        return None
        
    def unload_skill(self, skill_id: str) -> bool:
        """
        卸载技能
        
        Args:
            skill_id: 技能 ID
            
        Returns:
            是否成功
        """
        if skill_id in self._skills:
            del self._skills[skill_id]
            return True
        return False
        
    def reload_skill(self, skill_id: str) -> Optional[AgentSkill]:
        """
        重新加载技能
        
        Args:
            skill_id: 技能 ID
            
        Returns:
            重新加载的技能
        """
        if skill_id in self._skills:
            path = self._skills[skill_id].path
            self.unload_skill(skill_id)
            return self.load_skill(path)
        return None
        
    def get_skill(self, skill_id: str) -> Optional[AgentSkill]:
        """
        获取技能
        
        Args:
            skill_id: 技能 ID
            
        Returns:
            AgentSkill 或 None
        """
        return self._skills.get(skill_id)
        
    def get_skills_by_tag(self, tag: str) -> List[AgentSkill]:
        """
        通过标签获取技能
        
        Args:
            tag: 标签
            
        Returns:
            技能列表
        """
        return [
            skill for skill in self._skills.values()
            if tag in skill.metadata.tags
        ]
        
    def get_skills_for_tools(self, tools: List[str]) -> List[AgentSkill]:
        """
        获取与指定工具相关的技能
        
        Args:
            tools: 工具列表
            
        Returns:
            技能列表
        """
        tool_set = set(tools)
        return [
            skill for skill in self._skills.values()
            if tool_set & set(skill.metadata.tools)
        ]
        
    def get_all_prompts(self, skill_ids: Optional[List[str]] = None) -> str:
        """
        获取所有技能的 prompt
        
        Args:
            skill_ids: 技能 ID 列表 (None 表示所有)
            
        Returns:
            合并的 prompt
        """
        prompts = []
        
        skills = self._skills.values()
        if skill_ids:
            skills = [self._skills[sid] for sid in skill_ids if sid in self._skills]
            
        # 按优先级排序
        skills = sorted(skills, key=lambda s: s.metadata.priority, reverse=True)
        
        for skill in skills:
            prompts.append(skill.to_prompt())
            
        return "\n\n---\n\n".join(prompts)
        
    def get_load_errors(self) -> Dict[str, str]:
        """获取加载错误"""
        return self._load_errors.copy()
        
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        source_counts = {}
        for source in SkillSource:
            source_counts[source.value] = sum(
                1 for s in self._skills.values() if s.source == source
            )
            
        return {
            "total_skills": len(self._skills),
            "source_counts": source_counts,
            "load_errors": len(self._load_errors),
            "search_paths": {
                "workspace": str(self._workspace_dir) if self._workspace_dir else None,
                "local": str(self._local_dir),
                "bundled": str(self._bundled_dir) if self._bundled_dir else None,
            },
        }


# ============== 便捷函数 ==============

def create_skill_loader(
    workspace_dir: Optional[Path] = None,
    local_dir: Optional[Path] = None,
    bundled_dir: Optional[Path] = None,
) -> SkillLoader:
    """
    创建技能加载器
    
    Args:
        workspace_dir: 工作空间技能目录
        local_dir: 本地技能目录
        bundled_dir: 内置技能目录
        
    Returns:
        SkillLoader 实例
    """
    return SkillLoader(
        workspace_dir=workspace_dir,
        local_dir=local_dir,
        bundled_dir=bundled_dir,
    )


def parse_skill_file(path: Path) -> Optional[AgentSkill]:
    """
    解析技能文件
    
    Args:
        path: 文件路径
        
    Returns:
        AgentSkill 或 None
    """
    parser = SkillParser()
    return parser.parse_file(path)


def check_skill_requirements(skill: AgentSkill) -> tuple[bool, str]:
    """
    检查技能要求
    
    Args:
        skill: 技能
        
    Returns:
        (是否满足, 原因)
    """
    return skill.can_load()
