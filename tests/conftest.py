"""
Pytest 配置和公共 fixtures

OpenRoboBrain 测试配置。
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import AsyncGenerator, Generator

import pytest

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# ============== Async 支持 ==============

@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """创建事件循环（session 级别）"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ============== 临时目录 ==============

@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """临时目录"""
    return tmp_path


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    """临时工作空间"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    
    # 创建基础结构
    (workspace / "AGENTS.md").write_text("# Agent Configuration\n")
    (workspace / "memory").mkdir()
    
    return workspace


# ============== 配置 Fixtures ==============

@pytest.fixture
def test_config() -> dict:
    """测试配置"""
    return {
        "llm": {
            "provider": "ollama",
            "model": "llama3.2",
            "base_url": "http://localhost:11434",
        },
        "tools": {
            "shell": {
                "mode": "deny",
                "timeout": 30,
            },
        },
        "data": {
            "database_url": ":memory:",
        },
    }


# ============== Mock Fixtures ==============

@pytest.fixture
def mock_llm_response() -> str:
    """模拟 LLM 响应"""
    return "这是一个模拟的 LLM 响应。"


@pytest.fixture
def mock_tool_result() -> dict:
    """模拟工具执行结果"""
    return {
        "status": "success",
        "result": "Tool executed successfully",
    }


# ============== 数据库 Fixtures ==============

@pytest.fixture
async def memory_db() -> AsyncGenerator[None, None]:
    """内存数据库"""
    # 使用内存数据库进行测试
    yield
    # 清理


@pytest.fixture
def sample_workflow() -> dict:
    """示例工作流数据"""
    return {
        "task_id": "test_cooking_001",
        "agent_chain": ["perception", "planning", "execution"],
        "expected_result": "完成烹饪任务",
        "influence_factors": {
            "ingredients": ["番茄", "鸡蛋"],
            "tools": ["锅", "铲"],
        },
    }


@pytest.fixture
def sample_entity() -> dict:
    """示例实体数据"""
    return {
        "entity_id": "user_001",
        "entity_type": "person",
        "name": "测试用户",
        "attributes": {
            "age": 30,
            "preferences": ["coffee", "reading"],
        },
    }


# ============== Agent Fixtures ==============

@pytest.fixture
def agent_config() -> dict:
    """Agent 配置"""
    return {
        "agent_id": "test_agent_001",
        "name": "TestAgent",
        "description": "测试用 Agent",
        "capabilities": ["chat", "tool_use"],
    }


# ============== 环境变量 ==============

@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """清理测试环境变量"""
    # 设置测试环境
    monkeypatch.setenv("ORB_ENV", "test")
    monkeypatch.setenv("ORB_DEBUG", "1")
