"""
任务拆解

将复杂任务分解为原子任务，支持模板和LLM智能分解两种模式。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from uuid import uuid4

from kaibrain.system.services.logger import LoggerMixin

if TYPE_CHECKING:
    from kaibrain.system.llm.base import BaseLLM


class TaskType(Enum):
    """任务类型"""
    ATOMIC = "atomic"         # 原子任务
    SEQUENTIAL = "sequential"  # 顺序任务
    PARALLEL = "parallel"     # 并行任务
    CONDITIONAL = "conditional"  # 条件任务


@dataclass
class Task:
    """任务"""
    task_id: str = field(default_factory=lambda: str(uuid4()))
    task_type: TaskType = TaskType.ATOMIC
    name: str = ""
    description: str = ""
    
    # 执行信息
    agent_type: str = ""      # 执行此任务的Agent类型
    input_data: Dict[str, Any] = field(default_factory=dict)
    parameters: Dict[str, Any] = field(default_factory=dict)
    
    # 依赖关系
    dependencies: List[str] = field(default_factory=list)  # 依赖的任务ID
    
    # 条件（用于条件任务）
    condition: Optional[str] = None
    
    # 子任务（用于复合任务）
    subtasks: List["Task"] = field(default_factory=list)
    
    # 结果
    result: Optional[Any] = None
    success: bool = False
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type.value,
            "name": self.name,
            "description": self.description,
            "agent_type": self.agent_type,
            "input_data": self.input_data,
            "parameters": self.parameters,
            "dependencies": self.dependencies,
            "subtasks": [st.to_dict() for st in self.subtasks],
        }


class TaskDecomposer(LoggerMixin):
    """
    任务拆解器
    
    将复杂任务分解为可执行的原子任务。
    支持两种模式：
    1. 模板模式 - 使用预定义的任务模板
    2. LLM模式 - 使用LLM智能分解任务
    """
    
    def __init__(self, llm: Optional["BaseLLM"] = None):
        """
        初始化任务拆解器
        
        Args:
            llm: LLM实例（用于智能分解）
        """
        self._llm = llm
        # 任务模板：任务类型 -> 子任务模板
        self._task_templates: Dict[str, List[Dict[str, Any]]] = {}
        
        # 注册默认模板
        self._register_default_templates()
        
    def _register_default_templates(self) -> None:
        """注册默认任务模板"""
        # 示例：抓取物体任务
        self._task_templates["grasp_object"] = [
            {"name": "detect_object", "agent_type": "vision.object_detect"},
            {"name": "plan_grasp", "agent_type": "cognitive.planning"},
            {"name": "execute_grasp", "agent_type": "action.grasp"},
        ]
        
        # 示例：对话任务
        self._task_templates["conversation"] = [
            {"name": "speech_to_text", "agent_type": "audio.asr"},
            {"name": "understand", "agent_type": "cognitive.qa"},
            {"name": "text_to_speech", "agent_type": "audio.tts"},
        ]
        
    def register_template(
        self,
        task_name: str,
        subtasks: List[Dict[str, Any]],
    ) -> None:
        """
        注册任务模板
        
        Args:
            task_name: 任务名称
            subtasks: 子任务定义列表
        """
        self._task_templates[task_name] = subtasks
        self.logger.info(f"注册任务模板: {task_name}")
        
    def decompose(
        self,
        task_name: str,
        input_data: Optional[Dict[str, Any]] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Task:
        """
        拆解任务
        
        Args:
            task_name: 任务名称
            input_data: 输入数据
            parameters: 参数
            
        Returns:
            Task
        """
        template = self._task_templates.get(task_name)
        
        if not template:
            # 没有模板，作为原子任务
            return Task(
                task_type=TaskType.ATOMIC,
                name=task_name,
                agent_type=task_name,
                input_data=input_data or {},
                parameters=parameters or {},
            )
            
        # 根据模板创建子任务
        subtasks = []
        prev_task_id = None
        
        for i, subtask_def in enumerate(template):
            subtask = Task(
                task_type=TaskType.ATOMIC,
                name=subtask_def["name"],
                agent_type=subtask_def["agent_type"],
                input_data=input_data if i == 0 else {},
                parameters=subtask_def.get("parameters", {}),
            )
            
            # 设置依赖（顺序执行）
            if prev_task_id:
                subtask.dependencies = [prev_task_id]
                
            subtasks.append(subtask)
            prev_task_id = subtask.task_id
            
        # 创建复合任务
        composite_task = Task(
            task_type=TaskType.SEQUENTIAL,
            name=task_name,
            input_data=input_data or {},
            parameters=parameters or {},
            subtasks=subtasks,
        )
        
        self.logger.info(f"任务拆解完成: {task_name} -> {len(subtasks)} 个子任务")
        return composite_task
        
    def decompose_parallel(
        self,
        task_name: str,
        subtask_defs: List[Dict[str, Any]],
    ) -> Task:
        """
        创建并行任务
        
        Args:
            task_name: 任务名称
            subtask_defs: 子任务定义列表
            
        Returns:
            Task
        """
        subtasks = [
            Task(
                task_type=TaskType.ATOMIC,
                name=subtask_def["name"],
                agent_type=subtask_def["agent_type"],
                input_data=subtask_def.get("input_data", {}),
                parameters=subtask_def.get("parameters", {}),
            )
            for subtask_def in subtask_defs
        ]
        
        return Task(
            task_type=TaskType.PARALLEL,
            name=task_name,
            subtasks=subtasks,
        )
    
    # ============== LLM智能分解 ==============
    
    async def smart_decompose(
        self,
        task_description: str,
        available_agents: Optional[List[str]] = None,
        available_tools: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Task:
        """
        使用LLM智能分解任务
        
        Args:
            task_description: 任务描述（自然语言）
            available_agents: 可用的Agent类型列表
            available_tools: 可用的工具列表
            context: 额外上下文
            
        Returns:
            分解后的Task
            
        Raises:
            RuntimeError: 如果没有配置LLM
        """
        if not self._llm:
            raise RuntimeError("TaskDecomposer没有配置LLM，无法进行智能分解")
        
        from kaibrain.system.llm.message import LLMMessage
        
        # 构建分解提示
        prompt = self._build_decompose_prompt(
            task_description,
            available_agents,
            available_tools,
            context,
        )
        
        # 调用LLM
        response = await self._llm.chat(
            messages=[
                LLMMessage.system(self._get_decomposer_system_prompt()),
                LLMMessage.user(prompt),
            ],
            temperature=0.3,  # 低温度保证输出稳定
        )
        
        # 解析LLM输出
        try:
            task = self._parse_llm_decomposition(response.content, task_description)
            self.logger.info(f"LLM分解任务完成: {task_description[:50]}... -> {len(task.subtasks)} 个子任务")
            return task
        except Exception as e:
            self.logger.error(f"解析LLM分解结果失败: {e}")
            # 降级为原子任务
            return Task(
                task_type=TaskType.ATOMIC,
                name="task",
                description=task_description,
                agent_type="smart_agent",
            )
    
    def _get_decomposer_system_prompt(self) -> str:
        """获取分解器的系统提示词"""
        return """你是一个任务分解专家。你的工作是将复杂任务分解为简单、可执行的子任务。

