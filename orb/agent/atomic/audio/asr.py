"""
语音识别 (ASR) 模块

基于 faster-whisper 实现本地语音识别。
支持麦克风实时录音 + VAD 自动检测语音段。

使用:
    asr = ASREngine()
    text = asr.listen()  # 阻塞直到说完一句话
"""

from __future__ import annotations

import io
import queue
import threading
import time
from typing import Optional

import numpy as np

from orb.system.services.logger import get_logger

logger = get_logger(__name__)

# 录音参数
SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "float32"

# VAD 参数
SILENCE_THRESHOLD = 0.01       # 静音阈值 (RMS)
SPEECH_START_FRAMES = 3        # 连续几帧超过阈值才算开始说话
SILENCE_END_SECONDS = 1.5      # 说话后静音多久算说完
FRAME_DURATION_MS = 100        # 每帧时长 (ms)
MAX_RECORD_SECONDS = 30        # 最长录音时间


class ASREngine:
    """
    本地语音识别引擎

    基于 faster-whisper + sounddevice 实现。
    调用 listen() 会阻塞直到用户说完一句话并返回文字。
    """

    def __init__(
        self,
        model_size: str = "small",
        language: str = "zh",
        device: str = "cpu",
        compute_type: str = "int8",
    ):
        """
        初始化 ASR 引擎

        Args:
            model_size: Whisper 模型大小 (tiny/base/small/medium/large-v3)
            language: 识别语言
            device: 运行设备 (cpu/cuda)
            compute_type: 计算精度 (int8/float16/float32)
        """
        self._model_size = model_size
        self._language = language
        self._device = device
        self._compute_type = compute_type
        self._model = None
        self._loaded = False

    def _ensure_model(self) -> None:
        """延迟加载模型"""
        if self._loaded:
            return

        from faster_whisper import WhisperModel

        logger.info(f"加载 Whisper 模型: {self._model_size} (首次加载需下载...)")
        self._model = WhisperModel(
            self._model_size,
            device=self._device,
            compute_type=self._compute_type,
        )
        self._loaded = True
        logger.info("Whisper 模型加载完成")

    def transcribe(self, audio_data: np.ndarray) -> str:
        """
        识别音频数据

        Args:
            audio_data: float32 numpy 数组, 采样率 16kHz

        Returns:
            识别出的文字
        """
        self._ensure_model()

        segments, info = self._model.transcribe(
            audio_data,
            language=self._language,
            beam_size=5,
            vad_filter=True,
        )

        text = "".join(seg.text for seg in segments).strip()
        return text

    def listen(self, prompt: str = "🎤 请说话...") -> Optional[str]:
        """
        监听麦克风并识别语音

        使用 VAD 检测语音段: 等待说话开始 → 录音 → 检测到沉默 → 停止 → 识别

        Args:
            prompt: 提示文字

        Returns:
            识别出的文字，如果没有有效语音则返回 None
        """
        import sounddevice as sd

        self._ensure_model()

        print(prompt, end="", flush=True)

        frame_samples = int(SAMPLE_RATE * FRAME_DURATION_MS / 1000)
        audio_queue: queue.Queue = queue.Queue()

        def audio_callback(indata, frames, time_info, status):
            audio_queue.put(indata.copy())

        # 状态机
        recording = False
        speech_frames = 0
        silence_start = 0.0
        all_frames = []

        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            blocksize=frame_samples,
            callback=audio_callback,
        ):
            start_time = time.time()

            while True:
                # 超时保护
                if time.time() - start_time > MAX_RECORD_SECONDS:
                    if recording:
                        break
                    else:
                        print(" (超时，未检测到语音)")
                        return None

                try:
                    frame = audio_queue.get(timeout=0.5)
                except queue.Empty:
                    continue

                rms = np.sqrt(np.mean(frame ** 2))

                if not recording:
                    # 等待说话开始
                    if rms > SILENCE_THRESHOLD:
                        speech_frames += 1
                        if speech_frames >= SPEECH_START_FRAMES:
                            recording = True
                            print(" 录音中...", end="", flush=True)
                            # 把之前几帧也加进去（捕获开头）
                            all_frames.append(frame)
                    else:
                        speech_frames = 0
                else:
                    # 正在录音
                    all_frames.append(frame)

                    if rms < SILENCE_THRESHOLD:
                        if silence_start == 0:
                            silence_start = time.time()
                        elif time.time() - silence_start > SILENCE_END_SECONDS:
                            # 静音超过阈值，停止录音
                            break
                    else:
                        silence_start = 0.0

        if not all_frames:
            print(" (无有效音频)")
            return None

        # 合并音频
        audio_data = np.concatenate(all_frames, axis=0).flatten()
        duration = len(audio_data) / SAMPLE_RATE
        print(f" ({duration:.1f}s)")

        if duration < 0.3:
            return None

        # 识别
        text = self.transcribe(audio_data)
        return text if text else None

    def is_available(self) -> bool:
        """检查音频设备是否可用"""
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            # 检查是否有输入设备
            for d in devices if isinstance(devices, list) else [devices]:
                if isinstance(d, dict) and d.get("max_input_channels", 0) > 0:
                    return True
            return False
        except Exception:
            return False
