"""FastAPI and WebSocket server for the Voice Agent UI Command Center.

Bridges the local Python audio/STT/Ollama/TTS pipeline with a 60 FPS
futuristic web interface over low-latency WebSockets.
"""

from __future__ import annotations

import asyncio
import base64
import ctypes
import fractions
import io
import json
import os
import socket
import sys
import threading
import time
import uuid
import webbrowser
from typing import Any, Callable, Dict, List, Optional, Set

import av
from aiortc import MediaStreamTrack, RTCPeerConnection, RTCSessionDescription
import numpy as np
from PIL import Image
import requests
import soundfile as sf
import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from audio import Recorder, Speaker, list_voices
from config import Config
from llm import OllamaAgent
from stt import Transcriber
from tools import ToolBox, assess_command_risk, classify


def get_local_ip() -> str:
    """Detect LAN IPv4 address for phone connections."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def generate_self_signed_cert(cert_path: str, key_path: str, ip: str = "127.0.0.1") -> None:
    """Auto-generate local self-signed certificate for HTTPS phone microphone access."""
    import datetime
    import ipaddress
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "VoiceAgent"),
        x509.NameAttribute(NameOID.COMMON_NAME, ip),
    ])

    san_list: List[x509.GeneralName] = [
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
    ]
    if ip not in ("127.0.0.1", "localhost"):
        try:
            san_list.append(x509.IPAddress(ipaddress.IPv4Address(ip)))
        except Exception:
            pass

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow())
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
        .add_extension(x509.SubjectAlternativeName(san_list), critical=False)
        .sign(key, hashes.SHA256())
    )

    with open(key_path, "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ))
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))


class FastScreenCapture:
    """Ultra-fast zero-copy Windows GDI screen capture delivering 60-200 FPS."""

    def __init__(self):
        self.user32 = ctypes.windll.user32
        self.gdi32 = ctypes.windll.gdi32
        self.w = self.user32.GetSystemMetrics(0)
        self.h = self.user32.GetSystemMetrics(1)
        self.hdc_screen = self.user32.GetDC(0)
        self.hdc_mem = self.gdi32.CreateCompatibleDC(self.hdc_screen)
        self.hbm = self.gdi32.CreateCompatibleBitmap(self.hdc_screen, self.w, self.h)
        self.gdi32.SelectObject(self.hdc_mem, self.hbm)

        self.bmi = bytearray(40)
        self.bmi[0:4] = (40).to_bytes(4, "little")
        self.bmi[4:8] = (self.w).to_bytes(4, "little", signed=True)
        self.bmi[8:12] = (-self.h).to_bytes(4, "little", signed=True)
        self.bmi[12:14] = (1).to_bytes(2, "little")
        self.bmi[14:16] = (32).to_bytes(2, "little")
        self.bmi[16:20] = (0).to_bytes(4, "little")

        self.buf = bytearray(self.w * self.h * 4)
        self.c_buf = (ctypes.c_char * len(self.buf)).from_buffer(self.buf)
        self.bmi_buf = (ctypes.c_char * 40).from_buffer(self.bmi)

    def grab_frame(self) -> av.VideoFrame:
        self.gdi32.BitBlt(self.hdc_mem, 0, 0, self.w, self.h, self.hdc_screen, 0, 0, 0x00CC0020)
        self.gdi32.GetDIBits(self.hdc_mem, self.hbm, 0, self.h, self.c_buf, self.bmi_buf, 0)
        arr = np.frombuffer(self.buf, dtype=np.uint8).reshape((self.h, self.w, 4))
        return av.VideoFrame.from_ndarray(arr, format="bgra")

    def grab_frame_jpeg(self, quality: int = 65, scale: float = 0.75) -> bytes:
        self.gdi32.BitBlt(self.hdc_mem, 0, 0, self.w, self.h, self.hdc_screen, 0, 0, 0x00CC0020)
        self.gdi32.GetDIBits(self.hdc_mem, self.hbm, 0, self.h, self.c_buf, self.bmi_buf, 0)
        img = Image.frombuffer("RGBA", (self.w, self.h), bytes(self.buf), "raw", "BGRA", 0, 1)
        if scale != 1.0:
            nw = max(320, int(self.w * scale))
            nh = max(180, int(self.h * scale))
            img = img.resize((nw, nh), Image.Resampling.BILINEAR)
        img_rgb = img.convert("RGB")
        out = io.BytesIO()
        img_rgb.save(out, format="JPEG", quality=quality)
        return out.getvalue()

    def close(self):
        try:
            self.gdi32.DeleteObject(self.hbm)
            self.gdi32.DeleteDC(self.hdc_mem)
            self.user32.ReleaseDC(0, self.hdc_screen)
        except Exception:
            pass


class ScreenVideoStreamTrack(MediaStreamTrack):
    """WebRTC 60 FPS Screen Video Stream Track."""

    kind = "video"

    def __init__(self, fps: int = 60):
        super().__init__()
        self.fps = fps
        self.fsc = FastScreenCapture()
        self._start_time = None
        self._frame_count = 0

    async def recv(self) -> av.VideoFrame:
        if self._start_time is None:
            self._start_time = time.monotonic()

        self._frame_count += 1
        target_time = self._start_time + (self._frame_count / self.fps)
        now = time.monotonic()
        sleep_dur = target_time - now
        if sleep_dur > 0:
            await asyncio.sleep(sleep_dur)

        frame = self.fsc.grab_frame()
        frame.pts = self._frame_count
        frame.time_base = fractions.Fraction(1, self.fps)
        return frame

    def stop(self):
        super().stop()
        self.fsc.close()


class ScreenStreamer:
    """Legacy MJPEG screen streamer wrapper."""

    def __init__(self):
        self.fsc = FastScreenCapture()

    def grab_frame_jpeg(self, quality: int = 65, scale: float = 0.75) -> bytes:
        return self.fsc.grab_frame_jpeg(quality=quality, scale=scale)


def decode_mobile_audio(audio_bytes: bytes) -> np.ndarray:
    """Universal audio decoder for WebM, Opus, MP4, AAC, WAV, etc. returning 16kHz float32 mono."""
    if not audio_bytes:
        return np.zeros(0, dtype=np.float32)

    # 1. Primary: Use PyAV / FFmpeg (decodes WebM, Opus, MP4, AAC, OGG, etc.)
    try:
        container = av.open(io.BytesIO(audio_bytes))
        audio_stream = next((s for s in container.streams if s.type == "audio"), None)
        if audio_stream is not None:
            resampler = av.AudioResampler(format="fltp", layout="mono", rate=16000)
            frames = []
            for frame in container.decode(audio_stream):
                for rf in resampler.resample(frame):
                    frames.append(rf.to_ndarray().flatten())
            if frames:
                result = np.concatenate(frames).astype(np.float32)
                return result
    except Exception:
        pass

    # 2. Secondary: Fallback to soundfile (WAV, FLAC, RAW)
    try:
        data, sr = sf.read(io.BytesIO(audio_bytes), dtype="float32")
        if data.ndim > 1:
            data = data.mean(axis=1)
        if sr != 16000:
            target_len = int(len(data) * 16000 / sr)
            indices = np.linspace(0, len(data) - 1, target_len)
            data = np.interp(indices, np.arange(len(data)), data).astype(np.float32)
        return data
    except Exception as e:
        print(f"[ui_server] Error decoding mobile audio bytes: {e}")

    return np.zeros(0, dtype=np.float32)


# --------------------------------------------------------------------------- #
# Application & Global State
# --------------------------------------------------------------------------- #
app = FastAPI(title="Voice Agent Command Center", version="2.4.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UI_DIR = os.path.join(BASE_DIR, "ui")


class AgentUIManager:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.active_sockets: List[WebSocket] = []

        # Current State
        self.state = "idle"  # idle | listening | hearing | processing | thinking | tool | confirmation | executing | speaking | success | error
        self.last_error = ""
        self.continuous_listening = False
        self._listen_thread: Optional[threading.Thread] = None
        self._listen_active = False

        # Pending Confirmation
        self._pending_confirm_id: Optional[str] = None
        self._pending_confirm_event = threading.Event()
        self._pending_confirm_result = False
        self._pending_confirm_data: Dict[str, Any] = {}

        # History & Activity Timeline
        self.history: List[Dict[str, Any]] = []
        self.timeline: List[Dict[str, Any]] = []

        # Subsystems
        self.toolbox = ToolBox(self.cfg, confirm_cb=self._ui_confirm_cb)
        self.agent = OllamaAgent(self.cfg, self.toolbox)
        self.speaker = Speaker(self.cfg, on_state=self._on_tts_state)

        # Mic & Whisper (initialized lazily or immediately)
        self.stt: Optional[Transcriber] = None
        self.recorder: Optional[Recorder] = None
        self._init_audio_pipeline()

    def _init_audio_pipeline(self) -> None:
        try:
            print("[ui_server] Initializing Faster-Whisper...")
            self.stt = Transcriber(self.cfg)
            self.recorder = Recorder(
                self.cfg,
                on_meter=self._on_mic_meter,
                on_speech_start=self._on_speech_start,
                on_speech_end=self._on_speech_end,
            )
            # Calibrate in background thread to not block server startup
            threading.Thread(target=self._calibrate_mic, daemon=True).start()
        except Exception as exc:
            print(f"[ui_server] Warning: Audio pipeline init failed: {exc}", file=sys.stderr)
            self.last_error = str(exc)

    def _calibrate_mic(self) -> None:
        if self.recorder:
            try:
                lvl = self.recorder.calibrate(seconds=0.8)
                print(f"[ui_server] Mic calibrated. Noise floor threshold: {lvl:.4f}")
                self.add_timeline("mic_ready", f"Microphone calibrated (threshold: {lvl:.4f})")
            except Exception as e:
                print(f"[ui_server] Calibration error: {e}")

    # -- WebSocket Broadcasting -------------------------------------------- #
    def broadcast_sync(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Thread-safe broadcast to all connected WebSocket clients."""
        payload = {"type": event_type, "timestamp": time.time(), **(data or {})}
        if self.loop and self.active_sockets:
            asyncio.run_coroutine_threadsafe(self._broadcast(payload), self.loop)

    async def _broadcast(self, payload: Dict[str, Any]) -> None:
        disconnected = []
        for ws in self.active_sockets:
            try:
                await ws.send_text(json.dumps(payload))
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            if ws in self.active_sockets:
                self.active_sockets.remove(ws)

    def set_state(self, new_state: str, extra: Optional[Dict[str, Any]] = None) -> None:
        self.state = new_state
        data = {"state": new_state, **(extra or {})}
        self.broadcast_sync("state_changed", data)

    def add_timeline(self, kind: str, message: str, meta: Optional[Dict[str, Any]] = None) -> None:
        entry = {
            "id": f"evt-{len(self.timeline) + 1}",
            "time": time.strftime("%H:%M:%S"),
            "kind": kind,
            "message": message,
            "meta": meta or {},
        }
        self.timeline.append(entry)
        if len(self.timeline) > 100:
            self.timeline.pop(0)
        self.broadcast_sync("timeline_item", {"entry": entry})

    # -- Audio Callbacks ---------------------------------------------------- #
    def _on_mic_meter(self, rms: float) -> None:
        # Scale to a normalised 0.0 - 1.0 representation for smooth orb reaction
        clamped = min(1.0, max(0.0, (rms - 0.005) * 25.0))
        self.broadcast_sync("mic_meter", {"rms": rms, "level": clamped})

    def _on_speech_start(self) -> None:
        if self.state in ("listening", "idle"):
            self.set_state("hearing")
            self.add_timeline("voice", "Speech detected")

    def _on_speech_end(self) -> None:
        if self.state == "hearing":
            self.set_state("processing")
            self.add_timeline("voice", "Speech segment completed, transcribing...")

    def _on_tts_state(self, tts_state: str, data: Dict[str, Any]) -> None:
        if tts_state == "speaking":
            self.set_state("speaking", data)
        elif tts_state == "idle" and self.state == "speaking":
            self.set_state("idle")

    # -- Confirmation Callback ---------------------------------------------- #
    def _ui_confirm_cb(self, command: str, shell: str) -> bool:
        mode = self.cfg.confirm_mode
        if mode == "auto":
            return True
        if mode == "deny":
            return False

        # Gather safety breakdown
        risk_info = assess_command_risk(command, cwd=self.toolbox.cwd)

        confirm_id = f"cmd-{uuid.uuid4().hex[:6]}"
        self._pending_confirm_id = confirm_id
        self._pending_confirm_event.clear()
        self._pending_confirm_result = False
        self._pending_confirm_data = {
            "id": confirm_id,
            "command": command,
            "shell": shell,
            **risk_info,
        }

        self.set_state("confirmation", self._pending_confirm_data)
        self.add_timeline("safety", f"Confirmation required for [{shell}]: {command}", risk_info)
        self.broadcast_sync("confirm_request", self._pending_confirm_data)

        # Spoken prompt if speech is enabled
        self.speaker.say("Confirmation required. May I run that command?", block=False)

        # Wait up to 60 seconds for user action in UI
        got_response = self._pending_confirm_event.wait(timeout=60.0)
        approved = self._pending_confirm_result if got_response else False

        self.broadcast_sync("confirm_resolved", {
            "id": confirm_id,
            "approved": approved,
            "timed_out": not got_response,
        })
        self._pending_confirm_id = None
        self._pending_confirm_data = {}

        if approved:
            self.add_timeline("safety", f"User approved: {command}")
        else:
            self.add_timeline("safety", f"User declined or timed out: {command}")

        return approved

    def resolve_confirmation(self, confirm_id: str, approved: bool) -> bool:
        if self._pending_confirm_id == confirm_id:
            self._pending_confirm_result = approved
            self._pending_confirm_event.set()
            return True
        return False

    def _process_audio_array(self, audio_arr: np.ndarray) -> None:
        """Process float32 16kHz audio array through Whisper and dispatch."""
        if self.stt is None:
            self.broadcast_sync("error", {"message": "Faster-Whisper STT is not ready."})
            return

        self.set_state("processing")
        self.add_timeline("voice", "Transcribing phone dictation...")
        t0 = time.monotonic()

        try:
            text = self.stt.transcribe(audio_arr)
            latency = time.monotonic() - t0
            if text and text.strip():
                print(f"[phone dictation] {text} ({len(audio_arr)/16000:.1f}s audio, {latency:.2f}s stt)")
                self.broadcast_sync("transcription_result", {"text": text, "latency": latency})
                self.add_timeline("voice", f"Dictation from phone: \"{text}\"")
                self.handle_utterance(text, latency_stt=latency)
            else:
                self.set_state("idle")
        except Exception as e:
            print(f"[ui_server] Error transcribing audio array: {e}")
            self.set_state("idle")

    def handle_mobile_audio(self, audio_bytes: bytes) -> None:
        """Transcribe audio bytes (WAV/WebM) streamed from a connected phone."""
        audio_arr = decode_mobile_audio(audio_bytes)
        if len(audio_arr) < 1600:
            self.set_state("idle")
            return
        self._process_audio_array(audio_arr)

    # -- Execution Pipeline ------------------------------------------------- #
    def handle_utterance(self, text: str, latency_stt: float = 0.0) -> None:
        """Processes a transcribed or typed user utterance through Ollama and Tools."""
        text = text.strip()
        if not text:
            self.set_state("idle")
            return

        t_start = time.monotonic()
        t_llm_start = 0.0
        t_llm_end = 0.0

        item: Dict[str, Any] = {
            "id": f"item-{uuid.uuid4().hex[:6]}",
            "time": time.strftime("%H:%M:%S"),
            "request": text,
            "reply": "",
            "tools": [],
            "status": "in_progress",
            "latency": {"stt": round(latency_stt, 3)},
        }

        # Check for commands like exit / clear
        normalised = text.lower().strip(" .!?,")
        if normalised in ("reset", "new chat", "clear history"):
            self.agent.reset()
            reply = "Conversation history cleared."
            item["reply"] = reply
            item["status"] = "success"
            self.history.append(item)
            self.broadcast_sync("history_cleared", {})
            self.speaker.say(reply)
            self.set_state("idle")
            return

        if self.cfg.wake_word:
            wake = self.cfg.wake_word.lower()
            if wake not in normalised:
                print(f"[ui_server] Ignored: wake word '{self.cfg.wake_word}' not found")
                self.set_state("idle")
                return
            text = normalised.split(wake, 1)[1].strip(" ,.") or text

        self.set_state("thinking", {"request": text})
        self.add_timeline("agent", f"Processing request: \"{text}\"")

        def on_tool(name: str, args: Dict[str, Any]) -> None:
            purpose = args.get("purpose", "")
            cmd = args.get("command", "")
            self.set_state("tool", {"tool": name, "command": cmd, "purpose": purpose})
            self.add_timeline("tool", f"Tool requested: {name} ({cmd or purpose})")

        def on_status(status_type: str, data: Dict[str, Any]) -> None:
            if status_type == "thinking":
                self.set_state("thinking", data)
            elif status_type == "tool_start":
                cmd = data.get("args", {}).get("command", "")
                self.set_state("executing", {"tool": data.get("name"), "command": cmd})
                self.broadcast_sync("tool_executing", data)
            elif status_type == "tool_result":
                self.broadcast_sync("tool_completed", data)
                item["tools"].append(data)

        try:
            t_llm_start = time.monotonic()
            reply = self.agent.ask(text, on_tool=on_tool, on_status=on_status)
            t_llm_end = time.monotonic()
        except Exception as exc:
            reply = f"Language model error: {exc}"
            self.last_error = str(exc)
            self.set_state("error", {"error": str(exc)})
            self.add_timeline("error", f"Model failure: {exc}")

        if not reply:
            reply = "I didn't get a response from the model."

        total_latency = time.monotonic() - t_start + latency_stt
        llm_latency = (t_llm_end - t_llm_start) if t_llm_start else 0.0

        item["reply"] = reply
        item["status"] = "success"
        item["latency"]["llm"] = round(llm_latency, 3)
        item["latency"]["total"] = round(total_latency, 3)

        self.history.append(item)
        if len(self.history) > 100:
            self.history.pop(0)

        self.broadcast_sync("agent_reply", {
            "item": item,
            "request": text,
            "reply": reply,
            "latency": item["latency"],
        })
        self.add_timeline("reply", f"Agent responded: \"{reply}\"")

        # Spoken output
        if self.cfg.tts_enabled:
            self.set_state("speaking", {"text": reply})
            self.speaker.say(reply, block=False)
        else:
            self.set_state("idle")

    # -- Background Listening Worker ---------------------------------------- #
    def start_listening_loop(self) -> None:
        if self._listen_active:
            return
        self._listen_active = True
        self._listen_thread = threading.Thread(target=self._run_listening_worker, daemon=True)
        self._listen_thread.start()

    def _run_listening_worker(self) -> None:
        print("[ui_server] Background voice listener started.")
        while self._listen_active:
            if not self.continuous_listening and self.state != "listening":
                time.sleep(0.1)
                continue

            if self.recorder is None or self.stt is None:
                time.sleep(0.5)
                continue

            # Wait if speaker is playing
            if self.speaker and not self.speaker._idle.is_set():
                time.sleep(0.1)
                continue

            self.set_state("listening")
            self.broadcast_sync("listen_started", {})

            try:
                audio = self.recorder.record_utterance()
            except Exception as e:
                print(f"[ui_server] record_utterance error: {e}")
                time.sleep(0.2)
                continue

            if audio is None:
                if not self.continuous_listening:
                    self.set_state("idle")
                continue

            # Transcribe
            self.set_state("processing")
            t0 = time.monotonic()
            try:
                text = self.stt.transcribe(audio)
            except Exception as e:
                text = ""
                print(f"[ui_server] Transcription error: {e}")

            stt_latency = time.monotonic() - t0
            if text:
                self.broadcast_sync("transcription_result", {
                    "text": text,
                    "duration": round(stt_latency, 3),
                    "audio_len": round(len(audio) / self.cfg.samplerate, 2),
                })
                self.handle_utterance(text, latency_stt=stt_latency)
            else:
                if not self.continuous_listening:
                    self.set_state("idle")

    def interrupt(self) -> None:
        """Immediately stop speaking, cancel recording, and reset to idle."""
        if self.speaker:
            self.speaker.interrupt()
        if self.recorder:
            self.recorder.cancel()
        if self._pending_confirm_event:
            self._pending_confirm_result = False
            self._pending_confirm_event.set()
        self.set_state("idle")
        self.add_timeline("user", "User issued interrupt/stop signal")
        self.broadcast_sync("interrupted", {})

    def get_system_status(self) -> Dict[str, Any]:
        """Provides status across all subsystems."""
        # Ollama check
        ollama_ok, ollama_msg = False, "unknown"
        installed_models: List[str] = []
        try:
            r = requests.get(f"{self.cfg.ollama_host.rstrip('/')}/api/tags", timeout=1.5)
            if r.status_code == 200:
                ollama_ok = True
                installed_models = [m.get("name", "") for m in r.json().get("models", [])]
                ollama_msg = "Connected"
            else:
                ollama_msg = f"HTTP {r.status_code}"
        except Exception as e:
            ollama_msg = f"Offline ({e})"

        # Voices
        voices_found = []
        voices_dir = self.cfg.piper_dir or os.path.join(BASE_DIR, "voices")
        if os.path.isdir(voices_dir):
            voices_found = [f for f in os.listdir(voices_dir) if f.endswith(".onnx")]

        return {
            "status": "ready" if ollama_ok else "warning",
            "state": self.state,
            "local_ai": True,
            "ollama": {
                "online": ollama_ok,
                "host": self.cfg.ollama_host,
                "current_model": self.cfg.model,
                "available_models": installed_models,
                "message": ollama_msg,
            },
            "whisper": {
                "model": self.cfg.whisper_model,
                "device": self.cfg.whisper_device,
                "compute": self.cfg.whisper_compute,
                "ready": self.stt is not None,
            },
            "tts": {
                "backend": self.cfg.tts_backend,
                "active_backend": getattr(self.speaker, "backend_name", self.cfg.tts_backend),
                "voice": self.cfg.tts_voice or self.cfg.edge_voice,
                "rate": self.cfg.tts_rate,
                "enabled": self.cfg.tts_enabled,
                "piper_voices": voices_found,
            },
            "microphone": {
                "device_index": self.cfg.input_device,
                "energy_floor": self.cfg.energy_floor,
                "threshold": getattr(self.recorder, "threshold", self.cfg.energy_floor),
                "ready": self.recorder is not None,
            },
            "safety": {
                "confirm_mode": self.cfg.confirm_mode,
                "default_shell": self.cfg.default_shell,
                "working_dir": self.toolbox.cwd,
            },
            "continuous_listening": self.continuous_listening,
        }


