"""
KaiBrain 核心入口

提供系统的统一入口和生命周期管理。
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Optional

from kaibrain.system.services.config_center import ConfigCenter
from kaibrain.system.services.logger import get_logger

if TYPE_CHECKING:
    from kaibrain.agent.super.super_agent import SuperAgent
    from kaibrain.system.brain_pipeline.message_bus import MessageBus

logger = get_logger(__name__)


class KaiBrain:
    """
    KaiBrain 系统主类
    
    负责整个系统的初始化、启动和关闭。
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化 KaiBrain 系统
        
        Args:
            config_path: 配置文件路径，默认使用 configs/system.yaml
        """
        self.config_path = config_path or "configs/system.yaml"
        self.config: Optional[ConfigCenter] = None
        self._message_bus: Optional[MessageBus] = None
        self._super_agent: Optional[SuperAgent] = None
        self._running = False
        
    async def initialize(self) -> None:
        """初始化系统所有组件"""
        logger.info("正在初始化 KaiBrain 系统...")
        
        # 1. 加载配置
        self.config = ConfigCenter(self.config_path)
        await self.config.load()
        logger.info("配置加载完成")
        
        # 2. 初始化系统层 - 大脑管道
        from kaibrain.system.brain_pipeline.message_bus import MessageBus
        self._message_bus = MessageBus(self.config)
        await self._message_bus.initialize()
        logger.info("大脑管道初始化完成")
        
        # 3. 初始化Agent层 - Super Agent
        from kaibrain.agent.super.super_agent import SuperAgent
        self._super_agent = SuperAgent(self._message_bus, self.config)
        await self._super_agent.initialize()
        logger.info("Super Agent 初始化完成")
        
        logger.info("KaiBrain 系统初始化完成")
        
    async def start(self) -> None:
        """启动系统"""
        if self._running:
            logger.warning("系统已在运行中")
            return
            
        logger.info("正在启动 KaiBrain 系统...")
        self._running = True
        
        # 启动 Super Agent
        if self._super_agent:
            await self._super_agent.start()
            
        logger.info("KaiBrain 系统启动完成")
        
    async def stop(self) -> None:
        """停止系统"""
        if not self._running:
            return
            
        logger.info("正在停止 KaiBrain 系统...")
        self._running = False
        
        # 停止 Super Agent
        if self._super_agent:
            await self._super_agent.stop()
            
        # 关闭大脑管道
        if self._message_bus:
            await self._message_bus.shutdown()
            
        logger.info("KaiBrain 系统已停止")
        
    async def run(self) -> None:
        """运行系统（阻塞直到收到停止信号）"""
        await self.initialize()
        await self.start()
        
        try:
            # 保持运行直到收到停止信号
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()
            
    @property
    def message_bus(self) -> Optional[MessageBus]:
        """获取大脑管道消息总线"""
        return self._message_bus
        
    @property
    def super_agent(self) -> Optional[SuperAgent]:
        """获取 Super Agent"""
        return self._super_agent
