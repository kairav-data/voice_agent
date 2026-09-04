"""Microphone capture (energy-gated VAD) and neural text-to-speech.

Three TTS backends, picked by config.tts_backend:
  piper - offline neural voice (onnx), ~0.2 s per reply once warm
  edge  - Microsoft Edge neural voices, the most natural, needs internet
  sapi  - built-in Windows SAPI5 voices, robotic but always available
"""

from __future__ import annotations

import os
import queue
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

import numpy as np
import sounddevice as sd

from config import Config


def resolve_input_device(requested_device: int | None = None) -> tuple[int | None, str]:
    """Resolve the best input device index.

    If an explicit device index is passed (>= 0), return it and its name.
    If None is requested, scan for connected Bluetooth or wireless headsets.
    If a Bluetooth headset is connected, automatically select its microphone
    (preferring DirectSound or MME, completely ignoring unstable WDM-KS devices).
    Otherwise, fall back to the system default input device.

    Returns: (device_index_or_None, device_display_name)
    """
    try:
        devices = sd.query_devices()
        apis = sd.query_hostapis()
        total = len(devices)

        def is_safe_api(hostapi_idx: int) -> bool:
            if 0 <= hostapi_idx < len(apis):
                aname = apis[hostapi_idx].get("name", "").lower()
                return "wdm" not in aname and "kernel" not in aname
            return True

        # 1. Explicit user request (ensure it's not a buggy WDM-KS device)
        if requested_device is not None and requested_device >= 0:
            if requested_device < total:
                d = devices[requested_device]
                if is_safe_api(d.get("hostapi", -1)):
                    return requested_device, d.get("name", f"Device {requested_device}")
            # If requested device is invalid or WDM-KS, fall through to auto-detect

        # 2. Check system default endpoints
        def_out_idx = sd.default.device[1]
        def_in_idx = sd.default.device[0]

        bt_keywords = (
            "bluetooth", "wireless", "headset", "hands-free", "buds",
            "airpods", "oneplus", "galaxy buds", "earphone", "bthhfenum"
        )

        is_bt_output = False
        out_name = ""
        if 0 <= def_out_idx < total:
            out_name = devices[def_out_idx].get("name", "").lower()
            if any(k in out_name for k in bt_keywords):
                is_bt_output = True

        candidates: list[tuple[int, int, str]] = []
        for i, d in enumerate(devices):
            if d.get("max_input_channels", 0) > 0:
                hostapi = d.get("hostapi", -1)
                if not is_safe_api(hostapi):
                    continue  # Strictly avoid WDM-KS

                name = d.get("name", "").lower()
                if any(k in name for k in bt_keywords):
                    score = 0
                    api_name = apis[hostapi]["name"].lower() if 0 <= hostapi < len(apis) else ""
                    # DirectSound is most reliable on Windows Bluetooth, followed by MME & WASAPI
                    if "directsound" in api_name:
                        score += 30
                    elif "mme" in api_name:
                        score += 20
                    elif "wasapi" in api_name:
                        score += 15

                    if is_bt_output and out_name:
                        cleaned_words = out_name.replace("(", " ").replace(")", " ").replace("-", " ").split()
                        for word in cleaned_words:
                            if len(word) > 3 and word in name:
                                score += 5
                    candidates.append((score, i, d.get("name", f"Device {i}")))

        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            best_idx = candidates[0][1]
            best_name = candidates[0][2]
            return best_idx, best_name

        # 3. Fall back to system default input
        if 0 <= def_in_idx < total and is_safe_api(devices[def_in_idx].get("hostapi", -1)):
            return None, devices[def_in_idx].get("name", "System Default")
    except Exception as e:
        print(f"[audio] Warning resolving audio input device: {e}")

    return None, "System Default"


