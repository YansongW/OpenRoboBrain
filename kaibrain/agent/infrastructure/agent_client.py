"""
Agent客户端

Agent与大脑管道交互的客户端接口。
"""

from __future__ import annotations

from typing import Any, Dict, Optional, TYPE_CHECKING

from kaibrain.system.brain_pipeline.protocol import Message, MessageType

if TYPE_CHECKING:
    from kaibrain.system.brain_pipeline.message_bus import MessageBus


class AgentClient:
    """
    Agent客户端
    
    提供简化的消息发送和接收接口。
    """
    
    def __init__(self, agent_id: str, message_bus: MessageBus):
        """
        初始化客户端
        
        Args:
            agent_id: Agent ID
            message_bus: 消息总线
        """
        self.agent_id = agent_id
        self.message_bus = message_bus
        
    async def send_task(
        self,
        target: str,
        task_type: str,
        input_data: Optional[Dict[str, Any]] = None,
        parameters: Optional[Dict[str, Any]] = None,
        timeout: float = 60.0,
    ) -> Optional[Dict[str, Any]]:
        """
        发送任务请求
        
        Args:
            target: 目标Agent ID
            task_type: 任务类型
            input_data: 输入数据
            parameters: 参数
            timeout: 超时时间
            
        Returns:
            任务结果
        """
        message = Message(
            type=MessageType.TASK_REQUEST,
            source=self.agent_id,
            target=target,
            payload={
                "task_type": task_type,
                "input_data": input_data or {},
                "parameters": parameters or {},
            },
        )
        
        response = await self.message_bus.request(message, timeout=timeout)
        
        if response:
            return response.payload
            
        return None
        
    async def broadcast(
        self,
        topic: str,
        data: Dict[str, Any],
    ) -> None:
        """
        广播消息
        
        Args:
            topic: 话题
            data: 数据
        """
        message = Message(
            type=MessageType.SYSTEM_EVENT,
            source=self.agent_id,
            topic=topic,
            payload=data,
        )
        
        await self.message_bus.send(message)
        
    async def query_data(
        self,
        query: Dict[str, Any],
        timeout: float = 30.0,
    ) -> Optional[Dict[str, Any]]:
        """
        查询数据
        
        Args:
            query: 查询条件
            timeout: 超时时间
            
        Returns:
            查询结果
        """
        message = Message(
            type=MessageType.DATA_QUERY,
            source=self.agent_id,
            target="data_gateway",
            payload={"query": query},
        )
        
        response = await self.message_bus.request(message, timeout=timeout)
        
        if response:
            return response.payload
            
        return None