# Global Manager Instance
manager: Optional[AgentUIManager] = None


# --------------------------------------------------------------------------- #
# REST Endpoints
# --------------------------------------------------------------------------- #
@app.get("/api/status")
def get_status() -> JSONResponse:
    if manager is None:
        raise HTTPException(status_code=503, detail="Manager not initialized")
    return JSONResponse(content=manager.get_system_status())


@app.get("/api/models")
def get_models() -> JSONResponse:
    if manager is None:
        raise HTTPException(status_code=503, detail="Manager not initialized")
    models = []
    try:
        r = requests.get(f"{manager.cfg.ollama_host.rstrip('/')}/api/tags", timeout=2.0)
        if r.status_code == 200:
            for item in r.json().get("models", []):
                models.append({
                    "name": item.get("name", ""),
                    "size": item.get("size", 0),
                    "parameter_size": item.get("details", {}).get("parameter_size", ""),
                })
    except Exception as e:
        print(f"[ui_server] Could not fetch models: {e}")
    return JSONResponse(content={"models": models, "current": manager.cfg.model})


@app.get("/api/voices")
def get_voices() -> JSONResponse:
    if manager is None:
        raise HTTPException(status_code=503, detail="Manager not initialized")
    return JSONResponse(content={"voices": list_voices(manager.cfg)})


