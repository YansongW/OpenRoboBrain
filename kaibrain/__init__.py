"""
KaiBrain - 具身智能机器人大脑系统

一个采用七层架构和双管道通信的机器人大脑系统，
支持多Agent协作、显隐数据分离、ROS2集成。

架构层级（从上到下）：
- 行为层 (Behavior Layer): 高层次行为（烹饪、清洁等）
- 能力层 (Capability Layer): 原子能力（导航、抓取等）
- Agent层 (Agent Layer): 三级Agent架构（Super→编排→原子）
- 系统层 (System Layer): 核心服务 + 大脑管道
- 桥接层 (Bridge Layer): 大脑-小脑桥接
- 中间件层 (Middleware Layer): 小脑管道（ROS2 DDS）+ 原子动作库
- 硬件层 (Hardware Layer): 控制软件→驱动→物理硬件
- 数据层 (Data Layer): 纵向贯穿，显性数据+隐性数据

快速开始：
    from kaibrain import KaiBrain
    
    brain = KaiBrain()
    await brain.initialize()
    await brain.start()
    
    result = await brain.process("帮我倒杯水")
    print(result.chat_response)  # 对话响应
    print(result.ros2_commands)  # ROS2控制命令
    
    await brain.stop()

CLI使用：
    # 命令行交互
    python -m kaibrain.cli
    
    # 或者直接运行
    kaibrain
"""

__version__ = "0.1.0"
__author__ = "KaiBrain Team"

from kaibrain.core import KaiBrain, ProcessResult

__all__ = [
    "KaiBrain",
    "ProcessResult",
    "__version__",
]