# --------------------------------------------------------------------------- #
# Microphone
# --------------------------------------------------------------------------- #
class Recorder:
    """Records one utterance at a time using a simple energy gate.

    Speech starts when a few consecutive frames are above the noise threshold and
    ends after `silence_hangover_s` of quiet. A short pre-roll is kept so the
    first syllable is not clipped.
    """

    def __init__(
        self,
        cfg: Config,
        on_meter: Callable[[float], None] | None = None,
        on_speech_start: Callable[[], None] | None = None,
        on_speech_end: Callable[[], None] | None = None,
    ):
        self.cfg = cfg
        self.on_meter = on_meter
        self.on_speech_start = on_speech_start
        self.on_speech_end = on_speech_end
        self.resolved_device, self.device_name = resolve_input_device(cfg.input_device)
        self.frame_len = int(cfg.samplerate * cfg.frame_ms / 1000)
        self.threshold = cfg.energy_floor
        self._q: queue.Queue[np.ndarray] = queue.Queue()
        self._stop_event = threading.Event()
        self._commit_event = threading.Event()

    # -- helpers ----------------------------------------------------------- #
    @staticmethod
    def _rms(frame: np.ndarray) -> float:
        return float(np.sqrt(np.mean(np.square(frame, dtype=np.float64)) + 1e-12))

    def _callback(self, indata, frames, time_info, status):  # noqa: ANN001
        if status:
            pass  # over/underflows are not fatal for speech capture
        frame = indata[:, 0].copy()
        self._q.put(frame)
        if self.on_meter:
            try:
                self.on_meter(self._rms(frame))
            except Exception:
                pass

    def _open_stream(self) -> sd.InputStream:
        dev = self.resolved_device
        try:
            return sd.InputStream(
                samplerate=self.cfg.samplerate,
                blocksize=self.frame_len,
                device=dev,
                channels=1,
                dtype="float32",
                callback=self._callback,
            )
        except Exception as e:
            print(f"[audio] Warning: could not open device {dev} ({e}), falling back to default device")
            return sd.InputStream(
                samplerate=self.cfg.samplerate,
                blocksize=self.frame_len,
                device=None,
                channels=1,
                dtype="float32",
                callback=self._callback,
            )

    # -- public ------------------------------------------------------------ #
    def calibrate(self, seconds: float = 1.0) -> float:
        """Measure the room noise floor and set the speech threshold."""
        levels: list[float] = []
        with self._open_stream():
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                try:
                    levels.append(self._rms(self._q.get(timeout=1.0)))
                except queue.Empty:
                    break
        self._drain()
        noise = float(np.median(levels)) if levels else 0.0
        self.threshold = max(self.cfg.energy_floor, noise * self.cfg.energy_multiplier)
        return self.threshold

    def _drain(self) -> None:
        while not self._q.empty():
            try:
                self._q.get_nowait()
            except queue.Empty:
                break

    def cancel(self) -> None:
        """Cancel current recording immediately and discard audio."""
        self._stop_event.set()

    def commit(self) -> None:
        """Commit current recording immediately and return recorded audio for transcription."""
        self._commit_event.set()

    def record_utterance(self) -> np.ndarray | None:
        """Block until the user speaks, then return float32 mono audio at 16 kHz."""
        cfg = self.cfg
        self._stop_event.clear()
        self._commit_event.clear()
        preroll_frames = max(1, int(0.3 * 1000 / cfg.frame_ms))
        hangover_frames = max(1, int(cfg.silence_hangover_s * 1000 / cfg.frame_ms))
        min_speech_frames = max(1, int(cfg.min_speech_s * 1000 / cfg.frame_ms))
        max_frames = int(cfg.max_utterance_s * 1000 / cfg.frame_ms)

        preroll: list[np.ndarray] = []
        voiced: list[np.ndarray] = []
        all_frames: list[np.ndarray] = []
        started = False
        loud_streak = 0
        quiet_streak = 0

        self._drain()
        with self._open_stream():
            while True:
                if self._stop_event.is_set():
                    self._stop_event.clear()
                    return None

                if self._commit_event.is_set():
                    self._commit_event.clear()
                    if self.on_speech_end:
                        try:
                            self.on_speech_end()
                        except Exception:
                            pass
                    if voiced:
                        break
                    if all_frames:
                        voiced = list(all_frames)
                        break
                    return None

                try:
                    frame = self._q.get(timeout=0.2)
                except queue.Empty:
                    continue

                all_frames.append(frame)
                level = self._rms(frame)
                if not started:
                    preroll.append(frame)
                    if len(preroll) > preroll_frames:
                        preroll.pop(0)
                    loud_streak = loud_streak + 1 if level > self.threshold else 0
                    if loud_streak >= 2:
                        started = True
                        voiced = list(preroll)
                        voiced.append(frame)
                        if self.on_speech_start:
                            try:
                                self.on_speech_start()
                            except Exception:
                                pass
                    continue

                voiced.append(frame)
                quiet_streak = 0 if level > self.threshold else quiet_streak + 1
                if quiet_streak >= hangover_frames or len(voiced) >= max_frames:
                    if self.on_speech_end:
                        try:
                            self.on_speech_end()
                        except Exception:
                            pass
                    break

        if not voiced or len(voiced) < 3:
            return None
        return np.concatenate(voiced).astype(np.float32)

    @staticmethod
    def list_devices() -> str:
        return str(sd.query_devices())