@app.get("/api/devices")
def get_devices() -> JSONResponse:
    import sounddevice as sd
    devices = []
    try:
        devs = sd.query_devices()
        for idx, dev in enumerate(devs):
            if dev.get("max_input_channels", 0) > 0:
                devices.append({
                    "index": idx,
                    "name": dev.get("name", f"Device {idx}"),
                    "channels": dev.get("max_input_channels"),
                    "samplerate": dev.get("default_samplerate"),
                })
    except Exception as e:
        print(f"[ui_server] Devices query failed: {e}")
    return JSONResponse(content={"devices": devices, "current": manager.cfg.input_device})


@app.post("/api/query")
async def post_query(payload: Dict[str, Any]) -> JSONResponse:
    if manager is None:
        raise HTTPException(status_code=503, detail="Manager not initialized")
    text = payload.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty text")

    # Run in background thread so HTTP response returns immediately
    threading.Thread(target=manager.handle_utterance, args=(text,), daemon=True).start()
    return JSONResponse(content={"status": "processing", "query": text})


@app.post("/api/confirm")
def post_confirm(payload: Dict[str, Any]) -> JSONResponse:
    if manager is None:
        raise HTTPException(status_code=503, detail="Manager not initialized")
    confirm_id = payload.get("id", "")
    approved = bool(payload.get("approved", False))
    success = manager.resolve_confirmation(confirm_id, approved)
    return JSONResponse(content={"success": success, "approved": approved})


