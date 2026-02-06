"""
任务拆解

将复杂任务分解为原子任务，支持模板和LLM智能分解两种模式。

功能：
1. 模板模式 - 使用预定义的任务模板进行拆解
2. LLM模式 - 使用大语言模型智能分解任务
3. 规则模式 - 基于关键词规则的快速分解（fallback）
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING
from uuid import uuid4

from orb.system.services.logger import LoggerMixin

if TYPE_CHECKING:
    from orb.system.llm.base import BaseLLM


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
        # ============== 物体操作类 ==============
        # 抓取物体
        self._task_templates["grasp_object"] = [
            {"name": "detect_object", "agent_type": "vision.object_detect", "description": "检测目标物体"},
            {"name": "plan_grasp", "agent_type": "cognitive.planning", "description": "规划抓取路径"},
            {"name": "execute_grasp", "agent_type": "action.grasp", "description": "执行抓取动作"},
        ]
        
        # 放置物体
        self._task_templates["place_object"] = [
            {"name": "detect_target", "agent_type": "vision.object_detect", "description": "检测目标位置"},
            {"name": "plan_place", "agent_type": "cognitive.planning", "description": "规划放置路径"},
            {"name": "execute_place", "agent_type": "action.place", "description": "执行放置动作"},
        ]
        
        # 递送物品（fetch and deliver）
        self._task_templates["fetch_deliver"] = [
            {"name": "navigate_to_source", "agent_type": "navigation.goto", "description": "导航到取物地点"},
            {"name": "detect_object", "agent_type": "vision.object_detect", "description": "检测目标物体"},
            {"name": "grasp_object", "agent_type": "action.grasp", "description": "抓取物体"},
            {"name": "navigate_to_target", "agent_type": "navigation.goto", "description": "导航到目标地点"},
            {"name": "place_object", "agent_type": "action.place", "description": "放置物体"},
        ]
        
        # ============== 导航类 ==============
        # 简单导航
        self._task_templates["navigate"] = [
            {"name": "localize", "agent_type": "navigation.localize", "description": "定位当前位置"},
            {"name": "plan_path", "agent_type": "navigation.planning", "description": "规划路径"},
            {"name": "execute_navigation", "agent_type": "navigation.execute", "description": "执行导航"},
        ]
        
        # 巡逻
        self._task_templates["patrol"] = [
            {"name": "get_waypoints", "agent_type": "cognitive.planning", "description": "获取巡逻路径点"},
            {"name": "navigate_loop", "agent_type": "navigation.patrol", "description": "循环导航"},
            {"name": "monitor_environment", "agent_type": "vision.monitor", "description": "监控环境"},
        ]
        
        # ============== 对话交互类 ==============
        # 语音对话
        self._task_templates["conversation"] = [
            {"name": "speech_to_text", "agent_type": "audio.asr", "description": "语音转文字"},
            {"name": "understand", "agent_type": "cognitive.qa", "description": "理解意图"},
            {"name": "text_to_speech", "agent_type": "audio.tts", "description": "文字转语音"},
        ]
        
        # ============== 日常任务类 ==============
        # 倒水
        self._task_templates["pour_water"] = [
            {"name": "find_cup", "agent_type": "vision.object_detect", "description": "找到杯子"},
            {"name": "find_water_source", "agent_type": "vision.object_detect", "description": "找到水源"},
            {"name": "navigate_to_water", "agent_type": "navigation.goto", "description": "移动到水源位置"},
            {"name": "grasp_water_container", "agent_type": "action.grasp", "description": "抓取水壶/饮水机"},
            {"name": "pour", "agent_type": "action.pour", "description": "倒水"},
            {"name": "navigate_to_user", "agent_type": "navigation.goto", "description": "移动到用户位置"},
            {"name": "deliver_cup", "agent_type": "action.deliver", "description": "递送杯子"},
        ]
        
        # 清洁
        self._task_templates["clean_area"] = [
            {"name": "survey_area", "agent_type": "vision.scene_understand", "description": "扫描区域"},
            {"name": "plan_cleaning", "agent_type": "cognitive.planning", "description": "规划清洁路径"},
            {"name": "execute_cleaning", "agent_type": "action.clean", "description": "执行清洁"},
            {"name": "verify_result", "agent_type": "vision.verify", "description": "验证清洁结果"},
        ]
        
        # ============== 关键词到模板映射 ==============
        self._keyword_to_template: Dict[str, str] = {
            # 抓取相关
            "拿": "grasp_object",
            "取": "grasp_object",
            "抓": "grasp_object",
            "给我": "fetch_deliver",
            "帮我拿": "fetch_deliver",
            # 放置相关
            "放": "place_object",
            "放下": "place_object",
            # 导航相关
            "去": "navigate",
            "到": "navigate",
            "走到": "navigate",
            "前往": "navigate",
            # 倒水相关
            "倒水": "pour_water",
            "倒杯水": "pour_water",
            # 清洁相关
            "打扫": "clean_area",
            "清洁": "clean_area",
            "擦": "clean_area",
        }
        
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
    
    # ============== 规则基础分解 ==============
    
    def rule_based_decompose(
        self,
        task_description: str,
        input_data: Optional[Dict[str, Any]] = None,
    ) -> Task:
        """
        基于规则的快速分解（当LLM不可用时的fallback）
        
        Args:
            task_description: 任务描述
            input_data: 输入数据
            
        Returns:
            分解后的Task
        """
        self.logger.info(f"使用规则分解任务: {task_description[:50]}...")
        
        # 尝试匹配关键词到模板
        for keyword, template_name in self._keyword_to_template.items():
            if keyword in task_description:
                self.logger.info(f"匹配到模板: {template_name} (关键词: {keyword})")
                return self.decompose(template_name, input_data)
        
        # 无法匹配，分析任务类型
        task_analysis = self._analyze_task_by_rules(task_description)
        
        if task_analysis["is_navigation"]:
            return self._create_navigation_task(task_description, task_analysis)
        elif task_analysis["is_manipulation"]:
            return self._create_manipulation_task(task_description, task_analysis)
        elif task_analysis["is_conversation"]:
            return self._create_conversation_task(task_description)
        else:
            # 默认作为原子任务
            return Task(
                task_type=TaskType.ATOMIC,
                name="general_task",
                description=task_description,
                agent_type="smart_agent",
                input_data=input_data or {},
            )
    
    def _analyze_task_by_rules(self, description: str) -> Dict[str, Any]:
        """基于规则分析任务类型"""
        analysis = {
            "is_navigation": False,
            "is_manipulation": False,
            "is_conversation": False,
            "target_location": None,
            "target_object": None,
        }
        
        # 导航关键词
        nav_keywords = ["去", "到", "走", "前往", "移动", "导航"]
        for kw in nav_keywords:
            if kw in description:
                analysis["is_navigation"] = True
                # 尝试提取目标地点
                match = re.search(f"{kw}(.+?)(?:[，。！？]|$)", description)
                if match:
                    analysis["target_location"] = match.group(1).strip()
                break
        
        # 物体操作关键词
        manip_keywords = ["拿", "取", "抓", "放", "给", "递", "倒", "拿来"]
        for kw in manip_keywords:
            if kw in description:
                analysis["is_manipulation"] = True
                break
        
        # 对话关键词
        conv_keywords = ["说", "告诉", "问", "回答", "聊"]
        for kw in conv_keywords:
            if kw in description:
                analysis["is_conversation"] = True
                break
        
        return analysis
    
    def _create_navigation_task(
        self,
        description: str,
        analysis: Dict[str, Any],
    ) -> Task:
        """创建导航任务"""
        target = analysis.get("target_location", "目标位置")
        
        subtasks = [
            Task(
                task_type=TaskType.ATOMIC,
                name="localize",
                description="确定当前位置",
                agent_type="navigation.localize",
            ),
            Task(
                task_type=TaskType.ATOMIC,
                name="plan_path",
                description=f"规划到{target}的路径",
                agent_type="navigation.planning",
                parameters={"target": target},
            ),
            Task(
                task_type=TaskType.ATOMIC,
                name="execute_navigation",
                description=f"执行导航到{target}",
                agent_type="navigation.execute",
            ),
        ]
        
        # 设置依赖
        subtasks[1].dependencies = [subtasks[0].task_id]
        subtasks[2].dependencies = [subtasks[1].task_id]
        
        return Task(
            task_type=TaskType.SEQUENTIAL,
            name="navigation_task",
            description=description,
            subtasks=subtasks,
        )
    
    def _create_manipulation_task(
        self,
        description: str,
        analysis: Dict[str, Any],
    ) -> Task:
        """创建物体操作任务"""
        subtasks = [
            Task(
                task_type=TaskType.ATOMIC,
                name="detect_object",
                description="检测目标物体",
                agent_type="vision.object_detect",
            ),
            Task(
                task_type=TaskType.ATOMIC,
                name="plan_manipulation",
                description="规划操作路径",
                agent_type="cognitive.planning",
            ),
            Task(
                task_type=TaskType.ATOMIC,
                name="execute_manipulation",
                description="执行操作",
                agent_type="action.manipulate",
            ),
        ]
        
        # 设置依赖
        subtasks[1].dependencies = [subtasks[0].task_id]
        subtasks[2].dependencies = [subtasks[1].task_id]
        
        return Task(
            task_type=TaskType.SEQUENTIAL,
            name="manipulation_task",
            description=description,
            subtasks=subtasks,
        )
    
    def _create_conversation_task(self, description: str) -> Task:
        """创建对话任务"""
        return Task(
            task_type=TaskType.ATOMIC,
            name="conversation",
            description=description,
            agent_type="cognitive.qa",
        )
    
    # ============== LLM智能分解 ==============
    
    async def smart_decompose(
        self,
        task_description: str,
        available_agents: Optional[List[str]] = None,
        available_tools: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
        use_fallback: bool = True,
    ) -> Task:
        """
        使用LLM智能分解任务
        
        Args:
            task_description: 任务描述（自然语言）
            available_agents: 可用的Agent类型列表
            available_tools: 可用的工具列表
            context: 额外上下文
            use_fallback: 当LLM不可用时是否使用规则分解
            
        Returns:
            分解后的Task
        """
        # 如果没有LLM，使用规则分解
        if not self._llm:
            if use_fallback:
                self.logger.warning("LLM未配置，使用规则分解")
                return self.rule_based_decompose(task_description)
            else:
                raise RuntimeError("TaskDecomposer没有配置LLM，无法进行智能分解")
        
        from orb.system.llm.message import LLMMessage
        
        # 设置默认的可用Agent
        if available_agents is None:
            available_agents = self._get_default_available_agents()
        
        # 构建分解提示
        prompt = self._build_decompose_prompt(
            task_description,
            available_agents,
            available_tools,
            context,
        )
        
        try:
            # 调用LLM
            response = await self._llm.chat(
                messages=[
                    LLMMessage.system(self._get_decomposer_system_prompt()),
                    LLMMessage.user(prompt),
                ],
                temperature=0.3,  # 低温度保证输出稳定
            )
            
            # 解析LLM输出
            task = self._parse_llm_decomposition(response.content, task_description)
            self.logger.info(f"LLM分解任务完成: {task_description[:50]}... -> {len(task.subtasks)} 个子任务")
            return task
            
        except Exception as e:
            self.logger.error(f"LLM分解失败: {e}")
            
            if use_fallback:
                self.logger.warning("降级到规则分解")
                return self.rule_based_decompose(task_description)
            else:
                # 降级为原子任务
                return Task(
                    task_type=TaskType.ATOMIC,
                    name="task",
                    description=task_description,
                    agent_type="smart_agent",
                )
    
    def _get_default_available_agents(self) -> List[str]:
        """获取默认可用的Agent类型列表"""
        return [
            # 感知类
            "vision.object_detect",
            "vision.scene_understand",
            "vision.face_recognize",
            "audio.asr",
            "audio.sound_detect",
            # 认知类
            "cognitive.qa",
            "cognitive.planning",
            "cognitive.reasoning",
            # 导航类
            "navigation.localize",
            "navigation.planning",
            "navigation.execute",
            "navigation.goto",
            # 动作类
            "action.grasp",
            "action.place",
            "action.pour",
            "action.manipulate",
            "action.clean",
            "action.deliver",
            # 通用
            "smart_agent",
        ]
    
    def _get_decomposer_system_prompt(self) -> str:
        """获取分解器的系统提示词"""
        return """你是一个机器人任务分解专家。你的工作是将用户的自然语言指令分解为机器人可执行的子任务序列。

