"""
Workspace 管理器

管理 Agent 的工作空间目录和 bootstrap 文件。
借鉴 Moltbot 的设计，每个 Agent 拥有独立的工作空间。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from orb.system.services.logger import LoggerMixin


# Bootstrap 文件默认模板
DEFAULT_TEMPLATES = {
    "AGENTS.md": """# Agent 操作指令

## 核心规则
- 遵循用户指令，保持专注
- 谨慎操作，先思考后行动
- 记录重要信息到记忆中

## 记忆管理
- 每日记忆存储在 memory/ 目录
- 使用 YYYY-MM-DD.md 格式命名
- 定期整理和归档旧记忆

## 工具使用
- 参考 TOOLS.md 了解可用工具
- 优先使用安全的只读操作
- 执行前确认操作的必要性
""",
    
    "SOUL.md": """# Agent 人格定义

## 身份
- 我是一个智能助手
- 我的目标是帮助用户完成任务

## 性格
- 专业、可靠
- 友好、耐心
- 严谨、细致

## 边界
- 不执行危险或有害操作
- 不泄露敏感信息
- 遵守安全策略
""",
    
    "USER.md": """# 用户配置

## 基本信息
- 称呼: 用户
- 偏好语言: 中文

## 交互偏好
- 回复风格: 简洁清晰
- 详细程度: 适中
""",
    
    "IDENTITY.md": """# Agent 身份

## 名称
OpenRoboBrain Agent

## 版本
1.0.0

## 描述
具身智能机器人大脑系统的智能代理
""",
    
    "TOOLS.md": """# 工具使用指南

## 可用工具
本 Agent 可以使用以下工具：

### 文件操作
- read: 读取文件内容
- write: 写入文件内容
- list: 列出目录内容

### 系统操作
- exec: 执行命令（需要权限）

## 使用规范
1. 优先使用只读操作
2. 写入前备份重要文件
3. 执行命令前确认安全性
""",
    
    "HEARTBEAT.md": """# 心跳检查清单

## 定期检查项
- [ ] 系统状态正常
- [ ] 内存使用合理
- [ ] 无挂起任务
""",
    
    "BOOT.md": """# 启动检查清单