@app.post("/api/interrupt")
def post_interrupt() -> JSONResponse:
    if manager is None:
        raise HTTPException(status_code=503, detail="Manager not initialized")
    manager.interrupt()
    return JSONResponse(content={"status": "interrupted"})


@app.post("/api/settings")
def post_settings(payload: Dict[str, Any]) -> JSONResponse:
    if manager is None:
        raise HTTPException(status_code=503, detail="Manager not initialized")
    cfg = manager.cfg
    if "model" in payload:
        cfg.model = str(payload["model"])
    if "tts_voice" in payload:
        cfg.tts_voice = str(payload["tts_voice"])
    if "tts_backend" in payload:
        cfg.tts_backend = str(payload["tts_backend"])
        # Recreate speaker
        manager.speaker.close()
        manager.speaker = Speaker(cfg, on_state=manager._on_tts_state)
    if "tts_rate" in payload:
        cfg.tts_rate = int(payload["tts_rate"])
    if "confirm_mode" in payload:
        cfg.confirm_mode = str(payload["confirm_mode"])
    if "default_shell" in payload:
        cfg.default_shell = str(payload["default_shell"])
    if "input_device" in payload:
        dev = payload["input_device"]
        cfg.input_device = int(dev) if dev is not None and int(dev) >= 0 else None
        manager.recorder = Recorder(
            cfg,
            on_meter=manager._on_mic_meter,
            on_speech_start=manager._on_speech_start,
            on_speech_end=manager._on_speech_end,
        )
    if "continuous_listening" in payload:
        manager.continuous_listening = bool(payload["continuous_listening"])

    manager.broadcast_sync("settings_updated", manager.get_system_status())
    return JSONResponse(content={"status": "updated", "config": manager.get_system_status()})