# --------------------------------------------------------------------------- #
# Text cleanup
# --------------------------------------------------------------------------- #
_MD = re.compile(r"[`*_#>|]|\[[^\]]*\]\([^)]*\)")


def clean_for_speech(text: str) -> str:
    """Strip markdown / code fences so the TTS engine does not read symbols."""
    text = re.sub(r"```.*?```", " code block omitted. ", text, flags=re.S)
    text = re.sub(r"<think>.*?</think>", " ", text, flags=re.S | re.I)
    text = _MD.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def split_sentences(text: str, min_len: int = 30) -> list[str]:
    """Split into sentences so the next one can be synthesised while this one plays."""
    parts = re.split(r"(?<=[.!?])\s+", text)
    merged: list[str] = []
    for part in parts:
        if merged and len(merged[-1]) < min_len:
            merged[-1] = f"{merged[-1]} {part}"
        else:
            merged.append(part)
    return [m for m in merged if m.strip()]


# --------------------------------------------------------------------------- #
# TTS backends
# --------------------------------------------------------------------------- #
def _wpm_to_sapi_rate(wpm: int) -> int:
    """SAPI rate is -10..10; ~200 wpm is 0."""
    return max(-10, min(10, round((wpm - 200) / 20)))


def find_piper_model(cfg: Config) -> str | None:
    """Explicit path, else the voice named in tts_voice, else the first .onnx found."""
    if cfg.piper_model and os.path.isfile(cfg.piper_model):
        return cfg.piper_model
    voices_dir = cfg.piper_dir or os.path.join(os.path.dirname(__file__), "voices")
    if not os.path.isdir(voices_dir):
        return None
    models = sorted(f for f in os.listdir(voices_dir) if f.endswith(".onnx"))
    if not models:
        return None
    wanted = (cfg.tts_voice or "").lower().strip()
    if wanted:
        for name in models:
            if wanted in name.lower():
                return os.path.join(voices_dir, name)
        # If wanted is an Edge voice or backend is auto, fall back to first available piper voice
        backend = (cfg.tts_backend or "auto").lower()
        if "neural" in wanted or backend == "auto":
            return os.path.join(voices_dir, models[0])
        return None
    return os.path.join(voices_dir, models[0])


class _PiperBackend:
    """Offline neural TTS. Model files live in ./voices (see README)."""

    name = "piper"

    def __init__(self, cfg: Config):
        from piper import PiperVoice

        model = find_piper_model(cfg)
        if model is None:
            raise RuntimeError("no .onnx voice found in ./voices")
        self.cfg = cfg
        self.model_name = os.path.basename(model)
        self._voice = PiperVoice.load(model)
        self._syn_cfg = None
        try:  # piper >= 1.3 exposes speed/volume through SynthesisConfig
            from piper import SynthesisConfig

            self._syn_cfg = SynthesisConfig(
                length_scale=max(0.5, min(2.0, 200.0 / max(60, cfg.tts_rate))),
                volume=max(0.0, min(1.0, cfg.tts_volume)),
            )
        except Exception:
            pass
        self.synth("Ready.")  # warm the graph so the first real reply is fast

    def synth(self, text: str) -> tuple[np.ndarray, int]:
        kwargs = {"syn_config": self._syn_cfg} if self._syn_cfg is not None else {}
        parts: list[np.ndarray] = []
        rate = getattr(self._voice.config, "sample_rate", 22050)
        for chunk in self._voice.synthesize(text, **kwargs):
            rate = getattr(chunk, "sample_rate", rate)
            if hasattr(chunk, "audio_float_array"):
                parts.append(np.asarray(chunk.audio_float_array, dtype=np.float32))
            else:
                raw = np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16)
                parts.append(raw.astype(np.float32) / 32768.0)
        if not parts:
            return np.zeros(0, dtype=np.float32), rate
        return np.concatenate(parts), rate


