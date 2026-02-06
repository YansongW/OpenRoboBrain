"""
工具执行器单元测试
"""

import asyncio
import pytest

from orb.agent.runtime.tool_executor import (
    ToolExecutor,
    ToolRegistry,
    ToolCall,
    ToolResult,
    ToolResultStatus,
    create_tool_executor,
)


class TestToolRegistry:
    """工具注册表测试"""
    
    def test_register_sync_tool(self):
        """测试注册同步工具"""
        registry = ToolRegistry()
        
        def my_tool(x: int, y: int) -> int:
            """加法工具"""
            return x + y
        
        registry.register("add", my_tool, description="两数相加")
        
        tool = registry.get("add")
        assert tool is not None
        assert tool.name == "add"
        assert tool.is_async is False
        
    def test_register_async_tool(self):
        """测试注册异步工具"""
        registry = ToolRegistry()
        
        async def my_async_tool(msg: str) -> str:
            """异步工具"""
            await asyncio.sleep(0.01)
            return f"processed: {msg}"
        
        registry.register("process", my_async_tool)
        
        tool = registry.get("process")
        assert tool is not None
        assert tool.is_async is True
        
    def test_register_decorator(self):
        """测试装饰器注册"""
        registry = ToolRegistry()
        
        @registry.register_decorator(name="greet", description="打招呼")
        def greet(name: str) -> str:
            return f"Hello, {name}!"
        
        tool = registry.get("greet")
        assert tool is not None
        assert tool.description == "打招呼"
        
    def test_unregister_tool(self):
        """测试注销工具"""
        registry = ToolRegistry()
        registry.register("temp", lambda: None)
        
        assert registry.get("temp") is not None
        assert registry.unregister("temp") is True
        assert registry.get("temp") is None
        
    def test_list_tools_by_tag(self):
        """测试按标签列出工具"""
        registry = ToolRegistry()
        registry.register("tool1", lambda: None, tags=["fs"])
        registry.register("tool2", lambda: None, tags=["http"])
        registry.register("tool3", lambda: None, tags=["fs", "read"])
        
        fs_tools = registry.list(tags=["fs"])
        assert len(fs_tools) == 2


class TestToolExecutor:
    """工具执行器测试"""
    
    @pytest.fixture
    def executor(self) -> ToolExecutor:
        """创建执行器"""
        executor = ToolExecutor()
        
        # 注册测试工具
        executor.registry.register(
            "echo",
            lambda msg: msg,
            description="回显消息",
        )
        
        async def async_double(n: int) -> int:
            await asyncio.sleep(0.01)
            return n * 2
        
        executor.registry.register("double", async_double)
        
        return executor
        
    @pytest.mark.asyncio
    async def test_execute_sync_tool(self, executor: ToolExecutor):
        """测试执行同步工具"""
        call = ToolCall(tool_name="echo", arguments={"msg": "hello"})
        result = await executor.execute(call)
        
        assert result.status == ToolResultStatus.SUCCESS
        assert result.result == "hello"
        
    @pytest.mark.asyncio
    async def test_execute_async_tool(self, executor: ToolExecutor):
        """测试执行异步工具"""
        call = ToolCall(tool_name="double", arguments={"n": 5})
        result = await executor.execute(call)
        
        assert result.status == ToolResultStatus.SUCCESS
        assert result.result == 10
        
    @pytest.mark.asyncio
    async def test_execute_nonexistent_tool(self, executor: ToolExecutor):
        """测试执行不存在的工具"""
        call = ToolCall(tool_name="nonexistent", arguments={})
        result = await executor.execute(call)
        
        assert result.status == ToolResultStatus.ERROR
        assert "不存在" in result.error
        
    @pytest.mark.asyncio
    async def test_execute_batch_parallel(self, executor: ToolExecutor):
        """测试并行批量执行"""
        calls = [
            ToolCall(tool_name="double", arguments={"n": i})
            for i in range(5)
        ]
        
        results = await executor.execute_batch(calls, parallel=True)
        
        assert len(results) == 5
        assert all(r.status == ToolResultStatus.SUCCESS for r in results)
        assert [r.result for r in results] == [0, 2, 4, 6, 8]
        
    def test_skip_tool_call(self, executor: ToolExecutor):
        """测试跳过工具调用"""
        call = ToolCall(tool_name="echo", arguments={"msg": "test"})
        result = executor.skip_tool_call(call, "test reason")
        
        assert result.status == ToolResultStatus.SKIPPED
        assert "test reason" in result.error
        
    def test_deny_tool_call(self, executor: ToolExecutor):
        """测试拒绝工具调用"""
        call = ToolCall(tool_name="echo", arguments={"msg": "test"})
        result = executor.deny_tool_call(call, "policy violation")
        
        assert result.status == ToolResultStatus.DENIED
        
    def test_get_stats(self, executor: ToolExecutor):
        """测试获取统计信息"""
        stats = executor.get_stats()
        
        assert "execution_count" in stats
        assert "registered_tools" in stats


class TestToolCall:
    """ToolCall 测试"""
    
    def test_from_dict(self):
        """测试从字典创建"""
        data = {
            "id": "call_123",
            "function": {
                "name": "test_tool",
                "arguments": '{"key": "value"}',
            },
        }
        
        call = ToolCall.from_dict(data)
        
        assert call.call_id == "call_123"
        assert call.tool_name == "test_tool"
        assert call.arguments == {"key": "value"}


class TestToolResult:
    """ToolResult 测试"""
    
    def test_to_dict(self):
        """测试转换为字典"""
        result = ToolResult(
            call_id="call_123",
            tool_name="test",
            status=ToolResultStatus.SUCCESS,
            result={"data": 123},
        )
        
        d = result.to_dict()
        
        assert d["call_id"] == "call_123"
        assert d["status"] == "success"
        assert d["result"] == {"data": 123}
        
    def test_to_string_success(self):
        """测试成功结果转字符串"""
        result = ToolResult(
            call_id="call_123",
            tool_name="test",
            status=ToolResultStatus.SUCCESS,
            result={"key": "value"},
        )
        
        s = result.to_string()
        assert "key" in s
        assert "value" in s
        
    def test_to_string_error(self):
        """测试错误结果转字符串"""
        result = ToolResult(
            call_id="call_123",
            tool_name="test",
            status=ToolResultStatus.ERROR,
            error="Something went wrong",
        )
        
        s = result.to_string()
        assert "Error" in s
        assert "Something went wrong" in s
