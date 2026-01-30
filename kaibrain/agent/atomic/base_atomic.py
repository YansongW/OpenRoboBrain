"""
原子Agent基类

所有子能力Agent的基类。
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from kaibrain.agent.base import BaseAgent, AgentLevel
from kaibrain.system.brain_pipeline.protocol import Message, MessageType

if TYPE_CHECKING:
    from kaibrain.system.brain_pipeline.message_bus import MessageBus


class AtomicAgent(BaseAgent):
    """
    原子Agent基类
    
    子能力Agent专注于单一能力，像神经元一样：
    - 接收输入 → 处理 → 输出结果
    - 通过显性数据（工作流记忆）与其他Agent建立关联
    - 可动态注册/删除（由Super Agent管理）
    """
    
    def __init__(
        self,
        name: str,
        agent_type: str,
        capabilities: Optional[List[str]] = None,
        message_bus: Optional[MessageBus] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        初始化原子Agent
        
        Args:
            name: Agent名称
            agent_type: Agent类型
            capabilities: 能力列表
            message_bus: 消息总线
            config: 配置
        """
        super().__init__(
            name=name,
            agent_type=agent_type,
            level=AgentLevel.ATOMIC,
            message_bus=message_bus,
            config=config,
        )
        
        self._info.capabilities = capabilities or []
        
    async def process(self, message: Message) -> Optional[Message]:
        """
        处理消息
        
        Args:
            message: 输入消息
            
        Returns:
            响应消息
        """
        msg_type = message.type
        
        if msg_type == MessageType.TASK_REQUEST:
            return await self._handle_task_request(message)
            
        elif msg_type == MessageType.DATA_QUERY:
            return await self._handle_data_query(message)
            
        return None
        
    async def _handle_task_request(self, message: Message) -> Message:
        """
        处理任务请求
        
        Args:
            message: 任务请求消息
            
        Returns:
            响应消息
        """
        payload = message.payload
        task_id = payload.get("task_id", "")
        input_data = payload.get("input_data", {})
        parameters = payload.get("parameters", {})
        
        self.logger.info(f"执行任务: {self.name} - {task_id}")
        
        try:
            # 调用子类实现的执行方法
            result = await self.execute(input_data, parameters)
            
            return message.create_response({
                "success": True,
                "task_id": task_id,
                "result": result,
            })
            
        except Exception as e:
            self.logger.error(f"任务执行失败: {e}")
            
            return message.create_response({
                "success": False,
                "task_id": task_id,
                "error": str(e),
            })
            
    async def _handle_data_query(self, message: Message) -> Message:
        """处理数据查询"""
        query = message.payload.get("query", {})
        
        try:
            result = await self.query(query)
            
            return message.create_response({
                "success": True,
                "result": result,
            })
            
        except Exception as e:
            return message.create_response({
                "success": False,
                "error": str(e),
            })
            
    # ============== 子类需要实现的方法 ==============
    
    @abstractmethod
    async def execute(
        self,
        input_data: Dict[str, Any],
        parameters: Dict[str, Any],
    ) -> Any:
        """
        执行任务（核心能力实现）
        
        Args:
            input_data: 输入数据
            parameters: 参数
            
        Returns:
            执行结果
        """
        pass
        
    async def query(self, query: Dict[str, Any]) -> Any:
        """
        查询（可选实现）
        
        Args:
            query: 查询条件
            
        Returns:
            查询结果
        """
        return {}