class _EdgeBackend:
    """Microsoft Edge neural voices. Highest quality, needs internet."""

    name = "edge"

    def __init__(self, cfg: Config):
        import socket

        import edge_tts  # noqa: F401  (availability check)
        import soundfile  # noqa: F401  (mp3 decoding)

        socket.create_connection(("speech.platform.bing.com", 443), timeout=5).close()
        self.cfg = cfg
        self.voice_name = cfg.tts_voice or cfg.edge_voice
        pct = max(-50, min(50, round((cfg.tts_rate - 200) / 2)))
        self.rate = f"{pct:+d}%"

    def synth(self, text: str) -> tuple[np.ndarray, int]:
        import asyncio
        import io

        import edge_tts
        import soundfile as sf

        async def _run() -> bytes:
            buf = io.BytesIO()
            comm = edge_tts.Communicate(text, self.voice_name, rate=self.rate)
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    buf.write(chunk["data"])
            return buf.getvalue()

        raw = asyncio.run(_run())
        if not raw:
            return np.zeros(0, dtype=np.float32), 24000
        data, rate = sf.read(io.BytesIO(raw), dtype="float32")
        if data.ndim > 1:
            data = data.mean(axis=1)
        return data * max(0.0, min(1.0, self.cfg.tts_volume)), rate


class _SapiBackend:
    """Built-in Windows voices over COM.

    pyttsx3 is not usable here: its driver only speaks the first utterance when
    driven from a worker thread, then runAndWait() returns instantly and silently.
    """

    name = "sapi"

    def __init__(self, cfg: Config):
        import comtypes
        import comtypes.client

        comtypes.CoInitialize()
        self._voice = comtypes.client.CreateObject("SAPI.SpVoice")
        self._voice.Rate = _wpm_to_sapi_rate(cfg.tts_rate)
        self._voice.Volume = max(0, min(100, int(cfg.tts_volume * 100)))
        if cfg.tts_voice:
            wanted = cfg.tts_voice.lower()
            tokens = self._voice.GetVoices()
            for i in range(tokens.Count):
                token = tokens.Item(i)
                if wanted in token.GetDescription().lower():
                    self._voice.Voice = token
                    break

    def speak(self, text: str) -> None:
        self._voice.Speak(text)


class _PowerShellBackend:
    """Last resort: System.Speech in a short-lived PowerShell process."""

    name = "powershell"

    def __init__(self, cfg: Config):
        import shutil
        import subprocess

        self._subprocess = subprocess
        self._exe = shutil.which("powershell") or "powershell"
        self._rate = _wpm_to_sapi_rate(cfg.tts_rate)
        self._volume = max(0, min(100, int(cfg.tts_volume * 100)))

    def speak(self, text: str) -> None:
        script = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$s.Rate = {self._rate}; $s.Volume = {self._volume}; "
            "$s.Speak($env:VA_TTS_TEXT)"
        )
        self._subprocess.run(
            [self._exe, "-NoProfile", "-NonInteractive", "-Command", script],
            env=dict(os.environ, VA_TTS_TEXT=text),
            capture_output=True,
            timeout=120,
        )


BACKENDS = {
    "piper": _PiperBackend,
    "edge": _EdgeBackend,
    "sapi": _SapiBackend,
    "powershell": _PowerShellBackend,
}
AUTO_ORDER = ("piper", "edge", "sapi", "powershell")


