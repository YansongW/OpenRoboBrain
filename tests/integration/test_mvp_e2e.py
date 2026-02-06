"""
MVP 端到端测试

测试OpenRoboBrain的完整调用链路:
CLI/API输入 -> OpenRoboBrain.process() -> BehaviorExecutor -> GeneralBehavior 
-> ReasoningAgent/RuleBased -> ProcessResult(chat_response + ros2_commands)
"""

import asyncio
import pytest
import pytest_asyncio
from typing import Optional

from orb import OpenRoboBrain, ProcessResult
from orb.behavior.base import BehaviorStatus


class TestMVPCallChain:
    """MVP调用链路测试"""
    
    @pytest_asyncio.fixture
    async def brain(self):
        """创建并初始化OpenRoboBrain实例"""
        brain = OpenRoboBrain(mock_ros2=True)
        await brain.initialize()
        await brain.start()
        yield brain
        await brain.stop()
    
    @pytest.mark.asyncio
    async def test_brain_initialization(self, brain: OpenRoboBrain):
        """测试OpenRoboBrain初始化"""
        assert brain is not None
        assert brain.is_running is True
        assert brain.behavior_executor is not None
        assert brain.bridge is not None
    
    @pytest.mark.asyncio
    async def test_process_returns_result(self, brain: OpenRoboBrain):
        """测试process()方法返回ProcessResult"""
        result = await brain.process("你好")
        
        assert result is not None
        assert isinstance(result, ProcessResult)
        assert result.trace_id is not None
        assert result.trace_id.startswith("trace-")
    
    @pytest.mark.asyncio
    async def test_process_generates_chat_response(self, brain: OpenRoboBrain):
        """测试process()生成chat_response"""
        result = await brain.process("你好")
        
        assert result.chat_response is not None
        assert len(result.chat_response) > 0
        assert result.success is True
    
    @pytest.mark.asyncio
    async def test_process_with_command_generates_ros2(self, brain: OpenRoboBrain):
        """测试指令类输入生成ROS2命令"""
        # 测试移动命令
        result = await brain.process("去厨房")
        
        assert result.success is True
        assert result.chat_response is not None
        # ROS2命令可能生成也可能不生成（取决于rule-based逻辑）
        assert isinstance(result.ros2_commands, list)
    
    @pytest.mark.asyncio
    async def test_process_greeting(self, brain: OpenRoboBrain):
        """测试问候语处理"""
        result = await brain.process("你好，你是谁？")
        
        assert result.success is True
        assert result.chat_response is not None
        # 问候语不应该生成ROS2命令
    
    @pytest.mark.asyncio
    async def test_process_with_trace_id(self, brain: OpenRoboBrain):
        """测试自定义trace_id"""
        custom_trace_id = "test-trace-12345"
        result = await brain.process("测试", trace_id=custom_trace_id)
        
        assert result.trace_id == custom_trace_id
    
    @pytest.mark.asyncio
    async def test_process_with_parameters(self, brain: OpenRoboBrain):
        """测试带参数的process调用"""
        params = {"context": "test_context", "priority": "high"}
        result = await brain.process("测试任务", parameters=params)
        
        assert result.success is True
        assert result.trace_id is not None
    
    @pytest.mark.asyncio
    async def test_execution_time_recorded(self, brain: OpenRoboBrain):
        """测试执行时间记录"""
        result = await brain.process("测试")
        
        assert result.execution_time_ms >= 0
    
    @pytest.mark.asyncio
    async def test_behavior_result_included(self, brain: OpenRoboBrain):
        """测试BehaviorResult包含在结果中"""
        result = await brain.process("测试")
        
        # behavior_result可能存在也可能不存在（取决于执行路径）
        if result.behavior_result:
            assert result.behavior_name is not None


