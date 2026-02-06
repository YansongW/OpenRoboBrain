"""
Subagent 终止机制测试

测试框架修复：
- 任务引用存储
- stop_spawn() 真正取消任务
- 批量取消
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from orb.agent.subagent.spawn import (
    SubAgentSpawner,
    SpawnRequest,
    SpawnResult,
    SpawnStatus,
)
from orb.agent.subagent.concurrency import ConcurrencyController


class MockConcurrencyController:
    """模拟并发控制器"""
    
    async def submit(self, coro, lane_id: str = "default"):
        """提交任务"""
        pass  # spawn 现在直接创建任务，不通过控制器


class MockSessionStore:
    """模拟会话存储"""
    
    async def create_session(self, **kwargs):
        """创建会话"""
        session = MagicMock()
        session.session_id = "mock_session_id"
        return session
    
    async def close_session(self, session_id: str):
        """关闭会话"""
        pass
    
    async def archive_session(self, session_id: str):
        """归档会话"""
        pass


class MockAgentRuntime:
    """模拟 Agent 运行时"""
    
    def __init__(self, execution_time: float = 0.1):
        self.execution_time = execution_time
        self.run_count = 0
    
    async def run(self, **kwargs):
        """执行"""
        self.run_count += 1
        await asyncio.sleep(self.execution_time)
        
        result = MagicMock()
        result.run_id = "mock_run_id"
        result.response = "mock response"
        result.tokens_used = 100
        result.status = "success"
        result.error = None
        return result


class TestSubAgentSpawnerInit:
    """SubAgentSpawner 初始化测试"""
    
    def test_init_with_task_tracking(self):
        """测试初始化包含任务跟踪"""
        spawner = SubAgentSpawner(
            concurrency_controller=MockConcurrencyController(),
        )
        
        assert hasattr(spawner, "_spawn_tasks")
        assert hasattr(spawner, "_task_lock")
        assert spawner._cancelled_spawns == 0


class TestSubAgentSpawn:
    """SubAgentSpawner 派生测试"""
    
    @pytest.fixture
    def spawner(self) -> SubAgentSpawner:
        """创建派生器"""
        return SubAgentSpawner(
            concurrency_controller=MockConcurrencyController(),
            enable_announce=False,
        )
    
    @pytest.mark.asyncio
    async def test_spawn_stores_task_reference(self, spawner: SubAgentSpawner):
        """测试派生时存储任务引用"""
        request = SpawnRequest(
            task="test task",
            parent_agent_id="parent",
            parent_session_id="parent_session",
        )
        
        runtime = MockAgentRuntime(execution_time=1.0)  # 长时间执行
        session_store = MockSessionStore()
        
        result = await spawner.spawn(request, runtime, session_store)
        
        # 应该存储了任务引用
        assert result.spawn_id in spawner._spawn_tasks
        
        # 清理
        await spawner.stop_spawn(result.spawn_id)
        
    @pytest.mark.asyncio
    async def test_task_reference_cleaned_after_completion(self, spawner: SubAgentSpawner):
        """测试任务完成后引用被清理"""
        request = SpawnRequest(
            task="quick task",
            parent_agent_id="parent",
            parent_session_id="parent_session",
        )
        
        runtime = MockAgentRuntime(execution_time=0.05)  # 快速完成
        session_store = MockSessionStore()
        
        result = await spawner.spawn(request, runtime, session_store)
        
        # 等待完成
        await asyncio.sleep(0.2)
        
        # 任务引用应该被清理
        assert result.spawn_id not in spawner._spawn_tasks


class TestSubAgentStop:
    """SubAgentSpawner 停止测试"""
    
    @pytest.fixture
    def spawner(self) -> SubAgentSpawner:
        """创建派生器"""
        return SubAgentSpawner(
            concurrency_controller=MockConcurrencyController(),
            enable_announce=False,
        )
    
    @pytest.mark.asyncio
    async def test_stop_spawn_cancels_running_task(self, spawner: SubAgentSpawner):
        """测试 stop_spawn 取消运行中的任务"""
        request = SpawnRequest(
            task="long task",
            parent_agent_id="parent",
            parent_session_id="parent_session",
        )
        
        runtime = MockAgentRuntime(execution_time=10.0)  # 长时间执行
        session_store = MockSessionStore()
        
        result = await spawner.spawn(request, runtime, session_store)
        
        # 确保任务正在运行
        await asyncio.sleep(0.1)
        assert result.status == SpawnStatus.RUNNING
        
        # 取消任务
        success = await spawner.stop_spawn(result.spawn_id)
        
        assert success is True
        assert result.status == SpawnStatus.CANCELLED
        
    @pytest.mark.asyncio
    async def test_stop_spawn_returns_false_for_nonexistent(self, spawner: SubAgentSpawner):
        """测试取消不存在的派生返回 False"""
        success = await spawner.stop_spawn("nonexistent_id")
        assert success is False
        
    @pytest.mark.asyncio
    async def test_stop_spawn_increments_cancelled_count(self, spawner: SubAgentSpawner):
        """测试取消增加计数"""
        request = SpawnRequest(
            task="task",
            parent_agent_id="parent",
            parent_session_id="parent_session",
        )
        
        runtime = MockAgentRuntime(execution_time=10.0)
        session_store = MockSessionStore()
        
        result = await spawner.spawn(request, runtime, session_store)
        await asyncio.sleep(0.1)
        
        initial_count = spawner._cancelled_spawns
        await spawner.stop_spawn(result.spawn_id)
        
        assert spawner._cancelled_spawns == initial_count + 1
        
    @pytest.mark.asyncio
    async def test_stop_spawn_with_force(self, spawner: SubAgentSpawner):
        """测试强制取消"""
        request = SpawnRequest(
            task="task",
            parent_agent_id="parent",
            parent_session_id="parent_session",
        )
        
        runtime = MockAgentRuntime(execution_time=0.05)
        session_store = MockSessionStore()
        
        result = await spawner.spawn(request, runtime, session_store)
        
        # 等待完成
        await asyncio.sleep(0.2)
        
        # 已完成的任务，使用 force 也应该返回 True
        success = await spawner.stop_spawn(result.spawn_id, force=True)
        assert success is True


class TestSubAgentStopAll:
    """SubAgentSpawner 批量停止测试"""
    
    @pytest.fixture
    def spawner(self) -> SubAgentSpawner:
        """创建派生器"""
        return SubAgentSpawner(
            concurrency_controller=MockConcurrencyController(),
            enable_announce=False,
        )
    
    @pytest.mark.asyncio
    async def test_stop_all_for_session(self, spawner: SubAgentSpawner):
        """测试停止会话的所有派生"""
        runtime = MockAgentRuntime(execution_time=10.0)
        session_store = MockSessionStore()
        
        # 创建多个派生
        requests = [
            SpawnRequest(
                task=f"task {i}",
                parent_agent_id="parent",
                parent_session_id="session1",
            )
            for i in range(3)
        ]
        
        for req in requests:
            await spawner.spawn(req, runtime, session_store)
        
        await asyncio.sleep(0.1)
        
        # 停止所有
        count = await spawner.stop_all_for_session("session1")
        
        assert count == 3
        
    @pytest.mark.asyncio
    async def test_stop_all_emergency(self, spawner: SubAgentSpawner):
        """测试紧急停止所有"""
        runtime = MockAgentRuntime(execution_time=10.0)
        session_store = MockSessionStore()
        
        # 创建多个派生
        for i in range(5):
            request = SpawnRequest(
                task=f"task {i}",
                parent_agent_id="parent",
                parent_session_id=f"session{i}",
            )
            await spawner.spawn(request, runtime, session_store)
        
        await asyncio.sleep(0.1)
        
        # 紧急停止
        count = await spawner.stop_all()
        
        assert count == 5


class TestSubAgentStats:
    """SubAgentSpawner 统计测试"""
    
    @pytest.fixture
    def spawner(self) -> SubAgentSpawner:
        """创建派生器"""
        return SubAgentSpawner(
            concurrency_controller=MockConcurrencyController(),
            enable_announce=False,
        )
    
    def test_stats_includes_running_tasks(self, spawner: SubAgentSpawner):
        """测试统计包含运行中的任务数"""
        stats = spawner.get_stats()
        
        assert "running_tasks" in stats
        assert "cancelled_spawns" in stats
        
    @pytest.mark.asyncio
    async def test_get_running_tasks(self, spawner: SubAgentSpawner):
        """测试获取运行中的任务列表"""
        runtime = MockAgentRuntime(execution_time=10.0)
        session_store = MockSessionStore()
        
        request = SpawnRequest(
            task="task",
            parent_agent_id="parent",
            parent_session_id="session",
        )
        
        result = await spawner.spawn(request, runtime, session_store)
        await asyncio.sleep(0.1)
        
        running = await spawner.get_running_tasks()
        
        assert result.spawn_id in running
        
        # 清理
        await spawner.stop_spawn(result.spawn_id)


class TestSubAgentCancelledError:
    """Subagent CancelledError 处理测试"""
    
    @pytest.fixture
    def spawner(self) -> SubAgentSpawner:
        """创建派生器"""
        return SubAgentSpawner(
            concurrency_controller=MockConcurrencyController(),
            enable_announce=False,
        )
    
    @pytest.mark.asyncio
    async def test_cancelled_error_handled_gracefully(self, spawner: SubAgentSpawner):
        """测试 CancelledError 被正确处理"""
        request = SpawnRequest(
            task="task",
            parent_agent_id="parent",
            parent_session_id="session",
        )
        
        runtime = MockAgentRuntime(execution_time=10.0)
        session_store = MockSessionStore()
        
        result = await spawner.spawn(request, runtime, session_store)
        await asyncio.sleep(0.1)
        
        # 取消
        await spawner.stop_spawn(result.spawn_id)
        
        # 状态应该是 CANCELLED
        assert result.status == SpawnStatus.CANCELLED
        assert "取消" in result.error
