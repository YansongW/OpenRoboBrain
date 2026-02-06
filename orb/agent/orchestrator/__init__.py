"""
第二级：编排Agent（调度层）

负责任务编排与输入输出管理：
- 输入管理：接收外部请求，解析任务
- 任务拆解：复杂任务分解为原子任务
- Agent选择：根据任务选择合适的子Agent
- 流程控制：编排执行顺序（串行/并行/条件）
- 输出管理：聚合结果，返回统一响应
"""

from orb.agent.orchestrator.orchestrator import OrchestratorAgent
from orb.agent.orchestrator.task_decomposer import TaskDecomposer
from orb.agent.orchestrator.flow_controller import FlowController

__all__ = ["OrchestratorAgent", "TaskDecomposer", "FlowController"]
