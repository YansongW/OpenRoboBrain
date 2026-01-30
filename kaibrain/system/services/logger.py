"""
日志服务

提供统一的日志收集、分级和检索功能。
"""

import logging
import sys
from typing import Optional

# 日志格式
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 全局日志级别
_log_level = logging.INFO
_initialized = False


def setup_logging(level: int = logging.INFO) -> None:
    """
    初始化日志系统
    
    Args:
        level: 日志级别
    """
    global _log_level, _initialized
    
    if _initialized:
        return
        
    _log_level = level
    
    # 配置根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    
    root_logger.addHandler(console_handler)
    _initialized = True


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    获取日志器
    
    Args:
        name: 日志器名称，通常使用 __name__
        
    Returns:
        Logger 实例
    """
    if not _initialized:
        setup_logging()
        
    logger = logging.getLogger(name or "kaibrain")
    return logger


class LoggerMixin:
    """日志器混入类，为类提供 self.logger 属性"""
    
    @property
    def logger(self) -> logging.Logger:
        if not hasattr(self, "_logger"):
            self._logger = get_logger(self.__class__.__name__)
        return self._logger
