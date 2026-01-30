"""
技能热加载 Watcher

监听 SKILL.md 文件变化，自动重新加载技能。

借鉴 OpenClaw/Moltbot 的设计：
- 文件监听
- Debounce 防抖
- 变化回调
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from kaibrain.system.services.logger import LoggerMixin, get_logger
from kaibrain.skills.loader import SkillLoader, AgentSkill

logger = get_logger(__name__)


class FileChangeType(Enum):
    """文件变化类型"""
    CREATED = "created"
    MODIFIED = "modified"
    DELETED = "deleted"


@dataclass
class FileChange:
    """文件变化事件"""
    path: Path
    change_type: FileChangeType
    timestamp: float = field(default_factory=time.time)


# 回调类型
SkillChangeCallback = Callable[[AgentSkill, FileChangeType], None]
AsyncSkillChangeCallback = Callable[[AgentSkill, FileChangeType], Any]


class SkillWatcher(LoggerMixin):
    """
    技能文件监听器
    
    监听 SKILL.md 文件变化，自动重新加载技能。
    支持 debounce 防抖。
    """
    
    def __init__(
        self,
        loader: SkillLoader,
        debounce_ms: int = 500,
        poll_interval: float = 1.0,
    ):
        """
        初始化技能监听器
        
        Args:
            loader: 技能加载器
            debounce_ms: 防抖延迟 (毫秒)
            poll_interval: 轮询间隔 (秒)
        """
        self._loader = loader
        self._debounce_ms = debounce_ms
        self._poll_interval = poll_interval
        
        self._running = False
        self._watch_task: Optional[asyncio.Task] = None
        
        # 文件状态缓存
        self._file_mtimes: Dict[str, float] = {}
        self._pending_changes: Dict[str, FileChange] = {}
        self._debounce_task: Optional[asyncio.Task] = None
        
        # 回调
        self._callbacks: List[AsyncSkillChangeCallback] = []
        
    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        return self._running
        
    def add_callback(self, callback: AsyncSkillChangeCallback) -> None:
        """添加变化回调"""
        self._callbacks.append(callback)
        
    def remove_callback(self, callback: AsyncSkillChangeCallback) -> bool:
        """移除变化回调"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
            return True
        return False
        
    async def start(self) -> None:
        """启动监听"""
        if self._running:
            return
            
        self._running = True
        
        # 初始化文件状态
        self._initialize_file_states()
        
        # 启动监听任务
        self._watch_task = asyncio.create_task(self._watch_loop())
        self.logger.info("技能监听器已启动")
        
    async def stop(self) -> None:
        """停止监听"""
        if not self._running:
            return
            
        self._running = False
        
        if self._watch_task:
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass
            self._watch_task = None
            
        if self._debounce_task:
            self._debounce_task.cancel()
            try:
                await self._debounce_task
            except asyncio.CancelledError:
                pass
            self._debounce_task = None
            
        self.logger.info("技能监听器已停止")
        
    def _initialize_file_states(self) -> None:
        """初始化文件状态"""
        self._file_mtimes.clear()
        
        for skill in self._loader.skills.values():
            if skill.path.exists():
                self._file_mtimes[str(skill.path)] = skill.path.stat().st_mtime
                
    def _get_watch_directories(self) -> List[Path]:
        """获取需要监听的目录"""
        dirs = []
        
        stats = self._loader.get_stats()
        search_paths = stats.get("search_paths", {})
        
        for key, path_str in search_paths.items():
            if path_str:
                path = Path(path_str)
                if path.exists():
                    dirs.append(path)
                    
        return dirs
        
    async def _watch_loop(self) -> None:
        """监听循环"""
        while self._running:
            try:
                # 扫描文件变化
                changes = self._scan_changes()
                
                if changes:
                    # 添加到待处理队列
                    for change in changes:
                        self._pending_changes[str(change.path)] = change
                        
                    # 触发 debounce
                    self._schedule_debounce()
                    
                await asyncio.sleep(self._poll_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"监听循环错误: {e}")
                await asyncio.sleep(self._poll_interval)
                
    def _scan_changes(self) -> List[FileChange]:
        """扫描文件变化"""
        changes = []
        current_files: Set[str] = set()
        
        # 扫描所有目录
        for directory in self._get_watch_directories():
            for skill_file in directory.glob("**/SKILL.md"):
                path_str = str(skill_file)
                current_files.add(path_str)
                
                if skill_file.exists():
                    mtime = skill_file.stat().st_mtime
                    
                    if path_str not in self._file_mtimes:
                        # 新文件
                        changes.append(FileChange(
                            path=skill_file,
                            change_type=FileChangeType.CREATED,
                        ))
                        self._file_mtimes[path_str] = mtime
                        
                    elif self._file_mtimes[path_str] != mtime:
                        # 文件修改
                        changes.append(FileChange(
                            path=skill_file,
                            change_type=FileChangeType.MODIFIED,
                        ))
                        self._file_mtimes[path_str] = mtime
                        
        # 检查删除的文件
        deleted = set(self._file_mtimes.keys()) - current_files
        for path_str in deleted:
            changes.append(FileChange(
                path=Path(path_str),
                change_type=FileChangeType.DELETED,
            ))
            del self._file_mtimes[path_str]
            
        return changes
        
    def _schedule_debounce(self) -> None:
        """调度 debounce 处理"""
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()
            
        self._debounce_task = asyncio.create_task(self._debounce_handler())
        
    async def _debounce_handler(self) -> None:
        """Debounce 处理器"""
        await asyncio.sleep(self._debounce_ms / 1000.0)
        
        # 处理所有待处理的变化
        pending = self._pending_changes.copy()
        self._pending_changes.clear()
        
        for path_str, change in pending.items():
            await self._handle_change(change)
            
    async def _handle_change(self, change: FileChange) -> None:
        """处理单个文件变化"""
        self.logger.info(f"技能文件变化: {change.path.name} ({change.change_type.value})")
        
        skill: Optional[AgentSkill] = None
        
        if change.change_type == FileChangeType.DELETED:
            # 卸载技能
            skill_id = change.path.stem
            existing_skill = self._loader.get_skill(skill_id)
            if existing_skill:
                skill = existing_skill
                self._loader.unload_skill(skill_id)
                
        elif change.change_type == FileChangeType.CREATED:
            # 加载新技能
            skill = self._loader.load_skill(change.path)
            
        elif change.change_type == FileChangeType.MODIFIED:
            # 重新加载技能
            skill_id = change.path.stem
            existing_skill = self._loader.get_skill(skill_id)
            if existing_skill:
                skill = self._loader.reload_skill(skill_id)
            else:
                skill = self._loader.load_skill(change.path)
                
        # 触发回调
        if skill:
            await self._notify_callbacks(skill, change.change_type)
            
    async def _notify_callbacks(
        self,
        skill: AgentSkill,
        change_type: FileChangeType,
    ) -> None:
        """通知回调"""
        for callback in self._callbacks:
            try:
                result = callback(skill, change_type)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                self.logger.error(f"回调执行失败: {e}")
                
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "running": self._running,
            "watched_files": len(self._file_mtimes),
            "pending_changes": len(self._pending_changes),
            "callbacks": len(self._callbacks),
            "debounce_ms": self._debounce_ms,
            "poll_interval": self._poll_interval,
        }


