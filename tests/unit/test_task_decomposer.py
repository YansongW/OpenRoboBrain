"""
任务拆解器单元测试

测试TaskDecomposer的模板分解和规则分解功能。
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from kaibrain.agent.orchestrator.task_decomposer import (
    TaskDecomposer,
    Task,
    TaskType,
)


class TestTemplateDecompose:
    """模板分解测试"""
    
    def test_decompose_with_template(self):
        """测试使用模板分解任务"""
        decomposer = TaskDecomposer()
        
        # 使用预定义的抓取物体模板
        task = decomposer.decompose("grasp_object")
        
        assert task.task_type == TaskType.SEQUENTIAL
        assert len(task.subtasks) == 3
        assert task.subtasks[0].name == "detect_object"
        assert task.subtasks[1].name == "plan_grasp"
        assert task.subtasks[2].name == "execute_grasp"
    
    def test_decompose_without_template(self):
        """测试无模板时降级为原子任务"""
        decomposer = TaskDecomposer()
        
        task = decomposer.decompose("unknown_task_type")
        
        assert task.task_type == TaskType.ATOMIC
        assert task.name == "unknown_task_type"
    
    def test_custom_template(self):
        """测试自定义模板"""
        decomposer = TaskDecomposer()
        
        # 注册自定义模板
        decomposer.register_template(
            "custom_task",
            [
                {"name": "step1", "agent_type": "agent1"},
                {"name": "step2", "agent_type": "agent2"},
            ]
        )
        
        task = decomposer.decompose("custom_task")
        
        assert task.task_type == TaskType.SEQUENTIAL
        assert len(task.subtasks) == 2
    
    def test_subtask_dependencies(self):
        """测试子任务依赖关系"""
        decomposer = TaskDecomposer()
        
        task = decomposer.decompose("grasp_object")
        
        # 第一个子任务没有依赖
        assert task.subtasks[0].dependencies == []
        # 第二个子任务依赖第一个
        assert task.subtasks[1].dependencies == [task.subtasks[0].task_id]
        # 第三个子任务依赖第二个
        assert task.subtasks[2].dependencies == [task.subtasks[1].task_id]


class TestRuleBasedDecompose:
    """规则分解测试"""
    
    def test_navigation_keyword(self):
        """测试导航关键词识别"""
        decomposer = TaskDecomposer()
        
        task = decomposer.rule_based_decompose("去厨房")
        
        assert task.task_type == TaskType.SEQUENTIAL
        # 应该识别为导航任务
        assert any("navigation" in st.agent_type for st in task.subtasks)
    
    def test_manipulation_keyword(self):
        """测试物体操作关键词识别"""
        decomposer = TaskDecomposer()
        
        task = decomposer.rule_based_decompose("拿杯子")
        
        # 应该匹配到抓取模板
        assert task.task_type == TaskType.SEQUENTIAL
    
    def test_pour_water_keyword(self):
        """测试倒水关键词识别"""
        decomposer = TaskDecomposer()
        
        task = decomposer.rule_based_decompose("帮我倒杯水")
        
        assert task.task_type == TaskType.SEQUENTIAL
        assert len(task.subtasks) > 1
    
    def test_clean_keyword(self):
        """测试清洁关键词识别"""
        decomposer = TaskDecomposer()
        
        task = decomposer.rule_based_decompose("打扫房间")
        
        assert task.task_type == TaskType.SEQUENTIAL
    
    def test_unknown_task(self):
        """测试未知任务类型"""
        decomposer = TaskDecomposer()
        
        task = decomposer.rule_based_decompose("一些随机的话语")
        
        # 无法识别时应该返回原子任务
        assert task.task_type == TaskType.ATOMIC


class TestParallelDecompose:
    """并行分解测试"""
    
    def test_parallel_decomposition(self):
        """测试并行任务创建"""
        decomposer = TaskDecomposer()
        
        task = decomposer.decompose_parallel(
            "parallel_task",
            [
                {"name": "task_a", "agent_type": "agent_a"},
                {"name": "task_b", "agent_type": "agent_b"},
                {"name": "task_c", "agent_type": "agent_c"},
            ]
        )
        
        assert task.task_type == TaskType.PARALLEL
        assert len(task.subtasks) == 3
        # 并行任务的子任务不应有依赖
        for subtask in task.subtasks:
            assert subtask.dependencies == []


class TestTaskToDict:
    """Task序列化测试"""
    
    def test_simple_task_to_dict(self):
        """测试简单任务序列化"""
        task = Task(
            task_type=TaskType.ATOMIC,
            name="test_task",
            description="测试任务",
            agent_type="test_agent",
        )
        
        result = task.to_dict()
        
        assert result["name"] == "test_task"
        assert result["task_type"] == "atomic"
        assert result["description"] == "测试任务"
    
    def test_composite_task_to_dict(self):
        """测试复合任务序列化"""
        decomposer = TaskDecomposer()
        task = decomposer.decompose("grasp_object")
        
        result = task.to_dict()
        
        assert result["task_type"] == "sequential"
        assert len(result["subtasks"]) == 3


class TestSmartDecomposeWithoutLLM:
    """无LLM情况下的智能分解测试"""
    
    @pytest.mark.asyncio
    async def test_fallback_to_rule_based(self):
        """测试LLM不可用时降级到规则分解"""
        decomposer = TaskDecomposer(llm=None)
        
        task = await decomposer.smart_decompose(
            "去厨房拿杯水",
            use_fallback=True,
        )
        
        # 应该成功返回任务（使用规则分解）
        assert task is not None
        assert task.task_type in [TaskType.SEQUENTIAL, TaskType.ATOMIC]
    
    @pytest.mark.asyncio
    async def test_no_fallback_raises_error(self):
        """测试禁用fallback时抛出错误"""
        decomposer = TaskDecomposer(llm=None)
        
        with pytest.raises(RuntimeError):
            await decomposer.smart_decompose(
                "去厨房",
                use_fallback=False,
            )


class TestSmartDecomposeWithMockLLM:
    """使用Mock LLM的智能分解测试"""
    
    @pytest.mark.asyncio
    async def test_llm_decomposition(self):
        """测试LLM分解任务"""
        # 创建Mock LLM
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '''```json
{
    "task_type": "sequential",
    "reasoning": "分解倒水任务",
    "subtasks": [
        {
            "name": "find_cup",
            "description": "找到杯子",
            "agent_type": "vision.object_detect",
            "dependencies": [],
            "parameters": {}
        },
        {
            "name": "pour_water",
            "description": "倒水",
            "agent_type": "action.pour",
            "dependencies": ["find_cup"],
            "parameters": {}
        }
    ]
}
```'''
        mock_llm.chat = AsyncMock(return_value=mock_response)
        
        decomposer = TaskDecomposer(llm=mock_llm)
        
        task = await decomposer.smart_decompose("帮我倒杯水")
        
        assert task.task_type == TaskType.SEQUENTIAL
        assert len(task.subtasks) == 2
        assert task.subtasks[0].name == "find_cup"
        assert task.subtasks[1].name == "pour_water"
    
    @pytest.mark.asyncio
    async def test_llm_failure_fallback(self):
        """测试LLM失败时的fallback"""
        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(side_effect=Exception("LLM Error"))
        
        decomposer = TaskDecomposer(llm=mock_llm)
        
        task = await decomposer.smart_decompose(
            "去厨房",
            use_fallback=True,
        )
        
        # 应该使用规则分解
        assert task is not None


class TestDefaultAgents:
    """默认Agent列表测试"""
    
    def test_default_agents_not_empty(self):
        """测试默认Agent列表不为空"""
        decomposer = TaskDecomposer()
        agents = decomposer._get_default_available_agents()
        
        assert len(agents) > 0
        assert "vision.object_detect" in agents
        assert "navigation.goto" in agents
        assert "action.grasp" in agents


# ============== 运行测试 ==============

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
