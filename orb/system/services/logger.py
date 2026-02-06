"""
日志服务

提供统一的日志收集、分级和检索功能。
支持trace_id追踪、层级标识、结构化日志。
"""

import contextvars
import logging
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

# 日志格式 - 增强版，包含trace_id、层级、组件
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(trace_id)s | %(layer)s | %(component)s | %(message)s"
LOG_FORMAT_SIMPLE = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 全局日志级别
_log_level = logging.INFO
_initialized = False
_use_enhanced_format = True

# 上下文变量 - 用于存储trace_id
_trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="-")
_layer_var: contextvars.ContextVar[str] = contextvars.ContextVar("layer", default="-")
_component_var: contextvars.ContextVar[str] = contextvars.ContextVar("component", default="-")


# 层级常量
class Layer:
    """系统层级常量"""
    BEHAVIOR = "Behavior"
    CAPABILITY = "Capability"
    AGENT = "Agent"
    SYSTEM = "System"
    BRIDGE = "Bridge"
    MIDDLEWARE = "Middleware"
    HARDWARE = "Hardware"
    DATA = "Data"
    CLI = "CLI"


@dataclass
class LogContext:
    """日志上下文"""
    trace_id: str = "-"
    layer: str = "-"
    component: str = "-"
    
    def to_dict(self) -> Dict[str, str]:
        return {
            "trace_id": self.trace_id,
            "layer": self.layer,
            "component": self.component,
        }


class TraceIdFilter(logging.Filter):
    """添加trace_id到日志记录的过滤器"""
    
    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = _trace_id_var.get()
        record.layer = _layer_var.get()
        record.component = _component_var.get()
        return True


def set_trace_context(
    trace_id: Optional[str] = None,
    layer: Optional[str] = None,
    component: Optional[str] = None,
) -> None:
    """
    设置当前上下文的追踪信息
    
    Args:
        trace_id: 追踪ID
        layer: 层级名称
        component: 组件名称
    """
    if trace_id is not None:
        _trace_id_var.set(trace_id)
    if layer is not None:
        _layer_var.set(layer)
    if component is not None:
        _component_var.set(component)


def get_trace_context() -> LogContext:
    """获取当前上下文的追踪信息"""
    return LogContext(
        trace_id=_trace_id_var.get(),
        layer=_layer_var.get(),
        component=_component_var.get(),
    )


def clear_trace_context() -> None:
    """清除追踪上下文"""
    _trace_id_var.set("-")
    _layer_var.set("-")
    _component_var.set("-")


class TraceContextManager:
    """追踪上下文管理器"""
    
    def __init__(
        self,
        trace_id: Optional[str] = None,
        layer: Optional[str] = None,
        component: Optional[str] = None,
    ):
        self.trace_id = trace_id
        self.layer = layer
        self.component = component
        self._old_trace_id: Optional[str] = None
        self._old_layer: Optional[str] = None
        self._old_component: Optional[str] = None
    
    def __enter__(self) -> "TraceContextManager":
        # 保存旧值
        self._old_trace_id = _trace_id_var.get()
        self._old_layer = _layer_var.get()
        self._old_component = _component_var.get()
        
        # 设置新值
        if self.trace_id is not None:
            _trace_id_var.set(self.trace_id)
        if self.layer is not None:
            _layer_var.set(self.layer)
        if self.component is not None:
            _component_var.set(self.component)
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        # 恢复旧值
        if self._old_trace_id is not None:
            _trace_id_var.set(self._old_trace_id)
        if self._old_layer is not None:
            _layer_var.set(self._old_layer)
        if self._old_component is not None:
            _component_var.set(self._old_component)


def trace_context(
    trace_id: Optional[str] = None,
    layer: Optional[str] = None,
    component: Optional[str] = None,
) -> TraceContextManager:
    """
    创建追踪上下文管理器
    
    用法:
        with trace_context(trace_id="abc123", layer=Layer.AGENT, component="Orchestrator"):
            logger.info("处理中...")
    """
    return TraceContextManager(trace_id, layer, component)


def setup_logging(
    level: int = logging.INFO,
    use_enhanced_format: bool = True,
) -> None:
    """
    初始化日志系统
    
    Args:
        level: 日志级别
        use_enhanced_format: 是否使用增强格式（包含trace_id、层级等）
    """
    global _log_level, _initialized, _use_enhanced_format
    
    if _initialized:
        return
        
    _log_level = level
    _use_enhanced_format = use_enhanced_format
    
    # 配置根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # 清除现有处理器
    root_logger.handlers.clear()
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    
    # 选择日志格式
    log_format = LOG_FORMAT if use_enhanced_format else LOG_FORMAT_SIMPLE
    console_handler.setFormatter(logging.Formatter(log_format, DATE_FORMAT))
    
    # 添加trace_id过滤器
    if use_enhanced_format:
        console_handler.addFilter(TraceIdFilter())
    
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
        
    logger = logging.getLogger(name or "OpenRoboBrain")
    return logger


def log_with_context(
    logger: logging.Logger,
    level: int,
    message: str,
    trace_id: Optional[str] = None,
    layer: Optional[str] = None,
    component: Optional[str] = None,
    **kwargs: Any,
) -> None:
    """
    带上下文的日志记录
    
    Args:
        logger: 日志器
        level: 日志级别
        message: 日志消息
        trace_id: 追踪ID
        layer: 层级
        component: 组件
        **kwargs: 额外参数
    """
    with trace_context(trace_id, layer, component):
        logger.log(level, message, **kwargs)


class LoggerMixin:
    """
    日志器混入类，为类提供 self.logger 属性
    
    增强功能：
    - 自动设置组件名称
    - 提供便捷的日志方法
    """
    
    # 子类可以覆盖这些属性
    _log_layer: str = "-"
    
    @property
    def logger(self) -> logging.Logger:
        if not hasattr(self, "_logger"):
            self._logger = get_logger(self.__class__.__name__)
        return self._logger
    
    def log_info(self, message: str, trace_id: Optional[str] = None) -> None:
        """带上下文的INFO日志"""
        with trace_context(trace_id=trace_id, layer=self._log_layer, component=self.__class__.__name__):
            self.logger.info(message)
    
    def log_debug(self, message: str, trace_id: Optional[str] = None) -> None:
        """带上下文的DEBUG日志"""
        with trace_context(trace_id=trace_id, layer=self._log_layer, component=self.__class__.__name__):
            self.logger.debug(message)
    
    def log_warning(self, message: str, trace_id: Optional[str] = None) -> None:
        """带上下文的WARNING日志"""
        with trace_context(trace_id=trace_id, layer=self._log_layer, component=self.__class__.__name__):
            self.logger.warning(message)
    
    def log_error(self, message: str, trace_id: Optional[str] = None) -> None:
        """带上下文的ERROR日志"""
        with trace_context(trace_id=trace_id, layer=self._log_layer, component=self.__class__.__name__):
            self.logger.error(message)


# 层级专用的LoggerMixin
class BehaviorLoggerMixin(LoggerMixin):
    """行为层日志混入"""
    _log_layer = Layer.BEHAVIOR


class CapabilityLoggerMixin(LoggerMixin):
    """能力层日志混入"""
    _log_layer = Layer.CAPABILITY


class AgentLoggerMixin(LoggerMixin):
    """Agent层日志混入"""
    _log_layer = Layer.AGENT


class SystemLoggerMixin(LoggerMixin):
    """系统层日志混入"""
    _log_layer = Layer.SYSTEM


class BridgeLoggerMixin(LoggerMixin):
    """桥接层日志混入"""
    _log_layer = Layer.BRIDGE
