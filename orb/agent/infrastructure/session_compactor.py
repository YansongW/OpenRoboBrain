"""
会话压缩器 (Session Compactor)

实现会话上下文的自动压缩，防止 context window 溢出。

功能:
1. Token 估算: 近似计算消息列表的 token 数
2. Session Pruning: LLM 调用前修剪旧的 tool results
3. LLM 摘要压缩: 调用 LLM 将旧消息压缩为摘要
4. 自动触发: 当 token 接近 context_window - reserve 时触发

借鉴 OpenClaw 的 reserveTokensFloor + softThresholdTokens 策略。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from orb.system.services.logger import LoggerMixin

if TYPE_CHECKING:
    from orb.system.llm.base import BaseLLM
    from orb.agent.infrastructure.session_store import (
        Session,
        SessionMessage,
        SessionStore,
    )


@dataclass
class CompactionConfig:
    """压缩配置"""
    # Context window 参数
    context_window: int = 128000          # 模型 context window 大小 (tokens)
    reserve_tokens_floor: int = 20000     # 为新回复保留的 token 数
    soft_threshold_tokens: int = 4000     # 软阈值 (触发 memory flush)

    # Pruning 参数
    prune_old_tool_results: bool = True   # 是否修剪旧的 tool results
    tool_result_max_age_turns: int = 5    # tool result 保留的最大轮次数
    tool_result_max_chars: int = 500      # tool result 截断长度

    # 压缩参数
    compaction_ratio: float = 0.5         # 压缩时保留最近 50% 的消息原文
    summary_max_tokens: int = 1000        # 摘要最大 token 数

    # Token 估算
    chars_per_token: float = 4.0          # 字符/token 估算比（中文约 1.5，英文约 4）


@dataclass
class CompactionResult:
    """压缩结果"""
    success: bool = True
    original_messages: int = 0
    compacted_messages: int = 0
    original_tokens: int = 0
    compacted_tokens: int = 0
    summary: str = ""
    pruned_tool_results: int = 0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "original_messages": self.original_messages,
            "compacted_messages": self.compacted_messages,
            "original_tokens": self.original_tokens,
            "compacted_tokens": self.compacted_tokens,
            "summary_length": len(self.summary),
            "pruned_tool_results": self.pruned_tool_results,
            "error": self.error,
        }


class SessionCompactor(LoggerMixin):
    """
    会话压缩器

    负责：
    - 估算 token 数
    - 修剪旧的 tool results (pruning)
    - 调用 LLM 生成摘要 (compaction)
    - 判断是否需要压缩 (auto-trigger)
    """

    # 压缩摘要的系统提示词
    COMPACTION_SYSTEM_PROMPT = """你是一个对话摘要助手。请将以下对话历史压缩为简明摘要。

要求：
1. 保留所有关键事实、决策和用户偏好
2. 保留任何尚未完成的任务状态
3. 保留重要的工具调用结果和环境状态变化
4. 省略重复的问候、确认和无关紧要的内容
5. 使用简洁的要点列表格式

输出格式：
## 对话摘要
- [关键信息1]
- [关键信息2]
...

## 未完成任务
- [任务1]
...

