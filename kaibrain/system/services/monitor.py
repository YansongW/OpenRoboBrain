"""
监控告警服务

提供系统性能监控、异常检测和告警通知。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from kaibrain.system.services.logger import LoggerMixin


class AlertLevel(Enum):
    """告警级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class Alert:
    """告警"""
    alert_id: str
    level: AlertLevel
    source: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    acknowledged: bool = False
    acknowledged_at: Optional[datetime] = None


@dataclass
class Metric:
    """指标"""
    name: str
    value: float
    unit: str = ""
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


class Monitor(LoggerMixin):
    """
    监控服务
    
    收集系统指标、检测异常、发送告警。
    """
    
    def __init__(self):
        self._metrics: Dict[str, List[Metric]] = {}
        self._alerts: List[Alert] = []
        self._alert_handlers: List[Callable[[Alert], None]] = []
        self._running = False
        self._check_task: Optional[asyncio.Task] = None
        
        # 指标阈值
        self._thresholds: Dict[str, Dict[str, float]] = {
            "cpu_usage": {"warning": 80.0, "critical": 95.0},
            "memory_usage": {"warning": 85.0, "critical": 95.0},
            "agent_latency_ms": {"warning": 1000.0, "critical": 5000.0},
        }
        
    def record_metric(self, metric: Metric) -> None:
        """记录指标"""
        if metric.name not in self._metrics:
            self._metrics[metric.name] = []
            
        self._metrics[metric.name].append(metric)
        
        # 保留最近1000个数据点
        if len(self._metrics[metric.name]) > 1000:
            self._metrics[metric.name] = self._metrics[metric.name][-1000:]
            
        # 检查阈值
        self._check_threshold(metric)
        
    def _check_threshold(self, metric: Metric) -> None:
        """检查指标是否超过阈值"""
        thresholds = self._thresholds.get(metric.name)
        if not thresholds:
            return
            
        if metric.value >= thresholds.get("critical", float("inf")):
            self.create_alert(
                level=AlertLevel.CRITICAL,
                source=metric.name,
                message=f"{metric.name} 达到危险水平: {metric.value}{metric.unit}",
                details={"value": metric.value, "threshold": thresholds["critical"]},
            )
        elif metric.value >= thresholds.get("warning", float("inf")):
            self.create_alert(
                level=AlertLevel.WARNING,
                source=metric.name,
                message=f"{metric.name} 达到警告水平: {metric.value}{metric.unit}",
                details={"value": metric.value, "threshold": thresholds["warning"]},
            )
            
    def create_alert(
        self,
        level: AlertLevel,
        source: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> Alert:
        """创建告警"""
        alert = Alert(
            alert_id=f"alert_{len(self._alerts)}_{datetime.now().timestamp()}",
            level=level,
            source=source,
            message=message,
            details=details or {},
        )
        
        self._alerts.append(alert)
        
        # 日志记录
        log_method = {
            AlertLevel.INFO: self.logger.info,
            AlertLevel.WARNING: self.logger.warning,
            AlertLevel.ERROR: self.logger.error,
            AlertLevel.CRITICAL: self.logger.critical,
        }.get(level, self.logger.info)
        
        log_method(f"[{source}] {message}")
        
        # 通知处理器
        for handler in self._alert_handlers:
            try:
                handler(alert)
            except Exception as e:
                self.logger.error(f"告警处理器错误: {e}")
                
        return alert
        
    def add_alert_handler(self, handler: Callable[[Alert], None]) -> None:
        """添加告警处理器"""
        self._alert_handlers.append(handler)
        
    def get_metrics(self, name: str, limit: int = 100) -> List[Metric]:
        """获取指标历史"""
        metrics = self._metrics.get(name, [])
        return metrics[-limit:]
        
    def get_alerts(
        self,
        level: Optional[AlertLevel] = None,
        acknowledged: Optional[bool] = None,
        limit: int = 100,
    ) -> List[Alert]:
        """获取告警列表"""
        alerts = self._alerts
        
        if level is not None:
            alerts = [a for a in alerts if a.level == level]
            
        if acknowledged is not None:
            alerts = [a for a in alerts if a.acknowledged == acknowledged]
            
        return alerts[-limit:]
        
    def acknowledge_alert(self, alert_id: str) -> bool:
        """确认告警"""
        for alert in self._alerts:
            if alert.alert_id == alert_id:
                alert.acknowledged = True
                alert.acknowledged_at = datetime.now()
                return True
        return False