@app.post("/api/test-voice")
def post_test_voice(payload: Dict[str, Any]) -> JSONResponse:
    if manager is None:
        raise HTTPException(status_code=503, detail="Manager not initialized")
    text = payload.get("text") or "Hello. System online and voice agent operational."
    voice = payload.get("voice")
    backend = payload.get("backend")

    def _speak_test() -> None:
        if voice or backend:
            import copy
            trial_cfg = copy.copy(manager.cfg)
            if voice:
                trial_cfg.tts_voice = voice
            if backend:
                trial_cfg.tts_backend = backend
            s = Speaker(trial_cfg)
            try:
                s.say(text, block=True)
            finally:
                s.close()
        else:
            manager.speaker.say(text, block=True)

    threading.Thread(target=_speak_test, daemon=True).start()
    return JSONResponse(content={"status": "speaking", "sample": text})


@app.get("/api/network-info")
def get_network_info() -> JSONResponse:
    ip = get_local_ip()
    port = manager.cfg.ui_port if manager else 8000
    protocol = "https" if (manager and manager.cfg.ui_ssl) else "http"
    return JSONResponse(content={
        "local_ip": ip,
        "port": port,
        "protocol": protocol,
        "url": f"{protocol}://{ip}:{port}",
        "hostname": socket.gethostname(),
        "ssl_enabled": manager.cfg.ui_ssl if manager else False,
    })


