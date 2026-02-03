"""
KaiBrain 风险监控器

提供系统级风险检测、监控和报告功能。
- 启动时检查：检测已知风险配置
- 运行时监控：监控资源使用、队列深度等
- 风险报告：生成风险评估报告

使用方式:
    from kaibrain.system.services.risk_monitor import RiskMonitor

    monitor = RiskMonitor()
    await monitor.initialize()
    
    # 启动检查
    report = await monitor.run_startup_checks()
    
    # 运行时监控
    await monitor.start_monitoring()
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from pathlib import Path

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """风险等级"""
    CRITICAL = "critical"  # 致命
    HIGH = "high"          # 高
    MEDIUM = "medium"      # 中
    LOW = "low"            # 低
    INFO = "info"          # 信息


class RiskCategory(Enum):
    """风险类别"""
    SECURITY = "SEC"       # 安全
    CONTROL = "CTL"        # 控制
    RESOURCE = "RES"       # 资源
    RELIABILITY = "REL"    # 可靠性
    HARDWARE = "HW"        # 硬件
    INTEGRATION = "INT"    # 集成


class RiskStatus(Enum):
    """风险状态"""
    DETECTED = "detected"      # 检测到
    MITIGATED = "mitigated"    # 已缓解
    RESOLVED = "resolved"      # 已解决
    MONITORING = "monitoring"  # 监控中


@dataclass
class RiskItem:
    """风险项"""
    id: str
    level: RiskLevel
    category: RiskCategory
    title: str
    description: str
    location: str = ""
    impact: str = ""
    mitigation: str = ""
    status: RiskStatus = RiskStatus.DETECTED
    detected_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MonitorMetric:
    """监控指标"""
    name: str
    value: float
    threshold_warning: float
    threshold_critical: float
    unit: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    
    @property
    def level(self) -> RiskLevel:
        """根据阈值判断风险等级"""
        if self.value >= self.threshold_critical:
            return RiskLevel.CRITICAL
        elif self.value >= self.threshold_warning:
            return RiskLevel.HIGH
        return RiskLevel.INFO


@dataclass
class RiskReport:
    """风险报告"""
    generated_at: datetime = field(default_factory=datetime.now)
    risks: List[RiskItem] = field(default_factory=list)
    metrics: List[MonitorMetric] = field(default_factory=list)
    summary: Dict[str, int] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "generated_at": self.generated_at.isoformat(),
            "risks": [
                {
                    "id": r.id,
                    "level": r.level.value,
                    "category": r.category.value,
                    "title": r.title,
                    "description": r.description,
                    "location": r.location,
                    "status": r.status.value,
                }
                for r in self.risks
            ],
            "metrics": [
                {
                    "name": m.name,
                    "value": m.value,
                    "threshold_warning": m.threshold_warning,
                    "threshold_critical": m.threshold_critical,
                    "unit": m.unit,
                    "level": m.level.value,
                }
                for m in self.metrics
            ],
            "summary": self.summary,
            "recommendations": self.recommendations,
        }


class RiskChecker:
    """风险检查器基类"""
    
    def __init__(self, checker_id: str, category: RiskCategory):
        self.checker_id = checker_id
        self.category = category
    
    async def check(self) -> List[RiskItem]:
        """执行检查，返回检测到的风险"""
        raise NotImplementedError


class SecurityChecker(RiskChecker):
    """安全风险检查器"""
    
    def __init__(self):
        super().__init__("security_checker", RiskCategory.SECURITY)
    
    async def check(self) -> List[RiskItem]:
        risks = []
        
        # 检查 Shell 工具安全模式
        risks.extend(await self._check_shell_security())
        
        # 检查工具策略配置
        risks.extend(await self._check_tool_policy())
        
        # 检查 HTTP 工具 SSRF 防护
        risks.extend(await self._check_http_ssrf())
        
        # 检查文件工具路径限制
        risks.extend(await self._check_file_path_restriction())
        
        return risks
    
    async def _check_shell_security(self) -> List[RiskItem]:
        """检查 Shell 工具安全配置"""
        risks = []
        try:
            from kaibrain.system.tools.builtin.shell import ShellTool, SecurityMode
            
            # 检查是否使用 FULL 模式
            # 这里只是示例，实际需要从配置读取
            shell_tool = ShellTool()
            if hasattr(shell_tool, '_security_mode'):
                if shell_tool._security_mode == SecurityMode.FULL:
                    risks.append(RiskItem(
                        id="RISK-SEC-001-CONFIG",
                        level=RiskLevel.CRITICAL,
                        category=RiskCategory.SECURITY,
                        title="Shell工具使用FULL安全模式",
                        description="Shell工具配置为FULL模式，允许执行任意命令",
                        location="kaibrain/system/tools/builtin/shell.py",
                        impact="可能执行危险命令，导致系统损坏",
                        mitigation="将安全模式改为 ALLOWLIST 或 DENY",
                    ))
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"Shell安全检查失败: {e}")
        
        return risks
    
    async def _check_tool_policy(self) -> List[RiskItem]:
        """检查工具策略是否正确配置"""
        risks = []
        
        # 检查是否存在工具策略配置
        try:
            from kaibrain.agent.security.tool_policy import ToolPolicy
            # 如果 ToolPolicy 存在但未配置，添加警告
        except ImportError:
            risks.append(RiskItem(
                id="RISK-SEC-002-MISSING",
                level=RiskLevel.HIGH,
                category=RiskCategory.SECURITY,
                title="工具策略模块缺失",
                description="未找到工具策略模块",
                location="kaibrain/agent/security/tool_policy.py",
            ))
        
        return risks
    
    async def _check_http_ssrf(self) -> List[RiskItem]:
        """检查 HTTP 工具 SSRF 防护"""
        risks = []
        
        try:
            from kaibrain.system.tools.builtin.http import HttpTool
            
            # 检查是否配置了 URL 黑名单
            http_tool = HttpTool()
            if not hasattr(http_tool, '_blocked_hosts') or not http_tool._blocked_hosts:
                risks.append(RiskItem(
                    id="RISK-SEC-003-SSRF",
                    level=RiskLevel.HIGH,
                    category=RiskCategory.SECURITY,
                    title="HTTP工具未配置SSRF防护",
                    description="HTTP工具未阻止内网地址访问",
                    location="kaibrain/system/tools/builtin/http.py",
                    impact="可能访问内部服务，导致信息泄露",
                    mitigation="添加内网IP黑名单",
                ))
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"HTTP SSRF检查跳过: {e}")
        
        return risks
    
    async def _check_file_path_restriction(self) -> List[RiskItem]:
        """检查文件工具路径限制"""
        risks = []
        
        try:
            from kaibrain.system.tools.builtin.file import FileTool
            
            # 检查是否配置了允许的根目录
            file_tool = FileTool()
            if not hasattr(file_tool, '_allowed_roots') or not file_tool._allowed_roots:
                risks.append(RiskItem(
                    id="RISK-SEC-004-PATH",
                    level=RiskLevel.HIGH,
                    category=RiskCategory.SECURITY,
                    title="文件工具未配置路径限制",
                    description="文件工具未限制可访问的目录",
                    location="kaibrain/system/tools/builtin/file.py",
                    impact="可能访问任意文件，导致信息泄露或系统损坏",
                    mitigation="配置允许访问的根目录列表",
                ))
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"文件路径检查跳过: {e}")
        
        return risks


class ControlChecker(RiskChecker):
    """控制风险检查器"""
    
    def __init__(self):
        super().__init__("control_checker", RiskCategory.CONTROL)
    
    async def check(self) -> List[RiskItem]:
        risks = []
        
        # 检查紧急停止机制
        risks.extend(await self._check_emergency_stop())
        
        # 检查 Agent 终止机制
        risks.extend(await self._check_agent_termination())
        
        return risks
    
    async def _check_emergency_stop(self) -> List[RiskItem]:
        """检查紧急停止机制"""
        risks = []
        
        try:
            from kaibrain.system.brain_pipeline.brain_cerebellum_bridge import BrainCerebellumBridge
            
            # 检查是否实现了紧急停止
            if not hasattr(BrainCerebellumBridge, 'emergency_stop'):
                risks.append(RiskItem(
                    id="RISK-CTL-002-ESTOP",
                    level=RiskLevel.CRITICAL,
                    category=RiskCategory.CONTROL,
                    title="未实现紧急停止机制",
                    description="Brain-Cerebellum Bridge 未实现紧急停止方法",
                    location="kaibrain/system/brain_pipeline/brain_cerebellum_bridge.py",
                    impact="无法在紧急情况下停止机器人",
                    mitigation="实现 emergency_stop() 方法",
                ))
        except ImportError:
            pass
        
        return risks
    
    async def _check_agent_termination(self) -> List[RiskItem]:
        """检查 Agent 终止机制"""
        risks = []
        
        try:
            from kaibrain.agent.subagent.spawn import SubAgentSpawner
            
            # 检查是否有强制终止能力
            # 这是一个结构性检查
            risks.append(RiskItem(
                id="RISK-CTL-001-TERM",
                level=RiskLevel.CRITICAL,
                category=RiskCategory.CONTROL,
                title="Subagent无法强制终止",
                description="stop_spawn() 仅更新状态，不会真正取消任务",
                location="kaibrain/agent/subagent/spawn.py",
                impact="紧急停止命令可能无效",
                mitigation="实现 asyncio.Task.cancel() 调用",
                status=RiskStatus.MONITORING,
            ))
        except ImportError:
            pass
        
        return risks


class ResourceChecker(RiskChecker):
    """资源风险检查器"""
    
    def __init__(self):
        super().__init__("resource_checker", RiskCategory.RESOURCE)
    
    async def check(self) -> List[RiskItem]:
        risks = []
        
        # 检查队列配置
        risks.extend(await self._check_queue_limits())
        
        # 检查超时配置
        risks.extend(await self._check_timeout_config())
        
        return risks
    
    async def _check_queue_limits(self) -> List[RiskItem]:
        """检查队列大小限制"""
        risks = []
        
        try:
            from kaibrain.system.brain_pipeline.message_bus import MessageBus
            
            # MessageBus 使用无界队列
            risks.append(RiskItem(
                id="RISK-RES-001-QUEUE",
                level=RiskLevel.HIGH,
                category=RiskCategory.RESOURCE,
                title="消息总线使用无界队列",
                description="MessageBus._queues 无大小限制",
                location="kaibrain/system/brain_pipeline/message_bus.py",
                impact="高负载下内存耗尽",
                mitigation="为队列设置 maxsize",
                status=RiskStatus.MONITORING,
            ))
        except ImportError:
            pass
        
        return risks
    
    async def _check_timeout_config(self) -> List[RiskItem]:
        """检查超时配置"""
        risks = []
        
        try:
            from kaibrain.agent.subagent.spawn import SubAgentSpawner
            
            # 默认无超时
            risks.append(RiskItem(
                id="RISK-REL-004-TIMEOUT",
                level=RiskLevel.MEDIUM,
                category=RiskCategory.RESOURCE,
                title="Subagent默认无超时限制",
                description="run_timeout_seconds 默认为 0（无限制）",
                location="kaibrain/agent/subagent/spawn.py",
                impact="Agent可能无限运行",
                mitigation="设置合理的默认超时（建议300秒）",
                status=RiskStatus.MONITORING,
            ))
        except ImportError:
            pass
        
        return risks


class RuntimeMonitor:
    """运行时监控器"""
    
    def __init__(self):
        self._metrics: Dict[str, MonitorMetric] = {}
        self._callbacks: List[Callable[[MonitorMetric], None]] = []
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
        # 默认阈值配置
        self._thresholds = {
            "queue_depth": {"warning": 100, "critical": 500},
            "pending_requests": {"warning": 50, "critical": 200},
            "active_agents": {"warning": 20, "critical": 50},
            "memory_mb": {"warning": 1024, "critical": 2048},
            "cpu_percent": {"warning": 70, "critical": 90},
        }
    
    def register_callback(self, callback: Callable[[MonitorMetric], None]):
        """注册指标回调"""
        self._callbacks.append(callback)
    
    async def start(self, interval: float = 5.0):
        """启动监控"""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop(interval))
        logger.info("运行时监控已启动")
    
    async def stop(self):
        """停止监控"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("运行时监控已停止")
    
    async def _monitor_loop(self, interval: float):
        """监控循环"""
        while self._running:
            try:
                await self._collect_metrics()
                await self._check_thresholds()
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"监控循环异常: {e}")
                await asyncio.sleep(interval)
    
    async def _collect_metrics(self):
        """收集指标"""
        try:
            import psutil
            
            # 内存使用
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            self._update_metric(
                "memory_mb",
                memory_mb,
                self._thresholds["memory_mb"]["warning"],
                self._thresholds["memory_mb"]["critical"],
                "MB"
            )
            
            # CPU 使用
            cpu_percent = process.cpu_percent()
            self._update_metric(
                "cpu_percent",
                cpu_percent,
                self._thresholds["cpu_percent"]["warning"],
                self._thresholds["cpu_percent"]["critical"],
                "%"
            )
        except ImportError:
            pass  # psutil 未安装
        except Exception as e:
            logger.debug(f"指标收集失败: {e}")
        
        # 收集应用级指标
        await self._collect_app_metrics()
    
    async def _collect_app_metrics(self):
        """收集应用级指标"""
        try:
            # 尝试获取 MessageBus 队列深度
            from kaibrain.system.brain_pipeline.message_bus import MessageBus
            
            # 这里需要访问实际的 MessageBus 实例
            # 暂时跳过，实际使用时需要注入实例
        except ImportError:
            pass
    
    def _update_metric(
        self,
        name: str,
        value: float,
        threshold_warning: float,
        threshold_critical: float,
        unit: str = ""
    ):
        """更新指标"""
        metric = MonitorMetric(
            name=name,
            value=value,
            threshold_warning=threshold_warning,
            threshold_critical=threshold_critical,
            unit=unit,
        )
        self._metrics[name] = metric
        
        # 触发回调
        for callback in self._callbacks:
            try:
                callback(metric)
            except Exception as e:
                logger.error(f"指标回调异常: {e}")
    
    async def _check_thresholds(self):
        """检查阈值并告警"""
        for name, metric in self._metrics.items():
            if metric.level == RiskLevel.CRITICAL:
                logger.critical(
                    f"指标 {name} 达到严重阈值: "
                    f"{metric.value}{metric.unit} >= {metric.threshold_critical}{metric.unit}"
                )
            elif metric.level == RiskLevel.HIGH:
                logger.warning(
                    f"指标 {name} 达到警告阈值: "
                    f"{metric.value}{metric.unit} >= {metric.threshold_warning}{metric.unit}"
                )
    
    def get_metrics(self) -> List[MonitorMetric]:
        """获取所有指标"""
        return list(self._metrics.values())


