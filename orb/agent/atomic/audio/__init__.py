"""
音频类Agent

包含：
- 语音识别（ASR）: faster-whisper 本地识别
- 语音合成（TTS）: edge-tts / CosyVoice
- 音频分析
- 声源定位
等
"""

from orb.agent.atomic.audio.asr import ASREngine
from orb.agent.atomic.audio.tts import TTSEngine

__all__ = ["ASREngine", "TTSEngine"]