分解原则：
1. 每个子任务应该是原子性的，可以独立执行
2. 子任务之间的依赖关系要明确
3. 考虑任务的执行顺序（串行/并行）
4. 为每个子任务指定合适的执行者（Agent类型或工具）

输出格式要求（严格JSON）：
{
    "task_type": "sequential" 或 "parallel",
    "subtasks": [
        {
            "name": "子任务名称",
            "description": "子任务描述",
            "agent_type": "执行者类型",
            "dependencies": ["依赖的子任务名称列表，可为空"],
            "parameters": {"参数名": "参数值"}
        }
    ]
}

注意：
- 只输出JSON，不要有其他内容
- agent_type应该从可用的Agent/工具列表中选择
- 如果任务简单，可以只有一个子任务"""
    
    def _build_decompose_prompt(
        self,
        task_description: str,
        available_agents: Optional[List[str]],
        available_tools: Optional[List[str]],
        context: Optional[Dict[str, Any]],
    ) -> str:
        """构建分解提示"""
        prompt_parts = [f"请分解以下任务：\n{task_description}"]
        
        if available_agents:
            prompt_parts.append(f"\n可用的Agent类型：\n{', '.join(available_agents)}")
        
        if available_tools:
            prompt_parts.append(f"\n可用的工具：\n{', '.join(available_tools)}")
        
        if context:
            prompt_parts.append(f"\n上下文信息：\n{json.dumps(context, ensure_ascii=False, indent=2)}")
        
        return "\n".join(prompt_parts)
    
    def _parse_llm_decomposition(self, llm_output: str, task_description: str) -> Task:
        """解析LLM的分解输出"""
        # 提取JSON
        json_str = llm_output.strip()
        
        # 尝试找到JSON块
        if "```json" in json_str:
            start = json_str.find("```json") + 7
            end = json_str.find("```", start)
            json_str = json_str[start:end].strip()
        elif "```" in json_str:
            start = json_str.find("```") + 3
            end = json_str.find("```", start)
            json_str = json_str[start:end].strip()
        
        # 解析JSON
        data = json.loads(json_str)
        
        # 构建Task
        task_type_str = data.get("task_type", "sequential")
        task_type = TaskType.SEQUENTIAL if task_type_str == "sequential" else TaskType.PARALLEL
        
        subtasks = []
        name_to_id = {}  # 用于处理依赖
        
        for st_data in data.get("subtasks", []):
            subtask = Task(
                task_type=TaskType.ATOMIC,
                name=st_data.get("name", "subtask"),
                description=st_data.get("description", ""),
                agent_type=st_data.get("agent_type", "smart_agent"),
                parameters=st_data.get("parameters", {}),
            )
            name_to_id[subtask.name] = subtask.task_id
            subtasks.append(subtask)
        
        # 处理依赖关系
        for i, st_data in enumerate(data.get("subtasks", [])):
            deps = st_data.get("dependencies", [])
            subtasks[i].dependencies = [name_to_id[d] for d in deps if d in name_to_id]
        
        return Task(
            task_type=task_type,
            name="decomposed_task",
            description=task_description,
            subtasks=subtasks,
        )
    
    async def analyze_task(self, task_description: str) -> Dict[str, Any]:
        """
        分析任务（不分解，只分析）
        
        Args:
            task_description: 任务描述
            
        Returns:
            分析结果
        """
        if not self._llm:
            return {"complexity": "unknown", "estimated_steps": 1}
        
        from kaibrain.system.llm.message import LLMMessage
        
        response = await self._llm.chat(
            messages=[
                LLMMessage.system("分析任务复杂度和所需步骤。只输出JSON格式。"),
                LLMMessage.user(f"""分析这个任务：{task_description}

输出格式：
{{
    "complexity": "simple" 或 "medium" 或 "complex",
    "estimated_steps": 预估步骤数,
    "required_capabilities": ["所需能力列表"],
    "potential_challenges": ["潜在挑战"]
}}"""),
            ],
            temperature=0.3,
        )
        
        try:
            json_str = response.content.strip()
            if "```" in json_str:
                start = json_str.find("```") + 3
                if json_str[start:start+4] == "json":
                    start += 4
                end = json_str.find("```", start)
                json_str = json_str[start:end].strip()
            return json.loads(json_str)
        except:
            return {"complexity": "unknown", "estimated_steps": 1}
