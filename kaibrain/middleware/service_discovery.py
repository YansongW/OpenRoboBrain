"""
服务发现

提供动态节点注册与发现功能。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from kaibrain.system.services.logger import LoggerMixin


@dataclass
class ServiceEndpoint:
    """服务端点"""
    service_id: str
    service_name: str
    service_type: str
    host: str = "localhost"
    port: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    registered_at: datetime = field(default_factory=datetime.now)
    last_heartbeat: datetime = field(default_factory=datetime.now)
    is_healthy: bool = True


class ServiceDiscovery(LoggerMixin):
    """
    服务发现
    
    管理服务的注册、发现和健康检查。
    """
    
    def __init__(self, heartbeat_interval: float = 10.0, timeout: float = 30.0):
        """
        初始化服务发现
        
        Args:
            heartbeat_interval: 心跳间隔（秒）
            timeout: 超时时间（秒）
        """
        self.heartbeat_interval = heartbeat_interval
        self.timeout = timeout
        self._services: Dict[str, ServiceEndpoint] = {}
        self._running = False
        self._health_check_task: Optional[asyncio.Task] = None
        
    async def start(self) -> None:
        """启动服务发现"""
        self._running = True
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        self.logger.info("服务发现已启动")
        
    async def stop(self) -> None:
        """停止服务发现"""
        self._running = False
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        self.logger.info("服务发现已停止")
        
    def register(
        self,
        service_id: str,
        service_name: str,
        service_type: str,
        host: str = "localhost",
        port: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ServiceEndpoint:
        """
        注册服务
        
        Args:
            service_id: 服务ID
            service_name: 服务名称
            service_type: 服务类型
            host: 主机地址
            port: 端口
            metadata: 元数据
            
        Returns:
            ServiceEndpoint
        """
        endpoint = ServiceEndpoint(
            service_id=service_id,
            service_name=service_name,
            service_type=service_type,
            host=host,
            port=port,
            metadata=metadata or {},
        )
        self._services[service_id] = endpoint
        
        self.logger.info(f"注册服务: {service_name} ({service_id})")
        return endpoint
        
    def unregister(self, service_id: str) -> None:
        """注销服务"""
        if service_id in self._services:
            service = self._services.pop(service_id)
            self.logger.info(f"注销服务: {service.service_name} ({service_id})")
            
    def heartbeat(self, service_id: str) -> bool:
        """
        发送心跳
        
        Args:
            service_id: 服务ID
            
        Returns:
            是否成功
        """
        if service_id in self._services:
            self._services[service_id].last_heartbeat = datetime.now()
            self._services[service_id].is_healthy = True
            return True
        return False
        
    def discover(
        self,
        service_type: Optional[str] = None,
        service_name: Optional[str] = None,
        healthy_only: bool = True,
    ) -> List[ServiceEndpoint]:
        """
        发现服务
        
        Args:
            service_type: 服务类型过滤
            service_name: 服务名称过滤
            healthy_only: 只返回健康的服务
            
        Returns:
            服务端点列表
        """
        services = list(self._services.values())
        
        if service_type:
            services = [s for s in services if s.service_type == service_type]
            
        if service_name:
            services = [s for s in services if s.service_name == service_name]
            
        if healthy_only:
            services = [s for s in services if s.is_healthy]
            
        return services
        
    def get(self, service_id: str) -> Optional[ServiceEndpoint]:
        """获取服务"""
        return self._services.get(service_id)
        
    async def _health_check_loop(self) -> None:
        """健康检查循环"""
        while self._running:
            now = datetime.now()
            timeout_threshold = now - timedelta(seconds=self.timeout)
            
            for service_id, service in self._services.items():
                if service.last_heartbeat < timeout_threshold:
                    if service.is_healthy:
                        service.is_healthy = False
                        self.logger.warning(f"服务不健康: {service.service_name} ({service_id})")
                        
            await asyncio.sleep(self.heartbeat_interval)