## 背景
你在为一个服务机器人（如家庭服务机器人、酒店服务机器人等）分解任务。机器人具备以下能力：
- 视觉感知：物体检测、场景理解、人脸识别
- 语音交互：语音识别、语音合成
- 导航移动：定位、路径规划、自主导航
- 物体操作：抓取、放置、倾倒、递送
- 认知推理：意图理解、任务规划

## 分解原则
1. **原子性**：每个子任务应该是单一、明确的动作
2. **顺序性**：子任务按执行顺序排列，明确依赖关系
3. **可执行性**：每个子任务必须映射到具体的Agent类型
4. **安全性**：考虑任务执行的安全性，必要时添加检查步骤
5. **完整性**：确保任务从开始到结束的完整流程

## Agent类型说明
- vision.object_detect：检测和定位物体
- vision.scene_understand：理解场景布局
- navigation.goto：导航到指定位置
- navigation.planning：规划导航路径
- action.grasp：抓取物体
- action.place：放置物体
- action.pour：倾倒液体
- action.deliver：递送物品
- cognitive.qa：对话问答
- cognitive.planning：复杂任务规划

## 输出格式（严格JSON）
```json
{
    "task_type": "sequential",
    "reasoning": "简要说明分解思路",
    "subtasks": [
        {
            "name": "简短任务名",
            "description": "具体描述",
            "agent_type": "agent类型",
            "dependencies": [],
            "parameters": {}
        }
    ]
}
```

## 注意事项
- 只输出JSON，不要有其他内容
- task_type通常是"sequential"（顺序执行）
- dependencies列表包含此子任务依赖的前置任务名称
- 如果任务非常简单（如问候），可以只有一个子任务"""
    
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
        
        from orb.system.llm.message import LLMMessage
        
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
