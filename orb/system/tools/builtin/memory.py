"""
Memory 工具

提供 Agent 通过 tool_calls 读写记忆的能力。

工具:
- memory_write: 写入记忆（存储重要信息）
- memory_search: 搜索记忆（基于 MemoryRanker 多信号排序）
- memory_get: 获取指定记忆详情
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from orb.system.tools.base import Tool
from orb.system.services.logger import LoggerMixin


class MemoryTools(LoggerMixin):
    """
    Memory 工具集

    将 MemoryStream 和 MemoryRanker 暴露为 Agent 可调用的工具。
    """

    def __init__(
        self,
        memory_stream=None,
        memory_ranker=None,
    ):
        """
        Args:
            memory_stream: MemoryStream 实例
            memory_ranker: MemoryRanker 实例
        """
        self._stream = memory_stream
        self._ranker = memory_ranker

    def set_memory_stream(self, stream) -> None:
        self._stream = stream

    def set_memory_ranker(self, ranker) -> None:
        self._ranker = ranker

    # ============== 工具定义 ==============

    def get_tools(self) -> List[Tool]:
        """获取所有 Memory 工具定义"""
        return [
            self._memory_write_tool(),
            self._memory_search_tool(),
            self._memory_get_tool(),
        ]

    def _memory_write_tool(self) -> Tool:
        return Tool(
            name="memory_write",
            description=(
                "将重要信息写入长期记忆。用于存储用户偏好、关键事实、"
                "任务结果、空间信息等需要跨会话保留的信息。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "要记忆的内容描述",
                    },
                    "importance": {
                        "type": "number",
                        "description": "重要性评分 (1-10, 10=最重要)",
                        "minimum": 1,
                        "maximum": 10,
                        "default": 5,
                    },
                    "memory_type": {
                        "type": "string",
                        "description": "记忆类型",
                        "enum": [
                            "observation", "reflection", "plan",
                            "fact", "preference", "spatial", "safety",
                        ],
                        "default": "observation",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "标签列表，用于分类",
                        "default": [],
                    },
                },
                "required": ["description"],
            },
            handler=self._handle_memory_write,
            is_async=False,
            timeout=5.0,
        )

    def _memory_search_tool(self) -> Tool:
        return Tool(
            name="memory_search",
            description=(
                "搜索长期记忆。基于语义相关性、时间衰减、重要性、"
                "访问频率和上下文亲和度进行多信号排序，返回最相关的记忆。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索查询",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "返回结果数量",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 20,
                    },
                    "memory_type": {
                        "type": "string",
                        "description": "过滤记忆类型（可选）",
                        "enum": [
                            "observation", "reflection", "plan",
                            "fact", "preference", "spatial", "safety",
                        ],
                    },
                },
                "required": ["query"],
            },
            handler=self._handle_memory_search,
            is_async=False,
            timeout=10.0,
        )

    def _memory_get_tool(self) -> Tool:
        return Tool(
            name="memory_get",
            description="获取指定 ID 的记忆详情。",
            parameters={
                "type": "object",
                "properties": {
                    "memory_id": {
                        "type": "string",
                        "description": "记忆 ID",
                    },
                },
                "required": ["memory_id"],
            },
            handler=self._handle_memory_get,
            is_async=False,
            timeout=5.0,
        )

    # ============== 工具处理函数 ==============

    def _handle_memory_write(self, **kwargs) -> str:
        """处理 memory_write 工具调用"""
        if not self._stream:
            return json.dumps({"error": "记忆系统未初始化"}, ensure_ascii=False)

        from orb.data.memory.memory_stream import MemoryType

        description = kwargs.get("description", "")
        importance = kwargs.get("importance", 5.0)
        memory_type_str = kwargs.get("memory_type", "observation")
        tags = kwargs.get("tags", [])

        try:
            memory_type = MemoryType(memory_type_str)
        except ValueError:
            memory_type = MemoryType.OBSERVATION

        memory = self._stream.create_and_add(
            description=description,
            memory_type=memory_type,
            importance=float(importance),
            tags=tags,
        )

        self.logger.info(
            f"记忆写入: {memory.memory_id[:8]}... "
            f"[{memory_type.value}] importance={importance}"
        )

        return json.dumps({
            "status": "success",
            "memory_id": memory.memory_id,
            "description": description[:100],
            "memory_type": memory_type.value,
            "importance": importance,
        }, ensure_ascii=False)

    def _handle_memory_search(self, **kwargs) -> str:
        """处理 memory_search 工具调用"""
        if not self._stream or not self._ranker:
            return json.dumps({"error": "记忆系统未初始化"}, ensure_ascii=False)

        query = kwargs.get("query", "")
        top_k = kwargs.get("top_k", 5)
        memory_type_str = kwargs.get("memory_type")

        candidates = self._stream.get_all()

        # 类型过滤
        if memory_type_str:
            from orb.data.memory.memory_stream import MemoryType
            try:
                mt = MemoryType(memory_type_str)
                candidates = [m for m in candidates if m.memory_type == mt]
            except ValueError:
                pass

        if not candidates:
            return json.dumps({
                "results": [],
                "total": 0,
                "query": query,
            }, ensure_ascii=False)

        # 排序
        ranked = self._ranker.rank(
            query=query,
            candidates=candidates,
            recently_activated=self._stream.recently_activated,
            top_k=top_k,
        )

        # 记录检索（触发记忆强化）
        for r in ranked:
            self._stream.retrieve(r.memory.memory_id)

        results = []
        for r in ranked:
            results.append({
                "memory_id": r.memory.memory_id,
                "description": r.memory.description,
                "memory_type": r.memory.memory_type.value,
                "importance": r.memory.importance,
                "score": round(r.final_score, 4),
                "signals": r.signals.to_dict(),
            })

        return json.dumps({
            "results": results,
            "total": len(results),
            "query": query,
        }, ensure_ascii=False)

    def _handle_memory_get(self, **kwargs) -> str:
        """处理 memory_get 工具调用"""
        if not self._stream:
            return json.dumps({"error": "记忆系统未初始化"}, ensure_ascii=False)

        memory_id = kwargs.get("memory_id", "")
        memory = self._stream.retrieve(memory_id)

        if not memory:
            return json.dumps({"error": f"记忆不存在: {memory_id}"}, ensure_ascii=False)

        return json.dumps({
            "memory_id": memory.memory_id,
            "description": memory.description,
            "memory_type": memory.memory_type.value,
            "importance": memory.importance,
            "access_count": memory.access_count,
            "memory_strength": round(memory.memory_strength, 2),
            "created_at": memory.created_at,
            "last_accessed_at": memory.last_accessed_at,
            "tags": memory.tags,
        }, ensure_ascii=False)


# ============== 便捷函数 ==============

def create_memory_tools(
    memory_stream=None,
    memory_ranker=None,
) -> MemoryTools:
    """创建 Memory 工具集"""
    return MemoryTools(
        memory_stream=memory_stream,
        memory_ranker=memory_ranker,
    )


def register_memory_tools(
    tool_executor,
    memory_stream=None,
    memory_ranker=None,
) -> MemoryTools:
    """
    创建并注册 Memory 工具到 ToolExecutor

    Args:
        tool_executor: ToolExecutor 实例
        memory_stream: MemoryStream 实例
        memory_ranker: MemoryRanker 实例

    Returns:
        MemoryTools 实例
    """
    tools = MemoryTools(
        memory_stream=memory_stream,
        memory_ranker=memory_ranker,
    )

    for tool in tools.get_tools():
        tool_executor.registry.register(
            name=tool.name,
            handler=tool.handler,
            description=tool.description,
            tags=["memory"],
        )

    return tools