# --------------------------------------------------------------------------- #
# Speaker
# --------------------------------------------------------------------------- #
class Speaker:
    """Queued text-to-speech.

    The backend is built inside the worker thread (SAPI objects are apartment
    bound, and piper/onnx prefers a single owning thread). Sentences are
    synthesised one ahead of playback so speech starts as soon as possible.
    """

    def __init__(self, cfg: Config, on_state: Callable[[str, dict], None] | None = None):
        self.cfg = cfg
        self.on_state = on_state
        self.backend_name = "none"
        self._backend = None
        self._synth_lock = threading.Lock()
        self._q: queue.Queue[str | None] = queue.Queue()
        self._streams: dict[int, sd.OutputStream] = {}
        self._idle = threading.Event()
        self._idle.set()
        self._ready = threading.Event()
        self._interrupt_event = threading.Event()
        self._thread: threading.Thread | None = None
        if cfg.tts_enabled:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def interrupt(self) -> None:
        """Immediately stop current and queued speech."""
        self._interrupt_event.set()
        while not self._q.empty():
            try:
                self._q.get_nowait()
            except queue.Empty:
                break
        self._close_streams()
        self._idle.set()
        if self.on_state:
            try:
                self.on_state("idle", {})
            except Exception:
                pass

    # -- backend selection --------------------------------------------------- #
    def _make_backend(self):
        wanted = (self.cfg.tts_backend or "auto").lower()
        order = AUTO_ORDER if wanted == "auto" else (wanted, "sapi", "powershell")
        for name in order:
            factory = BACKENDS.get(name)
            if factory is None:
                print(f"[tts] unknown backend '{name}'", file=sys.stderr)
                continue
            try:
                backend = factory(self.cfg)
                self.backend_name = backend.name
                detail = getattr(backend, "model_name", None) or getattr(
                    backend, "voice_name", ""
                )
                print(f"[tts] {backend.name}" + (f" ({detail})" if detail else ""))
                return backend
            except Exception as exc:
                prefix = "" if wanted == "auto" else "requested backend failed - "
                print(f"[tts] {prefix}{name} unavailable: {exc}", file=sys.stderr)
        return None

    # -- worker -------------------------------------------------------------- #
    def _play(self, audio: np.ndarray, rate: int) -> None:
        """Write to a stream kept open per sample rate; reopening costs ~0.5 s."""
        if not audio.size:
            return
        stream = self._streams.get(rate)
        if stream is None:
            stream = sd.OutputStream(samplerate=rate, channels=1, dtype="float32")
            stream.start()
            self._streams[rate] = stream
        try:
            stream.write(np.ascontiguousarray(audio, dtype=np.float32))
        except Exception:  # device changed under us - reopen once
            self._close_streams()
            sd.play(audio, rate)
            sd.wait()

    def _close_streams(self) -> None:
        for stream in self._streams.values():
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        self._streams.clear()

    def _run(self) -> None:
        backend = self._make_backend()
        self._backend = backend
        if backend is None:
            print("[tts] no speech backend available, replies will be text only",
                  file=sys.stderr)
        streaming = backend is not None and hasattr(backend, "synth")
        pool = ThreadPoolExecutor(max_workers=1) if streaming else None
        self._ready.set()

        while True:
            text = self._q.get()
            if text is None:
                break
            self._idle.clear()
            self._interrupt_event.clear()
            if self.on_state:
                try:
                    self.on_state("speaking", {"text": text})
                except Exception:
                    pass
            try:
                if backend is None:
                    pass
                elif not streaming:
                    backend.speak(text)
                else:
                    chunks = split_sentences(text)
                    pending = pool.submit(backend.synth, chunks[0])
                    for i, _chunk in enumerate(chunks):
                        if self._interrupt_event.is_set():
                            break
                        audio, rate = pending.result()
                        if self._interrupt_event.is_set():
                            break
                        if i + 1 < len(chunks):
                            pending = pool.submit(backend.synth, chunks[i + 1])
                        self._play(audio, rate)
            except Exception as exc:  # never let a TTS hiccup kill the agent
                print(f"[tts] {exc}", file=sys.stderr)
            finally:
                self._idle.set()
                if self.on_state:
                    try:
                        self.on_state("idle", {})
                    except Exception:
                        pass

        self._close_streams()
        if pool is not None:
            pool.shutdown(wait=False)

    # -- public -------------------------------------------------------------- #
    def say(self, text: str, block: bool = True) -> None:
        text = clean_for_speech(text)
        if not text or not self.cfg.tts_enabled or self._thread is None:
            return
        self._idle.clear()
        self._q.put(text)
        if block:
            self.wait()

    def wait(self) -> None:
        """Wait until the queue is drained (so the mic does not hear the speaker)."""
        while not self._q.empty():
            time.sleep(0.05)
        self._idle.wait()
        time.sleep(0.15)

    def close(self) -> None:
        if self._thread is not None:
            self._q.put(None)

    def synth_wav_bytes(self, text: str) -> tuple[bytes, int] | None:
        """Synthesizes text to 16-bit PCM WAV bytes in memory without local playback.
        
        Enables streaming audio directly to mobile/remote clients (phone speaker).
        """
        text = clean_for_speech(text)
        if not text:
            return None
        self._ready.wait(timeout=3.0)
        backend = getattr(self, "_backend", None)
        if backend is None or not hasattr(backend, "synth"):
            return None
        with self._synth_lock:
            try:
                chunks = split_sentences(text)
                audio_parts = []
                sample_rate = 22050
                for chunk in chunks:
                    audio, chunk_rate = backend.synth(chunk)
                    if audio.size > 0:
                        audio_parts.append(audio)
                        sample_rate = chunk_rate
                if not audio_parts:
                    return None
                full_audio = np.concatenate(audio_parts)
                import io
                import soundfile as sf
                buf = io.BytesIO()
                sf.write(buf, full_audio, sample_rate, format="WAV", subtype="PCM_16")
                return buf.getvalue(), sample_rate
            except Exception as exc:
                print(f"[tts synth_wav error]: {exc}", file=sys.stderr)
                return None