## 启动时执行
- 检查工作空间完整性
- 加载配置文件
- 初始化连接
""",
}


@dataclass
class WorkspaceConfig:
    """工作空间配置"""
    root_path: Path
    agent_id: str
    skip_bootstrap: bool = False
    bootstrap_max_chars: int = 20000
    create_if_missing: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BootstrapFile:
    """Bootstrap 文件信息"""
    name: str
    path: Path
    exists: bool
    content: Optional[str] = None
    truncated: bool = False
    char_count: int = 0


class WorkspaceManager(LoggerMixin):
    """
    工作空间管理器
    
    管理 Agent 的独立工作空间，包括：
    - 工作空间目录结构
    - Bootstrap 文件（AGENTS.md, SOUL.md 等）
    - 日常记忆目录
    - 技能目录
    """
    
    # Bootstrap 文件列表（按加载顺序）
    BOOTSTRAP_FILES = [
        "AGENTS.md",
        "SOUL.md", 
        "USER.md",
        "IDENTITY.md",
        "TOOLS.md",
        "HEARTBEAT.md",
        "BOOT.md",
        "BOOTSTRAP.md",
    ]
    
    # 必需的子目录
    REQUIRED_DIRS = [
        "memory",
        "skills",
        "canvas",
    ]
    
    def __init__(self, config: WorkspaceConfig):
        """
        初始化工作空间管理器
        
        Args:
            config: 工作空间配置
        """
        self._config = config
        self._root = config.root_path
        self._agent_id = config.agent_id
        self._initialized = False
        
    @property
    def root(self) -> Path:
        """工作空间根目录"""
        return self._root
        
    @property
    def agent_id(self) -> str:
        """Agent ID"""
        return self._agent_id
        
    @property
    def memory_dir(self) -> Path:
        """记忆目录"""
        return self._root / "memory"
        
    @property
    def skills_dir(self) -> Path:
        """技能目录"""
        return self._root / "skills"
        
    @property
    def canvas_dir(self) -> Path:
        """Canvas UI 目录"""
        return self._root / "canvas"
        
    @classmethod
    def create_workspace_path(cls, base_dir: str, agent_id: str) -> Path:
        """
        创建工作空间路径
        
        Args:
            base_dir: 基础目录（如 ~/OpenRoboBrain）
            agent_id: Agent ID
            
        Returns:
            工作空间路径
        """
        base = Path(base_dir).expanduser()
        if agent_id == "main":
            return base
        return base.parent / f"{base.name}-{agent_id}"
        
    def initialize(self) -> bool:
        """
        初始化工作空间
        
        Returns:
            是否成功
        """
        if self._initialized:
            return True
            
        self.logger.info(f"初始化工作空间: {self._root}")
        
        try:
            # 创建根目录
            if self._config.create_if_missing:
                self._root.mkdir(parents=True, exist_ok=True)
            elif not self._root.exists():
                self.logger.error(f"工作空间不存在: {self._root}")
                return False
                
            # 创建子目录
            for dir_name in self.REQUIRED_DIRS:
                dir_path = self._root / dir_name
                dir_path.mkdir(parents=True, exist_ok=True)
                
            # 创建 bootstrap 文件
            if not self._config.skip_bootstrap:
                self._create_bootstrap_files()
                
            self._initialized = True
            self.logger.info(f"工作空间初始化完成: {self._root}")
            return True
            
        except Exception as e:
            self.logger.error(f"工作空间初始化失败: {e}")
            return False
            
    def _create_bootstrap_files(self) -> None:
        """创建默认的 bootstrap 文件"""
        for filename in self.BOOTSTRAP_FILES:
            file_path = self._root / filename
            
            # 如果文件已存在，跳过
            if file_path.exists():
                continue
                
            # 特殊处理 BOOTSTRAP.md：只在全新工作空间创建
            if filename == "BOOTSTRAP.md":
                # 检查是否有其他 bootstrap 文件存在
                has_other_files = any(
                    (self._root / f).exists() 
                    for f in self.BOOTSTRAP_FILES 
                    if f != "BOOTSTRAP.md"
                )
                if has_other_files:
                    continue
                    
            # 获取模板内容
            template = DEFAULT_TEMPLATES.get(filename)
            if template:
                file_path.write_text(template, encoding="utf-8")
                self.logger.debug(f"创建 bootstrap 文件: {filename}")
                
    def get_bootstrap_file(self, filename: str) -> BootstrapFile:
        """
        获取 bootstrap 文件信息
        
        Args:
            filename: 文件名
            
        Returns:
            Bootstrap 文件信息
        """
        file_path = self._root / filename
        exists = file_path.exists()
        content = None
        truncated = False
        char_count = 0
        
        if exists:
            try:
                full_content = file_path.read_text(encoding="utf-8")
                char_count = len(full_content)
                
                # 检查是否需要截断
                if char_count > self._config.bootstrap_max_chars:
                    content = full_content[:self._config.bootstrap_max_chars]
                    content += f"\n\n[... 文件已截断，完整内容请读取 {filename} ...]"
                    truncated = True
                else:
                    content = full_content
                    
            except Exception as e:
                self.logger.warning(f"读取文件失败 {filename}: {e}")
                
        return BootstrapFile(
            name=filename,
            path=file_path,
            exists=exists,
            content=content,
            truncated=truncated,
            char_count=char_count,
        )
        
    def load_bootstrap_files(self) -> Dict[str, BootstrapFile]:
        """
        加载所有 bootstrap 文件
        
        Returns:
            文件名到 BootstrapFile 的映射
        """
        files = {}
        for filename in self.BOOTSTRAP_FILES:
            files[filename] = self.get_bootstrap_file(filename)
        return files
        
    def get_bootstrap_context(self) -> str:
        """
        获取 bootstrap 上下文（用于注入到 Agent 提示中）
        
        Returns:
            合并后的 bootstrap 内容
        """
        context_parts = []
        
        for filename in self.BOOTSTRAP_FILES:
            file_info = self.get_bootstrap_file(filename)
            
            if file_info.exists and file_info.content:
                context_parts.append(f"=== {filename} ===\n{file_info.content}")
            else:
                # 标记缺失的文件
                context_parts.append(f"=== {filename} ===\n[文件缺失]")
                
        return "\n\n".join(context_parts)
        
    def get_today_memory_path(self) -> Path:
        """
        获取今日记忆文件路径
        
        Returns:
            今日记忆文件路径
        """
        today = datetime.now().strftime("%Y-%m-%d")
        return self.memory_dir / f"{today}.md"
        
    def get_memory_files(self, days: int = 7) -> List[Path]:
        """
        获取最近的记忆文件
        
        Args:
            days: 天数
            
        Returns:
            记忆文件路径列表
        """
        files = []
        if not self.memory_dir.exists():
            return files
            
        # 获取所有 markdown 文件
        all_files = sorted(
            self.memory_dir.glob("*.md"),
            key=lambda p: p.name,
            reverse=True,
        )
        
        return all_files[:days]
        
    def write_memory(self, content: str, append: bool = True) -> bool:
        """
        写入今日记忆
        
        Args:
            content: 内容
            append: 是否追加
            
        Returns:
            是否成功
        """
        try:
            memory_path = self.get_today_memory_path()
            
            if append and memory_path.exists():
                existing = memory_path.read_text(encoding="utf-8")
                content = existing + "\n\n" + content
                
            memory_path.write_text(content, encoding="utf-8")
            return True
            
        except Exception as e:
            self.logger.error(f"写入记忆失败: {e}")
            return False
            
    def list_skills(self) -> List[str]:
        """
        列出工作空间中的技能
        
        Returns:
            技能名称列表
        """
        skills = []
        if not self.skills_dir.exists():
            return skills
            
        for item in self.skills_dir.iterdir():
            if item.is_dir() or item.suffix in [".py", ".yaml", ".json"]:
                skills.append(item.stem)
                
        return skills
        
    def update_bootstrap_file(self, filename: str, content: str) -> bool:
        """
        更新 bootstrap 文件
        
        Args:
            filename: 文件名
            content: 新内容
            
        Returns:
            是否成功
        """
        if filename not in self.BOOTSTRAP_FILES:
            self.logger.warning(f"未知的 bootstrap 文件: {filename}")
            return False
            
        try:
            file_path = self._root / filename
            file_path.write_text(content, encoding="utf-8")
            self.logger.info(f"更新 bootstrap 文件: {filename}")
            return True
            
        except Exception as e:
            self.logger.error(f"更新文件失败 {filename}: {e}")
            return False
            
    def delete_bootstrap_file(self, filename: str) -> bool:
        """
        删除 bootstrap 文件
        
        Args:
            filename: 文件名
            
        Returns:
            是否成功
        """
        try:
            file_path = self._root / filename
            if file_path.exists():
                file_path.unlink()
                self.logger.info(f"删除 bootstrap 文件: {filename}")
            return True
            
        except Exception as e:
            self.logger.error(f"删除文件失败 {filename}: {e}")
            return False
            
    def get_workspace_info(self) -> Dict[str, Any]:
        """
        获取工作空间信息
        
        Returns:
            工作空间信息
        """
        bootstrap_files = self.load_bootstrap_files()
        
        return {
            "agent_id": self._agent_id,
            "root_path": str(self._root),
            "initialized": self._initialized,
            "bootstrap_files": {
                name: {
                    "exists": info.exists,
                    "char_count": info.char_count,
                    "truncated": info.truncated,
                }
                for name, info in bootstrap_files.items()
            },
            "memory_files_count": len(self.get_memory_files(days=30)),
            "skills": self.list_skills(),
            "directories": {
                "memory": self.memory_dir.exists(),
                "skills": self.skills_dir.exists(),
                "canvas": self.canvas_dir.exists(),
            },
        }
        
    def cleanup(self) -> None:
        """清理工作空间（仅清理临时文件）"""
        # 可以在这里添加临时文件清理逻辑
        pass


# 便捷函数
def get_default_workspace_root() -> Path:
    """
    获取默认工作空间根目录
    
    Returns:
        默认根目录路径
    """
    # 优先使用环境变量
    env_path = os.environ.get("ORB_WORKSPACE")
    if env_path:
        return Path(env_path).expanduser()
        
    # 默认使用 ~/OpenRoboBrain
    return Path.home() / "OpenRoboBrain"


def create_workspace_manager(
    agent_id: str,
    base_dir: Optional[str] = None,
    **kwargs,
) -> WorkspaceManager:
    """
    创建工作空间管理器
    
    Args:
        agent_id: Agent ID
        base_dir: 基础目录
        **kwargs: 其他配置参数
        
    Returns:
        WorkspaceManager 实例
    """
    if base_dir is None:
        base_dir = str(get_default_workspace_root())
        
    root_path = WorkspaceManager.create_workspace_path(base_dir, agent_id)
    
    config = WorkspaceConfig(
        root_path=root_path,
        agent_id=agent_id,
        **kwargs,
    )
    
    return WorkspaceManager(config)