class SkillWatcherManager(LoggerMixin):
    """
    技能监听管理器
    
    管理 SkillLoader 和 SkillWatcher 的生命周期。
    """
    
    def __init__(
        self,
        workspace_dir: Optional[Path] = None,
        local_dir: Optional[Path] = None,
        bundled_dir: Optional[Path] = None,
        auto_start: bool = False,
    ):
        """
        初始化管理器
        
        Args:
            workspace_dir: 工作空间目录
            local_dir: 本地目录
            bundled_dir: 内置目录
            auto_start: 是否自动启动监听
        """
        from kaibrain.skills.loader import create_skill_loader
        
        self._loader = create_skill_loader(
            workspace_dir=workspace_dir,
            local_dir=local_dir,
            bundled_dir=bundled_dir,
        )
        self._watcher = SkillWatcher(self._loader)
        self._auto_start = auto_start
        
    @property
    def loader(self) -> SkillLoader:
        """技能加载器"""
        return self._loader
        
    @property
    def watcher(self) -> SkillWatcher:
        """技能监听器"""
        return self._watcher
        
    async def initialize(self) -> int:
        """
        初始化：加载所有技能
        
        Returns:
            加载的技能数量
        """
        count = self._loader.load_all()
        
        if self._auto_start:
            await self._watcher.start()
            
        return count
        
    async def shutdown(self) -> None:
        """关闭"""
        await self._watcher.stop()
        
    def on_skill_change(self, callback: AsyncSkillChangeCallback) -> None:
        """注册技能变化回调"""
        self._watcher.add_callback(callback)
        
    def get_skill(self, skill_id: str) -> Optional[AgentSkill]:
        """获取技能"""
        return self._loader.get_skill(skill_id)
        
    def get_all_skills(self) -> List[AgentSkill]:
        """获取所有技能"""
        return list(self._loader.skills.values())
        
    def get_skills_prompt(self, skill_ids: Optional[List[str]] = None) -> str:
        """获取技能 prompt"""
        return self._loader.get_all_prompts(skill_ids)


# ============== 便捷函数 ==============

def create_skill_watcher(
    loader: SkillLoader,
    debounce_ms: int = 500,
    poll_interval: float = 1.0,
) -> SkillWatcher:
    """
    创建技能监听器
    
    Args:
        loader: 技能加载器
        debounce_ms: 防抖延迟
        poll_interval: 轮询间隔
        
    Returns:
        SkillWatcher 实例
    """
    return SkillWatcher(
        loader=loader,
        debounce_ms=debounce_ms,
        poll_interval=poll_interval,
    )


def create_skill_manager(
    workspace_dir: Optional[Path] = None,
    local_dir: Optional[Path] = None,
    bundled_dir: Optional[Path] = None,
    auto_start: bool = False,
) -> SkillWatcherManager:
    """
    创建技能管理器
    
    Args:
        workspace_dir: 工作空间目录
        local_dir: 本地目录
        bundled_dir: 内置目录
        auto_start: 是否自动启动监听
        
    Returns:
        SkillWatcherManager 实例
    """
    return SkillWatcherManager(
        workspace_dir=workspace_dir,
        local_dir=local_dir,
        bundled_dir=bundled_dir,
        auto_start=auto_start,
    )
