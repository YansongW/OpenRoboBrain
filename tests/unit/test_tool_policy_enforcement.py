"""
工具策略强制执行测试

测试框架修复：
- ToolPolicy 在 ToolExecutor.execute() 中强制执行
- 被拒绝的工具调用返回 DENIED 状态
"""

import asyncio
import pytest

from orb.agent.runtime.tool_executor import (
    ToolExecutor,
    ToolRegistry,
    ToolCall,
    ToolResultStatus,
)
from orb.agent.security.tool_policy import (
    ToolPolicy,
    ToolPolicyConfig,
    PolicyDecision,
    create_tool_policy,
)


class TestToolPolicyEnforcement:
    """工具策略强制执行测试"""
    
    @pytest.fixture
    def registry(self) -> ToolRegistry:
        """创建带工具的注册表"""
        registry = ToolRegistry()
        
        registry.register("read_file", lambda path: f"content of {path}")
        registry.register("write_file", lambda path, content: f"wrote to {path}")
        registry.register("exec", lambda cmd: f"executed {cmd}")
        registry.register("safe_tool", lambda: "safe result")
        
        return registry
    
    @pytest.fixture
    def deny_policy(self) -> ToolPolicy:
        """创建拒绝 exec 工具的策略"""
        config = ToolPolicyConfig(
            allow=["*"],
            deny=["exec"],
        )
        return ToolPolicy(config)
    
    @pytest.fixture
    def readonly_policy(self) -> ToolPolicy:
        """创建只读策略"""
        config = ToolPolicyConfig(
            allow=["read_file", "safe_tool"],
            deny=["write_file", "exec"],
        )
        return ToolPolicy(config)
    
    @pytest.mark.asyncio
    async def test_execute_without_policy(self, registry: ToolRegistry):
        """测试无策略时正常执行"""
        executor = ToolExecutor(registry=registry, policy=None)
        
        call = ToolCall(tool_name="exec", arguments={"cmd": "ls"})
        result = await executor.execute(call)
        
        assert result.status == ToolResultStatus.SUCCESS
        assert "executed" in result.result
        
    @pytest.mark.asyncio
    async def test_execute_allowed_tool(
        self,
        registry: ToolRegistry,
        deny_policy: ToolPolicy,
    ):
        """测试执行允许的工具"""
        executor = ToolExecutor(registry=registry, policy=deny_policy)
        
        call = ToolCall(tool_name="read_file", arguments={"path": "/test"})
        result = await executor.execute(call)
        
        assert result.status == ToolResultStatus.SUCCESS
        
    @pytest.mark.asyncio
    async def test_execute_denied_tool(
        self,
        registry: ToolRegistry,
        deny_policy: ToolPolicy,
    ):
        """测试执行被拒绝的工具"""
        executor = ToolExecutor(registry=registry, policy=deny_policy)
        
        call = ToolCall(tool_name="exec", arguments={"cmd": "rm -rf /"})
        result = await executor.execute(call)
        
        assert result.status == ToolResultStatus.DENIED
        assert "拒绝" in result.error or "denied" in result.error.lower()
        
    @pytest.mark.asyncio
    async def test_denied_count_incremented(
        self,
        registry: ToolRegistry,
        deny_policy: ToolPolicy,
    ):
        """测试拒绝计数增加"""
        executor = ToolExecutor(registry=registry, policy=deny_policy)
        
        assert executor._denied_count == 0
        
        call = ToolCall(tool_name="exec", arguments={"cmd": "test"})
        await executor.execute(call)
        
        assert executor._denied_count == 1
        
    @pytest.mark.asyncio
    async def test_readonly_policy_allows_read(
        self,
        registry: ToolRegistry,
        readonly_policy: ToolPolicy,
    ):
        """测试只读策略允许读取"""
        executor = ToolExecutor(registry=registry, policy=readonly_policy)
        
        call = ToolCall(tool_name="read_file", arguments={"path": "/test"})
        result = await executor.execute(call)
        
        assert result.status == ToolResultStatus.SUCCESS
        
    @pytest.mark.asyncio
    async def test_readonly_policy_denies_write(
        self,
        registry: ToolRegistry,
        readonly_policy: ToolPolicy,
    ):
        """测试只读策略拒绝写入"""
        executor = ToolExecutor(registry=registry, policy=readonly_policy)
        
        call = ToolCall(tool_name="write_file", arguments={"path": "/test", "content": "data"})
        result = await executor.execute(call)
        
        assert result.status == ToolResultStatus.DENIED
        
    @pytest.mark.asyncio
    async def test_enforce_policy_can_be_disabled(
        self,
        registry: ToolRegistry,
        deny_policy: ToolPolicy,
    ):
        """测试可以禁用策略强制执行"""
        executor = ToolExecutor(
            registry=registry,
            policy=deny_policy,
            enforce_policy=False,  # 禁用强制执行
        )
        
        # 即使在拒绝列表中，也应该执行
        call = ToolCall(tool_name="exec", arguments={"cmd": "test"})
        result = await executor.execute(call)
        
        assert result.status == ToolResultStatus.SUCCESS
        
    @pytest.mark.asyncio
    async def test_set_policy_updates_executor(self, registry: ToolRegistry):
        """测试动态设置策略"""
        executor = ToolExecutor(registry=registry, policy=None)
        
        # 无策略时可以执行
        call = ToolCall(tool_name="exec", arguments={"cmd": "test"})
        result = await executor.execute(call)
        assert result.status == ToolResultStatus.SUCCESS
        
        # 设置策略
        policy = create_tool_policy(deny=["exec"])
        executor.set_policy(policy)
        
        # 现在应该被拒绝
        result = await executor.execute(call)
        assert result.status == ToolResultStatus.DENIED
        
    @pytest.mark.asyncio
    async def test_context_passed_to_policy(
        self,
        registry: ToolRegistry,
    ):
        """测试上下文传递给策略"""
        # 创建一个对特定 agent 有特殊规则的策略
        policy = ToolPolicy()
        
        # 为特定 agent 设置策略
        agent_config = ToolPolicyConfig(
            allow=["read_file"],
            deny=["exec"],
        )
        policy.set_agent_config("restricted_agent", agent_config)
        
        executor = ToolExecutor(registry=registry, policy=policy)
        
        # 普通 agent 可以执行 exec
        call = ToolCall(tool_name="exec", arguments={"cmd": "test"})
        result = await executor.execute(call, context={"agent_id": "normal_agent"})
        assert result.status == ToolResultStatus.SUCCESS
        
        # restricted_agent 不能执行 exec
        result = await executor.execute(call, context={"agent_id": "restricted_agent"})
        assert result.status == ToolResultStatus.DENIED
        
    def test_get_stats_includes_policy_info(self, registry: ToolRegistry):
        """测试统计信息包含策略信息"""
        policy = create_tool_policy(deny=["exec"])
        executor = ToolExecutor(registry=registry, policy=policy)
        
        stats = executor.get_stats()
        
        assert "policy_enabled" in stats
        assert stats["policy_enabled"] is True
        assert "denied_count" in stats


