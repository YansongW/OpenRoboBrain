"""
Agent Runtime Layer

Agent 运行时层，实现完整的 Agent Loop 执行周期：
intake → context assembly → model inference → tool execution → streaming replies → persistence

借鉴 OpenClaw/Moltbot 的 agentic loop 设计，支持：
- 事件驱动架构
- 流式输出
- 工具调用 (ReAct 模式)
- 生命周期钩子
- 会话管理
"""

from orb.agent.runtime.agent_loop import (
    AgentLoop,
    LoopConfig,
    LoopState,
    LoopPhase,
    QueueMode,
    RunContext,
    RunResult,
    create_agent_loop,
    run_single_turn,
)
from orb.agent.runtime.context_builder import (
    ContextBuilder,
    ContextConfig,
    AgentContext,
    MessageContext,
    create_context_builder,
)
from orb.agent.runtime.tool_executor import (
    ToolExecutor,
    ToolRegistry,
    ToolDefinition,
    ToolCall,
    ToolResult,
    ToolResultStatus,
    create_tool_executor,
    register_builtin_tools,
)
from orb.agent.runtime.stream_handler import (
    StreamHandler,
    BlockStreamHandler,
    StreamEvent,
    StreamEventType,
    ChunkingConfig,
    create_stream_handler,
)
from orb.agent.runtime.agent_runtime import (
    AgentRuntime,
    RuntimeConfig,
)

__all__ = [
    # Agent Loop
    "AgentLoop",
    "LoopConfig",
    "LoopState",
    "LoopPhase",
    "QueueMode",
    "RunContext",
    "RunResult",
    "create_agent_loop",
    "run_single_turn",
    # Context Builder
    "ContextBuilder",
    "ContextConfig",
    "AgentContext",
    "MessageContext",
    "create_context_builder",
    # Tool Executor
    "ToolExecutor",
    "ToolRegistry",
    "ToolDefinition",
    "ToolCall",
    "ToolResult",
    "ToolResultStatus",
    "create_tool_executor",
    "register_builtin_tools",
    # Stream Handler
    "StreamHandler",
    "BlockStreamHandler",
    "StreamEvent",
    "StreamEventType",
    "ChunkingConfig",
    "create_stream_handler",
    # Agent Runtime
    "AgentRuntime",
    "RuntimeConfig",
]
