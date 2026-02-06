"""
对话管理器 (Dialogue Manager)

自由推理式对话理解，不做枚举分类。

核心理念：
- LLM 像人一样理解用户输入：用户说了什么 → 为什么这么说 → 我该怎么做
- 不使用 IntentType 枚举，行为从 LLM 推理中涌现
- 完整记录推理链，为调试和未来反思学习提供数据

位置: 能力层 (Capability Layer) → 交互能力 (interaction/)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from uuid import uuid4

from orb.system.services.logger import LoggerMixin, get_logger

if TYPE_CHECKING:
    from orb.system.llm.base import BaseLLM

logger = get_logger(__name__)


# ============== 数据结构 ==============


@dataclass
class Turn:
    """对话轮次"""
    role: str                  # "user" 或 "assistant"
    content: str               # 对话内容
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DialogueContext:
    """
    对话上下文

    DialogueManager 用来构建理解所需的上下文信息。
    """
    history: List[Turn] = field(default_factory=list)
    memory_snippets: List[str] = field(default_factory=list)
    active_task: Optional[str] = None
    world_state: Dict[str, Any] = field(default_factory=dict)

    def add_turn(self, role: str, content: str, **metadata) -> None:
        self.history.append(Turn(role=role, content=content, metadata=metadata))
        # 保持历史长度合理
        if len(self.history) > 20:
            self.history = self.history[-20:]

    def get_history_text(self, max_turns: int = 10) -> str:
        """将近 N 轮对话格式化为文本"""
        recent = self.history[-max_turns:]
        lines = []
        for t in recent:
            role_label = "用户" if t.role == "user" else "助手"
            lines.append(f"{role_label}: {t.content}")
        return "\n".join(lines)


@dataclass
class Understanding:
    """
    LLM 对用户输入的自由推理结果

    不做枚举分类，所有字段都是 LLM 自由推理的产物。
    """
    raw_input: str                          # 用户原始输入
    reasoning: str                          # LLM 的完整推理过程（思维链）
    summary: str                            # 推理结论的简短摘要
    requires_action: bool                   # 是否需要物理动作（从推理中提取）
    suggested_response: str                 # LLM 建议的回复
    action_description: str = ""            # 如需行动，描述要做什么
    context_used: List[str] = field(default_factory=list)
    trace_id: str = ""
    llm_time_ms: float = 0.0               # LLM 推理耗时
    raw_llm_output: str = ""                # LLM 原始输出（完整保留）

    def to_log_dict(self) -> Dict[str, Any]:
        """转换为日志友好的字典"""
        return {
            "trace_id": self.trace_id,
            "raw_input": self.raw_input,
            "summary": self.summary,
            "requires_action": self.requires_action,
            "action_description": self.action_description,
            "suggested_response": self.suggested_response[:100],
            "reasoning_length": len(self.reasoning),
            "llm_time_ms": self.llm_time_ms,
        }


# ============== 提示词 ==============

UNDERSTANDING_PROMPT = """你是一个具身智能机器人的大脑。你需要像人一样理解用户说的话。

请按以下步骤思考（输出你的完整思考过程）：

1. **用户说了什么**：复述用户的话，确保你理解了字面意思
2. **用户为什么这么说**：分析用户的真实需求、情绪、上下文
3. **是否需要物理动作**：判断是否需要机器人做出物理行动（移动、抓取等）
4. **我该怎么做**：如果需要行动，描述具体要做什么；如果不需要，想好怎么回复

然后用以下 JSON 格式输出你的结论（思考过程之后）：
```json
{
    "summary": "一句话总结你的理解",
    "requires_action": true或false,
    "action_description": "如需行动，描述要做什么（不需要则留空）",
    "suggested_response": "你对用户说的话"
}
```