class TestToolPolicyProfiles:
    """工具策略预设测试"""
    
    @pytest.fixture
    def registry(self) -> ToolRegistry:
        """创建带工具的注册表"""
        registry = ToolRegistry()
        
        registry.register("read", lambda: "read")
        registry.register("write", lambda: "write")
        registry.register("edit", lambda: "edit")
        registry.register("exec", lambda: "exec")
        registry.register("message", lambda: "message")
        
        return registry
    
    @pytest.mark.asyncio
    async def test_safe_profile(self, registry: ToolRegistry):
        """测试 safe 预设"""
        policy = create_tool_policy(profile="safe")
        executor = ToolExecutor(registry=registry, policy=policy)
        
        # safe 只允许 read 和 message
        read_result = await executor.execute(ToolCall(tool_name="read", arguments={}))
        message_result = await executor.execute(ToolCall(tool_name="message", arguments={}))
        exec_result = await executor.execute(ToolCall(tool_name="exec", arguments={}))
        
        assert read_result.status == ToolResultStatus.SUCCESS
        assert message_result.status == ToolResultStatus.SUCCESS
        assert exec_result.status == ToolResultStatus.DENIED
        
    @pytest.mark.asyncio
    async def test_readonly_profile(self, registry: ToolRegistry):
        """测试 readonly 预设"""
        policy = create_tool_policy(profile="readonly")
        executor = ToolExecutor(registry=registry, policy=policy)
        
        read_result = await executor.execute(ToolCall(tool_name="read", arguments={}))
        write_result = await executor.execute(ToolCall(tool_name="write", arguments={}))
        
        assert read_result.status == ToolResultStatus.SUCCESS
        assert write_result.status == ToolResultStatus.DENIED
