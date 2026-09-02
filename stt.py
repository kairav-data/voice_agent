"""Speech to text with faster-whisper (runs fully offline once the model is cached)."""

from __future__ import annotations

import numpy as np

from config import Config


class Transcriber:
    def __init__(self, cfg: Config):
        from faster_whisper import WhisperModel

        self.cfg = cfg
        self.model = WhisperModel(
            cfg.whisper_model,
            device=cfg.whisper_device,
            compute_type=cfg.whisper_compute,
        )

    def transcribe(self, audio: np.ndarray) -> str:
        """audio: float32 mono @ 16 kHz in [-1, 1]."""
        segments, _info = self.model.transcribe(
            audio,
            language=self.cfg.language,
            beam_size=1,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 300},
            condition_on_previous_text=False,
        )
        return " ".join(s.text.strip() for s in segments).strip()
