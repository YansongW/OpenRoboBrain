"""
视觉类Agent

包含：
- 图片理解
- 视频理解
- OCR
- 目标检测
- 人脸识别
- 姿态估计
等
"""

from kaibrain.agent.atomic.vision.image_understand import ImageUnderstandAgent
from kaibrain.agent.atomic.vision.object_detect import ObjectDetectAgent

__all__ = ["ImageUnderstandAgent", "ObjectDetectAgent"]