@app.get("/api/screen/frame")
def get_screen_frame(quality: int = 70, scale: float = 0.8) -> Response:
    """Returns a single snapshot JPEG frame of the primary laptop screen."""
    try:
        streamer = ScreenStreamer()
        frame = streamer.grab_frame_jpeg(quality=quality, scale=scale)
        return Response(content=frame, media_type="image/jpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Screen capture failed: {e}")


@app.get("/api/screen/stream")
async def get_screen_stream(quality: int = 60, scale: float = 0.75, fps: int = 20):
    """High-speed MJPEG screen mirror video stream for phone browser."""
    streamer = ScreenStreamer()
    delay = 1.0 / max(5, min(30, fps))

    async def _stream():
        while True:
            try:
                frame = streamer.grab_frame_jpeg(quality=quality, scale=scale)
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
                )
                await asyncio.sleep(delay)
            except Exception:
                await asyncio.sleep(0.1)

    return StreamingResponse(_stream(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.post("/api/screen/click")
def post_screen_click(payload: Dict[str, Any]) -> JSONResponse:
    """Remote mouse click simulation for tapping on phone screen mirror."""
    x_norm = float(payload.get("x", 0))
    y_norm = float(payload.get("y", 0))
    button = str(payload.get("button", "left")).lower()

    try:
        user32 = ctypes.windll.user32
        screen_w = user32.GetSystemMetrics(0)
        screen_h = user32.GetSystemMetrics(1)

        target_x = max(0, min(screen_w - 1, int(x_norm * screen_w)))
        target_y = max(0, min(screen_h - 1, int(y_norm * screen_h)))

        user32.SetCursorPos(target_x, target_y)
        if button == "left":
            user32.mouse_event(0x0002, 0, 0, 0, 0)
            user32.mouse_event(0x0004, 0, 0, 0, 0)
        elif button == "right":
            user32.mouse_event(0x0008, 0, 0, 0, 0)
            user32.mouse_event(0x0010, 0, 0, 0, 0)
        elif button == "double":
            user32.mouse_event(0x0002, 0, 0, 0, 0)
            user32.mouse_event(0x0004, 0, 0, 0, 0)
            time.sleep(0.04)
            user32.mouse_event(0x0002, 0, 0, 0, 0)
            user32.mouse_event(0x0004, 0, 0, 0, 0)

        return JSONResponse(content={"status": "ok", "x": target_x, "y": target_y})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Click failed: {e}")


@app.post("/api/audio/transcribe")
async def post_audio_transcribe(payload: Dict[str, Any]) -> JSONResponse:
    """Receives audio blob (base64) from phone mic and transcribes via Whisper."""
    if manager is None:
        raise HTTPException(status_code=503, detail="Manager not initialized")
    raw_b64 = payload.get("audio", "")
    if not raw_b64:
        raise HTTPException(status_code=400, detail="No audio data provided")

    if "," in raw_b64:
        raw_b64 = raw_b64.split(",", 1)[1]

    audio_bytes = base64.b64decode(raw_b64)
    threading.Thread(target=manager.handle_mobile_audio, args=(audio_bytes,), daemon=True).start()
    return JSONResponse(content={"status": "received"})


# --------------------------------------------------------------------------- #
# WebRTC 60 FPS Low-Latency Peer Connection Manager
# --------------------------------------------------------------------------- #
webrtc_pcs: Set[RTCPeerConnection] = set()


async def handle_incoming_webrtc_audio(track, mgr: AgentUIManager) -> None:
    """Stream and buffer live Opus audio from mobile WebRTC microphone."""
    resampler = av.AudioResampler(format="fltp", layout="mono", rate=16000)
    audio_buffer: List[np.ndarray] = []
    silence_count = 0
    is_speaking = False

    while True:
        try:
            frame = await track.recv()
            resampled_frames = resampler.resample(frame)
            for rf in resampled_frames:
                pcm = rf.to_ndarray().flatten()
                if len(pcm) == 0:
                    continue
                rms = float(np.sqrt(np.mean(pcm**2)))
                mgr._on_mic_meter(rms)

                # Voice Activity Detection (VAD)
                if rms > 0.015:
                    if not is_speaking:
                        is_speaking = True
                        mgr.set_state("hearing")
                        mgr.add_timeline("voice", "Mobile microphone speech detected")
                    silence_count = 0
                    audio_buffer.append(pcm)
                elif is_speaking:
                    audio_buffer.append(pcm)
                    silence_count += 1
                    # ~0.55s silence marks utterance boundary
                    if silence_count > 28:
                        is_speaking = False
                        full_pcm = np.concatenate(audio_buffer)
                        audio_buffer = []
                        if len(full_pcm) > 8000:
                            threading.Thread(
                                target=mgr._process_audio_array,
                                args=(full_pcm,),
                                daemon=True,
                            ).start()
        except Exception:
            break


@app.post("/api/webrtc/offer")
async def post_webrtc_offer(payload: Dict[str, Any]) -> JSONResponse:
    """Establishes 60 FPS WebRTC screen stream & 2-way audio with phone browser."""
    if manager is None:
        raise HTTPException(status_code=503, detail="Manager not initialized")

    offer = RTCSessionDescription(sdp=payload["sdp"], type=payload["type"])
    pc = RTCPeerConnection()
    webrtc_pcs.add(pc)

    video_track = ScreenVideoStreamTrack(fps=60)
    pc.addTrack(video_track)

    @pc.on("datachannel")
    def on_datachannel(channel):
        @channel.on("message")
        def on_message(message):
            try:
                data = json.loads(message)
                mtype = data.get("type")
                if mtype == "click":
                    x_norm = float(data.get("x", 0))
                    y_norm = float(data.get("y", 0))
                    btn = str(data.get("button", "left")).lower()
                    user32 = ctypes.windll.user32
                    sw = user32.GetSystemMetrics(0)
                    sh = user32.GetSystemMetrics(1)
                    tx = max(0, min(sw - 1, int(x_norm * sw)))
                    ty = max(0, min(sh - 1, int(y_norm * sh)))
                    user32.SetCursorPos(tx, ty)
                    if btn == "left":
                        user32.mouse_event(0x0002, 0, 0, 0, 0)
                        user32.mouse_event(0x0004, 0, 0, 0, 0)
                    elif btn == "right":
                        user32.mouse_event(0x0008, 0, 0, 0, 0)
                        user32.mouse_event(0x0010, 0, 0, 0, 0)
                    elif btn == "double":
                        user32.mouse_event(0x0002, 0, 0, 0, 0)
                        user32.mouse_event(0x0004, 0, 0, 0, 0)
                        time.sleep(0.04)
                        user32.mouse_event(0x0002, 0, 0, 0, 0)
                        user32.mouse_event(0x0004, 0, 0, 0, 0)
            except Exception:
                pass

    @pc.on("track")
    def on_track(track):
        if track.kind == "audio":
            print("[WebRTC] Receiving live 60 FPS microphone stream from phone!")
            asyncio.create_task(handle_incoming_webrtc_audio(track, manager))

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        if pc.connectionState in ("failed", "closed"):
            video_track.stop()
            await pc.close()
            webrtc_pcs.discard(pc)

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return JSONResponse(content={
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type,
    })


# --------------------------------------------------------------------------- #
# WebSocket Handler
# --------------------------------------------------------------------------- #
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    if manager is None:
        await websocket.close()
        return

    manager.loop = asyncio.get_running_loop()
    manager.active_sockets.append(websocket)

    local_ip = get_local_ip()
    # Send initial state snapshot with network info
    await websocket.send_text(json.dumps({
        "type": "init",
        "system": manager.get_system_status(),
        "history": manager.history,
        "timeline": manager.timeline[-20:],
        "state": manager.state,
        "network": {
            "local_ip": local_ip,
            "port": manager.cfg.ui_port,
            "protocol": "https" if manager.cfg.ui_ssl else "http",
            "url": f"{'https' if manager.cfg.ui_ssl else 'http'}://{local_ip}:{manager.cfg.ui_port}",
        },
    }))

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type")
            if msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

            elif msg_type == "start_listening":
                if manager.state in ("idle", "success", "error"):
                    manager.set_state("listening")
                    manager.broadcast_sync("listen_started", {})

            elif msg_type == "stop_listening":
                if manager.recorder:
                    manager.recorder.cancel()
                manager.set_state("idle")

            elif msg_type == "toggle_listening":
                if manager.state == "listening":
                    if manager.recorder:
                        manager.recorder.cancel()
                    manager.set_state("idle")
                else:
                    manager.set_state("listening")
                    manager.broadcast_sync("listen_started", {})

            elif msg_type == "toggle_continuous":
                manager.continuous_listening = not manager.continuous_listening
                manager.broadcast_sync("continuous_changed", {
                    "enabled": manager.continuous_listening,
                })

            elif msg_type == "stop" or msg_type == "interrupt":
                manager.interrupt()

            elif msg_type == "send_text":
                text = msg.get("text", "").strip()
                if text:
                    threading.Thread(
                        target=manager.handle_utterance,
                        args=(text,),
                        daemon=True,
                    ).start()

            elif msg_type == "mobile_audio" or msg_type == "audio_data":
                raw_b64 = msg.get("audio", "")
                if raw_b64:
                    if "," in raw_b64:
                        raw_b64 = raw_b64.split(",", 1)[1]
                    audio_bytes = base64.b64decode(raw_b64)
                    threading.Thread(
                        target=manager.handle_mobile_audio,
                        args=(audio_bytes,),
                        daemon=True,
                    ).start()

            elif msg_type == "screen_click":
                x_norm = float(msg.get("x", 0))
                y_norm = float(msg.get("y", 0))
                btn = str(msg.get("button", "left")).lower()
                try:
                    user32 = ctypes.windll.user32
                    screen_w = user32.GetSystemMetrics(0)
                    screen_h = user32.GetSystemMetrics(1)
                    tx = max(0, min(screen_w - 1, int(x_norm * screen_w)))
                    ty = max(0, min(screen_h - 1, int(y_norm * screen_h)))
                    user32.SetCursorPos(tx, ty)
                    if btn == "left":
                        user32.mouse_event(0x0002, 0, 0, 0, 0)
                        user32.mouse_event(0x0004, 0, 0, 0, 0)
                    elif btn == "right":
                        user32.mouse_event(0x0008, 0, 0, 0, 0)
                        user32.mouse_event(0x0010, 0, 0, 0, 0)
                except Exception:
                    pass

            elif msg_type == "confirm_response":
                cid = msg.get("id", "")
                approved = bool(msg.get("approved", False))
                manager.resolve_confirmation(cid, approved)

            elif msg_type == "clear_history":
                manager.history.clear()
                manager.agent.reset()
                manager.broadcast_sync("history_cleared", {})

            elif msg_type == "get_status":
                await websocket.send_text(json.dumps({
                    "type": "status_update",
                    "system": manager.get_system_status(),
                }))

    except WebSocketDisconnect:
        if websocket in manager.active_sockets:
            manager.active_sockets.remove(websocket)
    except Exception as exc:
        print(f"[ui_server] WebSocket connection closed: {exc}")
        if websocket in manager.active_sockets:
            manager.active_sockets.remove(websocket)


# --------------------------------------------------------------------------- #
# Static Files & UI Serving
# --------------------------------------------------------------------------- #
if os.path.isdir(UI_DIR):
    app.mount("/static", StaticFiles(directory=UI_DIR), name="static")


@app.get("/")
def serve_root() -> FileResponse:
    index_path = os.path.join(UI_DIR, "index.html")
    if not os.path.isfile(index_path):
        raise HTTPException(status_code=404, detail="UI index.html not found")
    return FileResponse(index_path)


# --------------------------------------------------------------------------- #
# Runner Entrypoint
# --------------------------------------------------------------------------- #
def run_server(cfg: Config, auto_open: bool = True) -> None:
    global manager
    manager = AgentUIManager(cfg)
    manager.start_listening_loop()

    local_ip = get_local_ip()
    protocol = "https" if cfg.ui_ssl else "http"
    url_local = f"{protocol}://localhost:{cfg.ui_port}"
    url_phone = f"{protocol}://{local_ip}:{cfg.ui_port}"
    print(f"\n=======================================================")
    print(f"  VOICE AGENT COMMAND CENTER & REMOTE CONTROLLER")
    print(f"  💻 Laptop Display:  {url_local}")
    print(f"  📱 Phone / Mobile:  {url_phone}")
    print(f"  🔒 Security:        {'HTTPS (Phone Mic & 60 FPS WebRTC Enabled)' if cfg.ui_ssl else 'HTTP'}")
    print(f"  Local AI: {cfg.model} @ {cfg.ollama_host}")
    print(f"  Voice: {cfg.tts_backend} ({cfg.tts_voice or 'default'})")
    print(f"=======================================================\n")

    ssl_certfile = None
    ssl_keyfile = None
    if cfg.ui_ssl:
        cert_path = os.path.join(BASE_DIR, cfg.ssl_cert)
        key_path = os.path.join(BASE_DIR, cfg.ssl_key)
        if not (os.path.isfile(cert_path) and os.path.isfile(key_path)):
            print("[ui_server] Generating self-signed SSL certificate for phone microphone access...")
            generate_self_signed_cert(cert_path, key_path, local_ip)
        ssl_certfile = cert_path
        ssl_keyfile = key_path

    if auto_open:
        def _open() -> None:
            time.sleep(1.2)
            # Try launching in Edge App Mode for native desktop window feel
            import subprocess
            edge_paths = [
                os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
                os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
            ]
            launched = False
            for ep in edge_paths:
                if os.path.isfile(ep):
                    try:
                        subprocess.Popen([ep, f"--app={url_local}", "--ignore-certificate-errors"])
                        launched = True
                        break
                    except Exception:
                        pass
            if not launched:
                webbrowser.open(url_local)

        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(
        app,
        host=cfg.ui_host,
        port=cfg.ui_port,
        ssl_certfile=ssl_certfile,
        ssl_keyfile=ssl_keyfile,
        log_level="warning",
    )


if __name__ == "__main__":
    from config import Config
    cfg = Config()
    run_server(cfg)
