"""
系统层 (System Layer)

系统层包含两大部分：
1. 核心服务：进程管理、资源调度、配置中心、日志、监控、安全
2. 大脑管道：Agent通信总线，负责所有Agent间的通信
"""

from kaibrain.system.services.config_center import ConfigCenter
from kaibrain.system.services.logger import get_logger

__all__ = ["ConfigCenter", "get_logger"]