# --------------------------------------------------------------------------- #
# Voice listing (for --list-voices)
# --------------------------------------------------------------------------- #
def list_voices(cfg: Config) -> str:
    lines: list[str] = ["piper (offline) - .onnx files in ./voices:"]
    voices_dir = cfg.piper_dir or os.path.join(os.path.dirname(__file__), "voices")
    found = sorted(os.listdir(voices_dir)) if os.path.isdir(voices_dir) else []
    lines += [f"  {f}" for f in found if f.endswith(".onnx")] or ["  (none downloaded)"]
    lines.append(
        "  more voices: python -m piper.download_voices --download-dir voices en_US-ryan-high"
    )

    lines.append("")
    lines.append("edge (online) - English neural voices:")
    try:
        import asyncio

        import edge_tts

        voices = asyncio.run(edge_tts.list_voices())
        names = sorted(v["ShortName"] for v in voices if v["ShortName"].startswith("en-"))
        lines += ["  " + ", ".join(names[i:i + 4]) for i in range(0, len(names), 4)]
    except Exception as exc:
        lines.append(f"  (could not fetch list: {exc})")

    lines.append("")
    lines.append("sapi (built in):")
    try:
        import comtypes
        import comtypes.client

        comtypes.CoInitialize()
        tokens = comtypes.client.CreateObject("SAPI.SpVoice").GetVoices()
        lines += [f"  {tokens.Item(i).GetDescription()}" for i in range(tokens.Count)]
    except Exception as exc:
        lines.append(f"  (unavailable: {exc})")
    return "\n".join(lines)

# --------------------------------------------------------------------------- #
# Voice demo (for --demo-voices)
# --------------------------------------------------------------------------- #
DEMO_LINE = ("Hello Kairav. I found six python files in that folder, "
             "and your disk is about eighty percent full.")


def demo_voices(cfg: Config) -> None:
    """Speak the same line through every available voice so you can pick one."""
    import copy

    candidates: list[tuple[str, str, str]] = []  # (backend, voice, label)
    voices_dir = cfg.piper_dir or os.path.join(os.path.dirname(__file__), "voices")
    if os.path.isdir(voices_dir):
        for name in sorted(f for f in os.listdir(voices_dir) if f.endswith(".onnx")):
            stem = name[:-5]
            candidates.append(("piper", stem, f"piper offline, {stem}"))
    candidates += [
        ("edge", "en-US-AvaNeural", "edge online, Ava, US female"),
        ("edge", "en-US-AndrewNeural", "edge online, Andrew, US male"),
        ("edge", "en-IN-NeerjaNeural", "edge online, Neerja, Indian female"),
        ("edge", "en-IN-PrabhatNeural", "edge online, Prabhat, Indian male"),
        ("sapi", "", "windows built in voice"),
    ]

    for backend, voice, label in candidates:
        trial = copy.copy(cfg)
        trial.tts_backend = backend
        trial.tts_voice = voice
        trial.tts_enabled = True
        print(f"\n--- {label}")
        print(f"    run with: --tts-backend {backend}" + (f" --voice {voice}" if voice else ""))
        speaker = Speaker(trial)
        try:
            speaker.say(f"{label}. {DEMO_LINE}")
        finally:
            speaker.close()
        time.sleep(0.4)