## 用户偏好
- [偏好1]
..."""

    def __init__(
        self,
        config: Optional[CompactionConfig] = None,
        llm: Optional["BaseLLM"] = None,
    ):
        """
        初始化压缩器

        Args:
            config: 压缩配置
            llm: LLM 实例 (用于生成摘要，可选)
        """
        self._config = config or CompactionConfig()
        self._llm = llm

        # 统计
        self._total_compactions = 0
        self._total_prunings = 0
        self._total_tokens_saved = 0

    @property
    def config(self) -> CompactionConfig:
        return self._config

    @config.setter
    def config(self, value: CompactionConfig) -> None:
        self._config = value

    def set_llm(self, llm: "BaseLLM") -> None:
        """设置 LLM 实例"""
        self._llm = llm

    # ============== Token 估算 ==============

    def estimate_tokens(self, text: str) -> int:
        """
        估算文本的 token 数

        使用简单的字符/token 比估算。
        中文文本约 1.5 字符/token，英文约 4 字符/token。
        混合文本取折中值。

        Args:
            text: 文本

        Returns:
            估算的 token 数
        """
        if not text:
            return 0

        # 统计中文字符比例以调整估算
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        total_chars = len(text)

        if total_chars == 0:
            return 0

        chinese_ratio = chinese_chars / total_chars

        # 中文约 1.5 字符/token，英文约 4 字符/token
        avg_chars_per_token = 1.5 * chinese_ratio + 4.0 * (1 - chinese_ratio)

        return max(1, int(total_chars / avg_chars_per_token))

    def estimate_messages_tokens(self, messages: list) -> int:
        """
        估算消息列表的总 token 数

        Args:
            messages: SessionMessage 列表

        Returns:
            估算的 token 总数
        """
        total = 0
        for msg in messages:
            # 消息内容
            content = getattr(msg, 'content', '') or ''
            total += self.estimate_tokens(content)

            # 角色标识 (约 4 tokens)
            total += 4

            # tool result (如果有)
            tool_result = getattr(msg, 'tool_result', None)
            if tool_result:
                total += self.estimate_tokens(str(tool_result))

        return total

    # ============== 自动触发检测 ==============

    def should_compact(self, messages: list) -> bool:
        """
        判断是否需要压缩

        当 token 接近 context_window - reserve_tokens_floor 时触发。

        Args:
            messages: 当前消息列表

        Returns:
            是否需要压缩
        """
        current_tokens = self.estimate_messages_tokens(messages)
        threshold = self._config.context_window - self._config.reserve_tokens_floor

        return current_tokens >= threshold

    def should_memory_flush(self, messages: list) -> bool:
        """
        判断是否需要 memory flush (在压缩前保存持久记忆)

        当 token 接近 context_window - reserve - softThreshold 时触发。

        Args:
            messages: 当前消息列表

        Returns:
            是否需要 memory flush
        """
        current_tokens = self.estimate_messages_tokens(messages)
        threshold = (
            self._config.context_window
            - self._config.reserve_tokens_floor
            - self._config.soft_threshold_tokens
        )

        return current_tokens >= threshold

    # ============== Session Pruning ==============

    def prune_messages(self, messages: list) -> tuple:
        """
        修剪消息列表 (轻量级，不调用 LLM)

        策略:
        1. 截断旧的 tool results (保留最近 N 轮)
        2. 截断过长的 tool result 内容

        Args:
            messages: SessionMessage 列表

        Returns:
            (pruned_messages, pruned_count) 元组
        """
        if not self._config.prune_old_tool_results:
            return messages, 0

        from orb.agent.infrastructure.session_store import MessageRole

        pruned_count = 0
        result = []

        # 找到最后一条用户消息的索引，用于计算轮次
        user_indices = [
            i for i, m in enumerate(messages)
            if getattr(m, 'role', None) == MessageRole.USER
        ]
        last_user_turn = len(user_indices)

        for i, msg in enumerate(messages):
            role = getattr(msg, 'role', None)

            if role == MessageRole.TOOL:
                # 计算此 tool result 所在的轮次
                preceding_user_count = sum(
                    1 for j in range(i)
                    if getattr(messages[j], 'role', None) == MessageRole.USER
                )
                turns_ago = last_user_turn - preceding_user_count

                if turns_ago > self._config.tool_result_max_age_turns:
                    # 旧的 tool result: 截断内容
                    content = getattr(msg, 'content', '') or ''
                    if len(content) > self._config.tool_result_max_chars:
                        # 创建截断版本 - 修改 content
                        msg.content = (
                            content[:self._config.tool_result_max_chars]
                            + f"\n... (截断，原始 {len(content)} 字符)"
                        )
                        pruned_count += 1

            result.append(msg)

        self._total_prunings += pruned_count
        return result, pruned_count

    # ============== LLM 摘要压缩 ==============

    async def compact(
        self,
        messages: list,
        keep_recent_ratio: Optional[float] = None,
    ) -> CompactionResult:
        """
        执行会话压缩

        策略:
        1. 将旧消息（前半部分）发送给 LLM 生成摘要
        2. 保留最近的消息原文
        3. 用摘要消息 + 最近消息替换原消息列表

        Args:
            messages: 原始消息列表
            keep_recent_ratio: 保留最近消息的比例 (默认使用 config)

        Returns:
            CompactionResult
        """
        from orb.agent.infrastructure.session_store import (
            SessionMessage,
            MessageRole,
        )

        original_count = len(messages)
        original_tokens = self.estimate_messages_tokens(messages)

        if original_count <= 2:
            return CompactionResult(
                success=True,
                original_messages=original_count,
                compacted_messages=original_count,
                original_tokens=original_tokens,
                compacted_tokens=original_tokens,
            )

        ratio = keep_recent_ratio or self._config.compaction_ratio

        # 分割: 旧消息 (要压缩) vs 新消息 (要保留)
        split_idx = max(1, int(original_count * (1 - ratio)))

        # 确保不拆分在 assistant-tool 对中间
        while split_idx < original_count - 1:
            msg_role = getattr(messages[split_idx], 'role', None)
            if msg_role == MessageRole.TOOL:
                split_idx += 1
            else:
                break

        old_messages = messages[:split_idx]
        recent_messages = messages[split_idx:]

        # 生成摘要
        summary = await self._generate_summary(old_messages)

        # 构建压缩后的消息列表
        compacted = []

        # 摘要作为系统消息
        if summary:
            summary_msg = SessionMessage(
                role=MessageRole.SYSTEM,
                content=f"[对话摘要 - 压缩于 {datetime.now().strftime('%Y-%m-%d %H:%M')}]\n\n{summary}",
                metadata={"is_compaction_summary": True, "original_messages": len(old_messages)},
            )
            compacted.append(summary_msg)

        # 保留最近的消息
        compacted.extend(recent_messages)

        compacted_tokens = self.estimate_messages_tokens(compacted)

        self._total_compactions += 1
        self._total_tokens_saved += original_tokens - compacted_tokens

        self.logger.info(
            f"会话压缩完成: {original_count} -> {len(compacted)} 消息, "
            f"{original_tokens} -> {compacted_tokens} tokens "
            f"(节省 {original_tokens - compacted_tokens})"
        )

        return CompactionResult(
            success=True,
            original_messages=original_count,
            compacted_messages=len(compacted),
            original_tokens=original_tokens,
            compacted_tokens=compacted_tokens,
            summary=summary,
        )

    async def _generate_summary(self, messages: list) -> str:
        """
        调用 LLM 生成对话摘要

        Args:
            messages: 要摘要的消息列表

        Returns:
            摘要文本
        """
        # 如果没有 LLM，使用规则生成简单摘要
        if not self._llm:
            return self._rule_based_summary(messages)

        from orb.system.llm.message import LLMMessage

        # 构建摘要请求
        conversation_text = self._format_messages_for_summary(messages)

        try:
            response = await self._llm.chat(
                messages=[
                    LLMMessage.system(self.COMPACTION_SYSTEM_PROMPT),
                    LLMMessage.user(f"请压缩以下对话历史:\n\n{conversation_text}"),
                ],
                temperature=0.3,  # 低温度确保忠实摘要
                max_tokens=self._config.summary_max_tokens,
            )

            return response.content.strip()

        except Exception as e:
            self.logger.warning(f"LLM 摘要生成失败，使用规则摘要: {e}")
            return self._rule_based_summary(messages)

    def _rule_based_summary(self, messages: list) -> str:
        """
        规则生成简单摘要 (LLM 不可用时的 fallback)

        Args:
            messages: 消息列表

        Returns:
            简单摘要
        """
        from orb.agent.infrastructure.session_store import MessageRole

        lines = ["## 对话摘要"]

        user_messages = [
            m for m in messages
            if getattr(m, 'role', None) == MessageRole.USER
        ]
        assistant_messages = [
            m for m in messages
            if getattr(m, 'role', None) == MessageRole.ASSISTANT
        ]

        # 提取用户关键请求
        if user_messages:
            lines.append("\n### 用户请求:")
            for msg in user_messages[-5:]:  # 最近 5 条
                content = (getattr(msg, 'content', '') or '')[:100]
                if content:
                    lines.append(f"- {content}")

        # 提取助手关键响应
        if assistant_messages:
            lines.append("\n### 系统响应:")
            for msg in assistant_messages[-3:]:  # 最近 3 条
                content = (getattr(msg, 'content', '') or '')[:150]
                if content:
                    lines.append(f"- {content}")

        lines.append(f"\n(共 {len(messages)} 条消息被压缩)")

        return "\n".join(lines)

    def _format_messages_for_summary(self, messages: list) -> str:
        """将消息格式化为文本，用于摘要"""
        lines = []
        for msg in messages:
            role = getattr(msg, 'role', None)
            content = getattr(msg, 'content', '') or ''

            if role:
                role_str = role.value if hasattr(role, 'value') else str(role)
            else:
                role_str = "unknown"

            if content:
                # 截断过长的单条消息
                if len(content) > 500:
                    content = content[:500] + "..."
                lines.append(f"[{role_str}]: {content}")

        return "\n".join(lines)

    # ============== 完整流程 ==============

    async def auto_compact_if_needed(
        self,
        session: "Session",
        session_store: "SessionStore",
    ) -> Optional[CompactionResult]:
        """
        自动检测并执行压缩

        完整流程:
        1. 检查是否达到压缩阈值
        2. 先执行 pruning
        3. 如果仍然超出，执行 LLM 摘要压缩
        4. 调用 session_store.compact_session 持久化

        Args:
            session: 会话对象
            session_store: 会话存储

        Returns:
            CompactionResult 或 None (如果不需要压缩)
        """
        messages = session.messages

        if not self.should_compact(messages):
            return None

        self.logger.info(
            f"会话 {session.session_id} 需要压缩 "
            f"({len(messages)} 消息, ~{self.estimate_messages_tokens(messages)} tokens)"
        )

        # Step 1: Pruning
        pruned_messages, pruned_count = self.prune_messages(messages)

        # Step 2: 检查 pruning 后是否仍需压缩
        if not self.should_compact(pruned_messages):
            self.logger.info(f"Pruning 足够，无需压缩 (修剪了 {pruned_count} 条)")
            # 更新 session
            session.messages = pruned_messages
            return CompactionResult(
                success=True,
                original_messages=len(messages),
                compacted_messages=len(pruned_messages),
                original_tokens=self.estimate_messages_tokens(messages),
                compacted_tokens=self.estimate_messages_tokens(pruned_messages),
                pruned_tool_results=pruned_count,
            )

        # Step 3: LLM 摘要压缩
        result = await self.compact(pruned_messages)

        if result.success:
            # Step 4: 持久化
            from orb.agent.infrastructure.session_store import SessionMessage
            # compact 返回的 compacted_messages 数据在 result 中
            # 需要重新构建压缩后的消息列表
            compacted_messages = await self._build_compacted_messages(
                pruned_messages, result.summary
            )
            await session_store.compact_session(
                session.session_id,
                compacted_messages,
            )
            result.pruned_tool_results = pruned_count

        return result

    async def _build_compacted_messages(
        self,
        messages: list,
        summary: str,
    ) -> list:
        """构建压缩后的消息列表"""
        from orb.agent.infrastructure.session_store import (
            SessionMessage,
            MessageRole,
        )

        ratio = self._config.compaction_ratio
        split_idx = max(1, int(len(messages) * (1 - ratio)))

        # 跳过 tool 消息的拆分问题
        while split_idx < len(messages) - 1:
            msg_role = getattr(messages[split_idx], 'role', None)
            if msg_role == MessageRole.TOOL:
                split_idx += 1
            else:
                break

        recent_messages = messages[split_idx:]

        compacted = []

        if summary:
            compacted.append(SessionMessage(
                role=MessageRole.SYSTEM,
                content=f"[对话摘要 - 压缩于 {datetime.now().strftime('%Y-%m-%d %H:%M')}]\n\n{summary}",
                metadata={"is_compaction_summary": True},
            ))

        compacted.extend(recent_messages)
        return compacted

    # ============== 统计 ==============

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_compactions": self._total_compactions,
            "total_prunings": self._total_prunings,
            "total_tokens_saved": self._total_tokens_saved,
            "config": {
                "context_window": self._config.context_window,
                "reserve_tokens_floor": self._config.reserve_tokens_floor,
                "compaction_ratio": self._config.compaction_ratio,
            },
        }


# ============== 便捷函数 ==============

def create_session_compactor(
    context_window: int = 128000,
    reserve_tokens: int = 20000,
    llm: Optional["BaseLLM"] = None,
    **kwargs,
) -> SessionCompactor:
    """
    创建会话压缩器

    Args:
        context_window: context window 大小
        reserve_tokens: 保留 token 数
        llm: LLM 实例
        **kwargs: 其他 CompactionConfig 参数

    Returns:
        SessionCompactor 实例
    """
    config = CompactionConfig(
        context_window=context_window,
        reserve_tokens_floor=reserve_tokens,
        **kwargs,
    )
    return SessionCompactor(config=config, llm=llm)
