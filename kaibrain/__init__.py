"""
KaiBrain - 具身智能机器人大脑系统

一个采用六层架构和双管道通信的机器人大脑系统，
支持多Agent协作、显隐数据分离、ROS2集成。

架构层级（从上到下）：
- 技能层 (Skill Layer): 对外暴露的语义化技能接口（烹饪、学习、跑步等）
- Agent层 (Agent Layer): 三级Agent架构（Super→编排→技能执行）
- 系统层 (System Layer): 核心服务 + 大脑管道
- 中间件层 (Middleware Layer): 小脑管道（ROS2 DDS）+ 原子动作库
- 硬件层 (Hardware Layer): 控制软件→驱动→物理硬件
- 数据层 (Data Layer): 纵向贯穿，显性数据+隐性数据
"""

__version__ = "0.1.0"
__author__ = "KaiBrain Team"

from kaibrain.core import KaiBrain

__all__ = ["KaiBrain", "__version__"]
