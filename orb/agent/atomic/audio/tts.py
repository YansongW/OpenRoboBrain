"""
语音合成 (TTS) 模块

支持多种 TTS 后端:
1. edge-tts (默认, 微软免费在线 TTS, 效果好, 无需 GPU)
2. pyttsx3 (离线 fallback)

使用:
    tts = TTSEngine()
    await tts.speak("你好，有什么可以帮你的？")
"""

from __future__ import annotations

import asyncio
import io
import tempfile
import os
from pathlib import Path
from typing import Optional

from orb.system.services.logger import get_logger

logger = get_logger(__name__)


class TTSEngine:
    """
    语音合成引擎

    默认使用 edge-tts (微软免费 TTS 服务, 中文效果优秀)。
    """

    def __init__(
        self,
        voice: str = "zh-CN-XiaoxiaoNeural",
        rate: str = "+0%",
        volume: str = "+0%",
    ):
        """
        初始化 TTS 引擎

        Args:
            voice: edge-tts 语音名称
                推荐中文女声: zh-CN-XiaoxiaoNeural, zh-CN-XiaoyiNeural
                推荐中文男声: zh-CN-YunxiNeural, zh-CN-YunjianNeural
            rate: 语速调整 (如 "+20%", "-10%")
            volume: 音量调整 (如 "+10%", "-5%")
        """
        self._voice = voice
        self._rate = rate
        self._volume = volume
        self._temp_dir = Path(tempfile.gettempdir()) / "orb_tts"
        self._temp_dir.mkdir(exist_ok=True)

    async def synthesize(self, text: str) -> Optional[bytes]:
        """
        合成语音，返回 MP3 音频数据

        Args:
            text: 要合成的文字

        Returns:
            MP3 音频数据 (bytes)，失败返回 None
        """
        try:
            import edge_tts

            communicate = edge_tts.Communicate(
                text=text,
                voice=self._voice,
                rate=self._rate,
                volume=self._volume,
            )

            audio_chunks = []
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_chunks.append(chunk["data"])

            if audio_chunks:
                return b"".join(audio_chunks)
            return None

        except Exception as e:
            logger.error(f"TTS 合成失败: {e}")
            return None

    async def speak(self, text: str) -> bool:
        """
        合成语音并播放

        Args:
            text: 要播放的文字

        Returns:
            是否播放成功
        """
        if not text or not text.strip():
            return False

        # 1. 合成为 MP3
        audio_data = await self.synthesize(text)
        if not audio_data:
            logger.warning("TTS 合成返回空音频")
            return False

        # 2. 保存到临时文件
        temp_file = self._temp_dir / "tts_output.mp3"
        temp_file.write_bytes(audio_data)

        # 3. 播放
        return await self._play_audio(temp_file)

    async def _play_audio(self, audio_path: Path) -> bool:
        """
        播放音频文件

        尝试多种播放方式:
        1. sounddevice + soundfile (如果安装了 soundfile)
        2. av (ffmpeg, 已安装作为 faster-whisper 依赖)
        3. Windows 系统命令 fallback
        """
        # 方法 1: 使用 av (PyAV) 解码 + sounddevice 播放
        try:
            import av
            import sounddevice as sd
            import numpy as np

            container = av.open(str(audio_path))
            audio_stream = container.streams.audio[0]

            frames = []
            for frame in container.decode(audio=0):
                # 转为 numpy float32
                arr = frame.to_ndarray()
                if arr.ndim > 1:
                    arr = arr.mean(axis=0)  # 多声道转单声道
                frames.append(arr.astype(np.float32))

            container.close()

            if not frames:
                return False

            audio = np.concatenate(frames)

            # 归一化到 [-1, 1]
            max_val = np.abs(audio).max()
            if max_val > 0:
                audio = audio / max_val

            sample_rate = audio_stream.codec_context.sample_rate or 24000

            # 阻塞播放
            sd.play(audio, samplerate=sample_rate)
            sd.wait()
            return True

        except Exception as e:
            logger.debug(f"av+sounddevice 播放失败: {e}")

        # 方法 2: Windows 系统命令
        try:
            import sys
            if sys.platform == "win32":
                # 使用 PowerShell 的 MediaPlayer
                proc = await asyncio.create_subprocess_exec(
                    "powershell", "-c",
                    f'(New-Object Media.SoundPlayer "{audio_path}").PlaySync()',
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await proc.wait()
                return proc.returncode == 0
        except Exception as e:
            logger.debug(f"系统命令播放失败: {e}")

        logger.warning("所有音频播放方式均失败")
        return False

    @staticmethod
    async def list_voices(language: str = "zh") -> list:
        """列出可用的语音"""
        try:
            import edge_tts
            voices = await edge_tts.list_voices()
            return [v for v in voices if language in v.get("Locale", "")]
        except Exception:
            return []