class RiskMonitor:
    """风险监控器主类"""
    
    def __init__(self):
        self._checkers: List[RiskChecker] = []
        self._runtime_monitor: Optional[RuntimeMonitor] = None
        self._detected_risks: Dict[str, RiskItem] = {}
        self._initialized = False
    
    async def initialize(self):
        """初始化风险监控器"""
        if self._initialized:
            return
        
        # 注册默认检查器
        self._checkers = [
            SecurityChecker(),
            ControlChecker(),
            ResourceChecker(),
        ]
        
        # 初始化运行时监控器
        self._runtime_monitor = RuntimeMonitor()
        
        self._initialized = True
        logger.info("风险监控器初始化完成")
    
    def register_checker(self, checker: RiskChecker):
        """注册自定义检查器"""
        self._checkers.append(checker)
    
    async def run_startup_checks(self) -> RiskReport:
        """运行启动检查"""
        if not self._initialized:
            await self.initialize()
        
        all_risks: List[RiskItem] = []
        
        for checker in self._checkers:
            try:
                risks = await checker.check()
                all_risks.extend(risks)
                logger.info(f"检查器 {checker.checker_id} 发现 {len(risks)} 个风险")
            except Exception as e:
                logger.error(f"检查器 {checker.checker_id} 执行失败: {e}")
        
        # 更新已检测风险
        for risk in all_risks:
            self._detected_risks[risk.id] = risk
        
        # 生成报告
        report = self._generate_report(all_risks)
        
        # 输出摘要
        self._log_summary(report)
        
        return report
    
    async def start_monitoring(self, interval: float = 5.0):
        """启动运行时监控"""
        if self._runtime_monitor:
            await self._runtime_monitor.start(interval)
    
    async def stop_monitoring(self):
        """停止运行时监控"""
        if self._runtime_monitor:
            await self._runtime_monitor.stop()
    
    def get_current_risks(self) -> List[RiskItem]:
        """获取当前所有风险"""
        return list(self._detected_risks.values())
    
    def get_risks_by_level(self, level: RiskLevel) -> List[RiskItem]:
        """按等级获取风险"""
        return [r for r in self._detected_risks.values() if r.level == level]
    
    def update_risk_status(self, risk_id: str, status: RiskStatus):
        """更新风险状态"""
        if risk_id in self._detected_risks:
            self._detected_risks[risk_id].status = status
            logger.info(f"风险 {risk_id} 状态更新为 {status.value}")
    
    def _generate_report(self, risks: List[RiskItem]) -> RiskReport:
        """生成风险报告"""
        # 统计
        summary = {
            "total": len(risks),
            "critical": len([r for r in risks if r.level == RiskLevel.CRITICAL]),
            "high": len([r for r in risks if r.level == RiskLevel.HIGH]),
            "medium": len([r for r in risks if r.level == RiskLevel.MEDIUM]),
            "low": len([r for r in risks if r.level == RiskLevel.LOW]),
        }
        
        # 建议
        recommendations = []
        if summary["critical"] > 0:
            recommendations.append("⚠️ 存在致命风险，强烈建议在部署前修复")
        if summary["high"] > 0:
            recommendations.append("⚠️ 存在高风险问题，建议尽快处理")
        
        # 收集指标
        metrics = []
        if self._runtime_monitor:
            metrics = self._runtime_monitor.get_metrics()
        
        return RiskReport(
            risks=risks,
            metrics=metrics,
            summary=summary,
            recommendations=recommendations,
        )
    
    def _log_summary(self, report: RiskReport):
        """输出风险摘要"""
        summary = report.summary
        
        logger.info("=" * 50)
        logger.info("风险检查摘要")
        logger.info("=" * 50)
        logger.info(f"总计: {summary['total']} 个风险")
        
        if summary['critical'] > 0:
            logger.critical(f"  🔴 致命: {summary['critical']}")
        if summary['high'] > 0:
            logger.warning(f"  🟠 高: {summary['high']}")
        if summary['medium'] > 0:
            logger.info(f"  🟡 中: {summary['medium']}")
        if summary['low'] > 0:
            logger.info(f"  🟢 低: {summary['low']}")
        
        for rec in report.recommendations:
            logger.warning(rec)
        
        logger.info("=" * 50)


# 全局实例
_risk_monitor: Optional[RiskMonitor] = None


def get_risk_monitor() -> RiskMonitor:
    """获取风险监控器单例"""
    global _risk_monitor
    if _risk_monitor is None:
        _risk_monitor = RiskMonitor()
    return _risk_monitor


async def run_risk_check() -> RiskReport:
    """便捷函数：运行风险检查"""
    monitor = get_risk_monitor()
    await monitor.initialize()
    return await monitor.run_startup_checks()