重要：
- 你的思考过程要完整、自然，像人一样推理
- 不要简单分类，要真正理解用户的意图和情感
- "这里好暗" 这样的话，人会推理出需要开灯，你也应该这样
- "好渴啊" 这样的话，人会想到帮忙倒水
- 闲聊时不需要行动，但要友好回复
- 如果不确定用户要什么，在 suggested_response 中追问"""


# ============== DialogueManager ==============


class DialogueManager(LoggerMixin):
    """
    对话管理器

    自由推理式理解，不做枚举分类。
    让 LLM 像人一样思考：
    "用户说了什么 → 他为什么这么说 → 我该怎么做"

    位置: 能力层 (Capability Layer) → 交互能力 (interaction/)
    """

    def __init__(self, llm: "BaseLLM"):
        """
        初始化对话管理器

        Args:
            llm: LLM 实例（用于推理）
        """
        self._llm = llm
        self._context = DialogueContext()
        self._understanding_count = 0

    @property
    def context(self) -> DialogueContext:
        """当前对话上下文"""
        return self._context

    async def understand(
        self,
        user_input: str,
        trace_id: str = "",
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> Understanding:
        """
        自由推理用户意图。

        LLM 输出完整思维链，从推理中自然得出结论。
        所有推理过程完整记录。

        Args:
            user_input: 用户输入
            trace_id: 追踪 ID
            extra_context: 额外上下文（记忆片段等）

        Returns:
            Understanding 推理结果
        """
        from orb.system.llm.message import LLMMessage

        trace_id = trace_id or f"trace-{uuid4().hex[:8]}"
        start_time = time.time()

        # 构建消息
        messages = self._build_understanding_messages(user_input, extra_context)

        # LLM 推理
        try:
            response = await self._llm.chat(
                messages=messages,
                temperature=0.7,
                max_tokens=1024,
            )
            raw_output = response.content if hasattr(response, 'content') else str(response)
        except Exception as e:
            logger.error(f"[{trace_id}] DialogueManager LLM 调用失败: {e}")
            return Understanding(
                raw_input=user_input,
                reasoning=f"LLM 调用失败: {e}",
                summary="无法理解用户输入",
                requires_action=False,
                suggested_response="抱歉，我暂时无法处理您的请求，请稍后再试。",
                trace_id=trace_id,
                llm_time_ms=(time.time() - start_time) * 1000,
                raw_llm_output="",
            )

        llm_time = (time.time() - start_time) * 1000

        # 解析推理结果
        understanding = self._parse_understanding(raw_output, user_input, trace_id, llm_time)

        # 记录到上下文
        self._context.add_turn("user", user_input, trace_id=trace_id)

        self._understanding_count += 1

        # 日志
        logger.info(
            f"[{trace_id}] 推理完成: {understanding.summary} "
            f"(action={understanding.requires_action}, {llm_time:.0f}ms)"
        )
        logger.debug(
            f"[{trace_id}] 思维链: {understanding.reasoning[:200]}..."
        )

        return understanding

    async def generate_reply(
        self,
        understanding: Understanding,
    ) -> str:
        """
        生成自然语言回复。

        如果 understanding 已包含 suggested_response 且质量足够，直接使用。
        否则单独调用 LLM 生成回复。

        Args:
            understanding: 推理结果

        Returns:
            回复文本
        """
        reply = understanding.suggested_response

        if reply:
            # 记录助手回复到上下文
            self._context.add_turn(
                "assistant", reply,
                trace_id=understanding.trace_id,
            )
            return reply

        # fallback: 用 LLM 单独生成回复
        return "我理解了。"

    def _build_understanding_messages(
        self,
        user_input: str,
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> list:
        """构建理解用的 LLM 消息"""
        from orb.system.llm.message import LLMMessage

        messages = []

        # 系统提示词
        system_prompt = UNDERSTANDING_PROMPT

        # 注入对话历史
        history_text = self._context.get_history_text(max_turns=6)
        if history_text:
            system_prompt += f"\n\n最近的对话历史:\n{history_text}"

        # 注入记忆片段
        if extra_context and extra_context.get("memory_snippets"):
            snippets = extra_context["memory_snippets"]
            system_prompt += f"\n\n相关记忆:\n" + "\n".join(f"- {s}" for s in snippets)

        # 注入当前任务
        if self._context.active_task:
            system_prompt += f"\n\n当前正在执行的任务: {self._context.active_task}"

        messages.append(LLMMessage(role="system", content=system_prompt))
        messages.append(LLMMessage(role="user", content=user_input))

        return messages

    def _parse_understanding(
        self,
        raw_output: str,
        user_input: str,
        trace_id: str,
        llm_time_ms: float,
    ) -> Understanding:
        """
        从 LLM 输出中解析 Understanding。

        LLM 输出格式: 思维链文本 + JSON 结论
        """
        import re

        reasoning = raw_output  # 完整保留原始输出作为推理链

        # 尝试从输出中提取 JSON 结论
        json_data = self._extract_json(raw_output)

        if json_data:
            return Understanding(
                raw_input=user_input,
                reasoning=reasoning,
                summary=json_data.get("summary", ""),
                requires_action=json_data.get("requires_action", False),
                action_description=json_data.get("action_description", ""),
                suggested_response=json_data.get("suggested_response", ""),
                trace_id=trace_id,
                llm_time_ms=llm_time_ms,
                raw_llm_output=raw_output,
            )

        # JSON 解析失败，从纯文本推断
        logger.warning(f"[{trace_id}] 推理输出无 JSON，从文本推断")
        return Understanding(
            raw_input=user_input,
            reasoning=reasoning,
            summary=raw_output[:100],
            requires_action=False,  # 安全默认：不行动
            suggested_response=raw_output.strip(),
            trace_id=trace_id,
            llm_time_ms=llm_time_ms,
            raw_llm_output=raw_output,
        )

    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        """从文本中提取 JSON（支持代码块和混合格式）"""
        import re

        # 1. 代码块中的 JSON
        match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
        if match:
            try:
                return json.loads(match.group(1))
            except (json.JSONDecodeError, TypeError):
                pass

        # 2. 直接 JSON
        try:
            return json.loads(text.strip())
        except (json.JSONDecodeError, TypeError):
            pass

        # 3. 文本中嵌入的 JSON 对象
        brace_start = text.rfind('{"')
        if brace_start >= 0:
            depth = 0
            for i in range(brace_start, len(text)):
                if text[i] == '{':
                    depth += 1
                elif text[i] == '}':
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[brace_start:i+1])
                        except (json.JSONDecodeError, TypeError):
                            pass
                        break

        return None

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "understanding_count": self._understanding_count,
            "context_turns": len(self._context.history),
            "active_task": self._context.active_task,
        }
