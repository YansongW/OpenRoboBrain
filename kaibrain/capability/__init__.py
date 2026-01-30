"""
能力层 (Capability Layer)

系统对外暴露的细粒度能力接口，由Agent协作实现。

分类：
- motion: 运动能力（行走、抓取等）
- perception: 感知能力（识别、检测等）
- cognition: 认知能力（对话、推理等）
- interaction: 交互能力（语音、手势等）
- autonomy: 自主能力（导航、自诊断等）
"""

from kaibrain.capability.base import Capability, CapabilityRegistry

__all__ = ["Capability", "CapabilityRegistry"]