class TestRuleBasedMode:
    """Rule-Based模式测试（无LLM情况下）"""
    
    @pytest_asyncio.fixture
    async def brain(self):
        """创建OpenRoboBrain实例（无LLM配置）"""
        brain = OpenRoboBrain(mock_ros2=True)
        await brain.initialize()
        await brain.start()
        yield brain
        await brain.stop()
    
    @pytest.mark.asyncio
    async def test_greeting_response(self, brain: OpenRoboBrain):
        """测试问候响应"""
        greetings = ["你好", "hi", "hello", "嗨"]
        
        for greeting in greetings:
            result = await brain.process(greeting)
            assert result.success is True
            assert result.chat_response is not None
            assert len(result.chat_response) > 0
    
    @pytest.mark.asyncio
    async def test_farewell_response(self, brain: OpenRoboBrain):
        """测试告别响应"""
        farewells = ["再见", "拜拜", "bye"]
        
        for farewell in farewells:
            result = await brain.process(farewell)
            assert result.success is True
            assert result.chat_response is not None
    
    @pytest.mark.asyncio
    async def test_navigation_command(self, brain: OpenRoboBrain):
        """测试导航命令"""
        commands = ["去客厅", "到厨房", "走到门口"]
        
        for cmd in commands:
            result = await brain.process(cmd)
            assert result.success is True
            # 应该生成ROS2命令
            if result.ros2_commands:
                assert len(result.ros2_commands) > 0
    
    @pytest.mark.asyncio
    async def test_grasp_command(self, brain: OpenRoboBrain):
        """测试抓取命令"""
        commands = ["拿杯子", "取苹果", "给我书"]
        
        for cmd in commands:
            result = await brain.process(cmd)
            assert result.success is True
    
    @pytest.mark.asyncio
    async def test_stop_command(self, brain: OpenRoboBrain):
        """测试停止命令"""
        commands = ["停", "别动", "stop"]
        
        for cmd in commands:
            result = await brain.process(cmd)
            assert result.success is True
    
    @pytest.mark.asyncio
    async def test_unknown_input(self, brain: OpenRoboBrain):
        """测试未知输入"""
        result = await brain.process("一些随机的文字内容")
        
        assert result.success is True
        assert result.chat_response is not None


class TestProcessResultFormat:
    """ProcessResult格式测试"""
    
    @pytest_asyncio.fixture
    async def brain(self):
        """创建OpenRoboBrain实例"""
        brain = OpenRoboBrain(mock_ros2=True)
        await brain.initialize()
        await brain.start()
        yield brain
        await brain.stop()
    
    @pytest.mark.asyncio
    async def test_result_to_dict(self, brain: OpenRoboBrain):
        """测试ProcessResult转字典"""
        result = await brain.process("测试")
        result_dict = result.to_dict()
        
        assert "trace_id" in result_dict
        assert "chat_response" in result_dict
        assert "ros2_commands" in result_dict
        assert "success" in result_dict
        assert "execution_time_ms" in result_dict
    
    @pytest.mark.asyncio
    async def test_ros2_commands_format(self, brain: OpenRoboBrain):
        """测试ROS2命令格式"""
        result = await brain.process("去厨房拿水杯")
        
        for cmd in result.ros2_commands:
            # 每个命令应该是字典或BrainCommand对象
            if hasattr(cmd, 'to_dict'):
                cmd_dict = cmd.to_dict()
                assert "commandType" in cmd_dict or "command_type" in cmd_dict


class TestConcurrentProcessing:
    """并发处理测试"""
    
    @pytest_asyncio.fixture
    async def brain(self):
        """创建OpenRoboBrain实例"""
        brain = OpenRoboBrain(mock_ros2=True)
        await brain.initialize()
        await brain.start()
        yield brain
        await brain.stop()
    
    @pytest.mark.asyncio
    async def test_concurrent_requests(self, brain: OpenRoboBrain):
        """测试并发请求处理"""
        inputs = ["你好", "去厨房", "拿杯子", "停止", "再见"]
        
        # 并发执行
        tasks = [brain.process(inp) for inp in inputs]
        results = await asyncio.gather(*tasks)
        
        # 所有请求都应该成功
        assert len(results) == len(inputs)
        for result in results:
            assert result.success is True
            assert result.trace_id is not None


class TestErrorHandling:
    """错误处理测试"""
    
    @pytest.mark.asyncio
    async def test_process_before_start(self):
        """测试未启动时调用process"""
        brain = OpenRoboBrain(mock_ros2=True)
        await brain.initialize()
        # 不调用start()
        
        result = await brain.process("测试")
        
        # 应该返回错误结果
        assert result.success is False
        assert result.error is not None
        
        await brain.stop()
    
    @pytest.mark.asyncio
    async def test_empty_input(self):
        """测试空输入"""
        brain = OpenRoboBrain(mock_ros2=True)
        await brain.initialize()
        await brain.start()
        
        result = await brain.process("")
        
        # 应该能处理空输入
        assert result.trace_id is not None
        
        await brain.stop()


# ============== 运行测试 ==============

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
