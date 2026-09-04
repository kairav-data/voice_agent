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
import re
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

# --------------------------------------------------------------------------- #
# Windows asyncio ProactorBasePipeTransport 10054 ConnectionReset fix & DPI
# --------------------------------------------------------------------------- #
if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor DPI aware (100% full screen resolution)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    try:
        from asyncio.proactor_events import _ProactorBasePipeTransport
        _orig_call_connection_lost = _ProactorBasePipeTransport._call_connection_lost

        def _safe_call_connection_lost(self, exc):
            try:
                if hasattr(self, "_sock") and self._sock is not None:
                    _s = getattr(self._sock, "shutdown", None)
                    if _s:
                        def _safe_shutdown(*args, **kwargs):
                            try:
                                return _s(*args, **kwargs)
                            except (ConnectionResetError, ConnectionAbortedError, OSError):
                                pass
                        self._sock.shutdown = _safe_shutdown
                _orig_call_connection_lost(self, exc)
            except Exception:
                pass

        _ProactorBasePipeTransport._call_connection_lost = _safe_call_connection_lost
    except Exception:
        pass


def _suppress_win_errors_handler(loop: asyncio.AbstractEventLoop, context: Dict[str, Any]) -> None:
    exc = context.get("exception")
    if isinstance(exc, (ConnectionResetError, ConnectionAbortedError, ConnectionError)):
        return
    if isinstance(exc, OSError) and getattr(exc, "winerror", None) in (10054, 10053, 10038):
        return
    msg = str(context.get("message", ""))
    if "10054" in msg or "10053" in msg or "forcibly closed" in msg:
        return
    try:
        loop.default_exception_handler(context)
    except Exception:
        pass


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
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

        self.user32 = ctypes.windll.user32
        self.gdi32 = ctypes.windll.gdi32

        # Attach to interactive Windows desktop station
        try:
            hWinsta = self.user32.OpenWindowStationW("winsta0", False, 0x10000000)
            if hWinsta:
                self.user32.SetProcessWindowStation(hWinsta)
            hDesk = self.user32.OpenDesktopW("default", 0, False, 0x10000000)
            if hDesk:
                self.user32.SetThreadDesktop(hDesk)
        except Exception:
            pass

        self.w = self.user32.GetSystemMetrics(0)
        self.h = self.user32.GetSystemMetrics(1)
        if not self.w or not self.h:
            self.w, self.h = 1920, 1080

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

    def grab_frame_jpeg(self, quality: int = 70, scale: float = 1.0) -> bytes:
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
        self.socket_queues: Dict[WebSocket, asyncio.Queue] = {}
        self.socket_clients: Dict[WebSocket, str] = {}
        self._sockets_lock = threading.Lock()
        self._last_meter_time = 0.0
        self._latest_reply_audio: Optional[bytes] = None
        self._active_source: str = "laptop"

        # Current State
        self.state = "idle"  # idle | listening | hearing | processing | thinking | tool | confirmation | executing | speaking | success | error
        self.last_error = ""
        self.continuous_listening = getattr(self.cfg, "continuous_listening", False)
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
        """Thread-safe broadcast to all connected WebSocket clients via pre-serialized JSON."""
        if not self.loop:
            return
        with self._sockets_lock:
            if not self.active_sockets:
                return

        try:
            payload = {"type": event_type, "timestamp": time.time()}
            if data:
                payload.update(data)
            payload_str = json.dumps(payload)
        except Exception:
            return

        try:
            asyncio.run_coroutine_threadsafe(self._broadcast_str(payload_str), self.loop)
        except Exception:
            pass

    async def _broadcast_str(self, payload_str: str) -> None:
        with self._sockets_lock:
            sockets = list(self.active_sockets)

        is_meter = payload_str.startswith('{"type": "mic_meter"')
        for ws in sockets:
            q = self.socket_queues.get(ws)
            if q is not None:
                try:
                    # For high-frequency meter updates, drop frame if queue already has pending items
                    if is_meter and q.qsize() > 2:
                        continue
                    if q.full():
                        try:
                            q.get_nowait()
                        except (asyncio.QueueEmpty, Exception):
                            pass
                    q.put_nowait(payload_str)
                except Exception:
                    pass

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
        # Rate-limit to max ~30 FPS to prevent WebSocket event flood
        now = time.monotonic()
        if now - self._last_meter_time < 0.033:
            return
        self._last_meter_time = now

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
        # Audio routing for confirmation prompt
        target = (self.cfg.tts_speaker_target or "auto").lower()
        active_src = getattr(self, "_active_source", "laptop")
        play_laptop_confirm = (target == "laptop") or (target == "both") or (target == "auto" and active_src != "phone")
        play_phone_confirm = (target == "phone") or (target == "both") or (target == "auto" and active_src == "phone")

        if play_phone_confirm and self.cfg.tts_enabled:
            wav_tuple = self.speaker.synth_wav_bytes("Confirmation required. May I run that command?")
            if wav_tuple:
                b64_wav = base64.b64encode(wav_tuple[0]).decode("ascii")
                self._pending_confirm_data["audio"] = f"data:audio/wav;base64,{b64_wav}"

        self.broadcast_sync("confirm_request", self._pending_confirm_data)

        # Spoken prompt on laptop speakers only if targeted
        if play_laptop_confirm and self.cfg.tts_enabled:
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

    def _process_audio_array(self, audio_arr: np.ndarray, source: str = "phone") -> None:
        """Process float32 16kHz audio array through Whisper and dispatch."""
        if self.stt is None:
            self.broadcast_sync("error", {"message": "Faster-Whisper STT is not ready."})
            return

        self.set_state("processing")
        self.add_timeline("voice", f"Transcribing {source} dictation...")
        t0 = time.monotonic()

        try:
            text = self.stt.transcribe(audio_arr)
            latency = time.monotonic() - t0
            if text and text.strip():
                print(f"[{source} dictation] {text} ({len(audio_arr)/16000:.1f}s audio, {latency:.2f}s stt)")
                self.broadcast_sync("transcription_result", {"text": text, "latency": latency, "source": source})
                self.add_timeline("voice", f"Dictation from {source}: \"{text}\"")
                self.handle_utterance(text, latency_stt=latency, source=source)
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
        self._process_audio_array(audio_arr, source="phone")

    # -- Execution Pipeline ------------------------------------------------- #
    def handle_utterance(self, text: str, latency_stt: float = 0.0, source: str = "laptop") -> None:
        """Processes a transcribed or typed user utterance through Ollama and Tools."""
        self._active_source = source
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
            self._dispatch_reply_audio(reply, source=source, item=item, request_text=text)
            return

        if self.cfg.wake_word:
            wake = self.cfg.wake_word.lower()
            if wake not in normalised:
                print(f"[ui_server] Ignored: wake word '{self.cfg.wake_word}' not found")
                self.set_state("idle")
                return
            text = normalised.split(wake, 1)[1].strip(" ,.") or text
            normalised = text.lower().strip(" .!?,")

        # -------------------------------------------------------------------
        # Fast-Path Direct Intent Recognition (<50ms execution)
        # -------------------------------------------------------------------
        # 1. Direct Page Scrolling
        if normalised in ("scroll down", "scroll down please", "please scroll down", "scroll page down", "page down", "scroll more"):
            call_res = json.loads(self.toolbox.call("scroll_page", {"direction": "down", "amount": "medium"}))
            reply = "Scrolled down."
            item["reply"] = reply
            item["status"] = "success"
            item["tools"].append({"name": "scroll_page", "args": {"direction": "down"}, "result": call_res})
            self.history.append(item)
            self._dispatch_reply_audio(reply, source=source, item=item, request_text=text)
            return
        elif normalised in ("scroll up", "scroll up please", "please scroll up", "scroll page up", "page up"):
            call_res = json.loads(self.toolbox.call("scroll_page", {"direction": "up", "amount": "medium"}))
            reply = "Scrolled up."
            item["reply"] = reply
            item["status"] = "success"
            item["tools"].append({"name": "scroll_page", "args": {"direction": "up"}, "result": call_res})
            self.history.append(item)
            self._dispatch_reply_audio(reply, source=source, item=item, request_text=text)
            return
        elif normalised in ("scroll to top", "scroll to the top", "go to top", "top of page"):
            call_res = json.loads(self.toolbox.call("scroll_page", {"direction": "top"}))
            reply = "Scrolled to the top."
            item["reply"] = reply
            item["status"] = "success"
            item["tools"].append({"name": "scroll_page", "args": {"direction": "top"}, "result": call_res})
            self.history.append(item)
            self._dispatch_reply_audio(reply, source=source, item=item, request_text=text)
            return
        elif normalised in ("scroll to bottom", "scroll to the bottom", "go to bottom", "bottom of page"):
            call_res = json.loads(self.toolbox.call("scroll_page", {"direction": "bottom"}))
            reply = "Scrolled to the bottom."
            item["reply"] = reply
            item["status"] = "success"
            item["tools"].append({"name": "scroll_page", "args": {"direction": "bottom"}, "result": call_res})
            self.history.append(item)
            self._dispatch_reply_audio(reply, source=source, item=item, request_text=text)
            return

        # 2. Media Controls
        if normalised in ("pause", "pause video", "pause the video", "pause music", "stop video", "stop music"):
            call_res = json.loads(self.toolbox.call("control_media", {"action": "play_pause"}))
            reply = "Paused playback."
            item["reply"] = reply
            item["status"] = "success"
            item["tools"].append({"name": "control_media", "args": {"action": "play_pause"}, "result": call_res})
            self.history.append(item)
            self._dispatch_reply_audio(reply, source=source, item=item, request_text=text)
            return
        elif normalised in ("resume", "resume video", "play video", "unpause", "unpause video", "resume music"):
            call_res = json.loads(self.toolbox.call("control_media", {"action": "play_pause"}))
            reply = "Resumed playback."
            item["reply"] = reply
            item["status"] = "success"
            item["tools"].append({"name": "control_media", "args": {"action": "play_pause"}, "result": call_res})
            self.history.append(item)
            self._dispatch_reply_audio(reply, source=source, item=item, request_text=text)
            return
        elif normalised in ("mute", "mute video", "mute audio", "unmute", "unmute video"):
            call_res = json.loads(self.toolbox.call("control_media", {"action": "mute"}))
            reply = "Mute toggled."
            item["reply"] = reply
            item["status"] = "success"
            item["tools"].append({"name": "control_media", "args": {"action": "mute"}, "result": call_res})
            self.history.append(item)
            self._dispatch_reply_audio(reply, source=source, item=item, request_text=text)
            return
        elif normalised in ("fullscreen", "full screen", "exit fullscreen", "toggle fullscreen"):
            call_res = json.loads(self.toolbox.call("control_media", {"action": "fullscreen"}))
            reply = "Fullscreen toggled."
            item["reply"] = reply
            item["status"] = "success"
            item["tools"].append({"name": "control_media", "args": {"action": "fullscreen"}, "result": call_res})
            self.history.append(item)
            self._dispatch_reply_audio(reply, source=source, item=item, request_text=text)
            return

        # 3. Direct YouTube Video Play
        # Handles e.g. "play bohemian rhapsody on youtube", "play interstellar soundtrack", "play lofi hip hop"
        yt_match = re.match(r"^(?:please\s+)?(?:play|search and play)\s+(.+?)(?:\s+on\s+youtube|\s+in\s+youtube)?$", normalised)
        if yt_match and not any(k in normalised for k in ("game", "with", "around")):
            target_video = yt_match.group(1).strip()
            if target_video not in ("video", "the video", "music", "the music"):
                self.set_state("thinking", {"request": text})
                self.add_timeline("agent", f"Searching YouTube for \"{target_video}\"")
                call_res = json.loads(self.toolbox.call("play_youtube_video", {"query": target_video, "autoplay": True}))
                reply = f"Playing {target_video} on YouTube."
                item["reply"] = reply
                item["status"] = "success"
                item["tools"].append({"name": "play_youtube_video", "args": {"query": target_video}, "result": call_res})
                self.history.append(item)
                self._dispatch_reply_audio(reply, source=source, item=item, request_text=text)
                return

        # 4. Direct Open Web App
        # Handles e.g. "open youtube", "open spotify", "open netflix", "open github", "open gmail"
        open_match = re.match(r"^(?:please\s+)?(?:open|launch|go to)\s+([a-zA-Z0-9_\-\.\s]+)$", normalised)
        if open_match:
            app_target = open_match.group(1).strip()
            from tools import WEB_APPS
            if app_target.lower() in WEB_APPS or "." in app_target:
                self.set_state("thinking", {"request": text})
                self.add_timeline("agent", f"Opening web app \"{app_target}\"")
                call_res = json.loads(self.toolbox.call("open_web_app", {"app_name_or_url": app_target}))
                reply = f"Opening {app_target}."
                item["reply"] = reply
                item["status"] = "success"
                item["tools"].append({"name": "open_web_app", "args": {"app_name_or_url": app_target}, "result": call_res})
                self.history.append(item)
                self._dispatch_reply_audio(reply, source=source, item=item, request_text=text)
                return

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

        self._dispatch_reply_audio(reply, source=source, item=item, request_text=text)

    def _dispatch_reply_audio(
        self,
        reply: str,
        source: str = "laptop",
        item: Optional[Dict[str, Any]] = None,
        request_text: str = "",
    ) -> None:
        """Routes spoken reply audio strictly to phone speaker, laptop speaker, or both."""
        audio_data_url = None
        target = (self.cfg.tts_speaker_target or "auto").lower()

        # Decide whether to play on laptop speakers or on client (phone)
        if target == "phone":
            play_on_laptop = False
            play_on_phone = True
            resolved_target = "phone"
        elif target == "laptop":
            play_on_laptop = True
            play_on_phone = False
            resolved_target = "laptop"
        elif target == "both":
            play_on_laptop = True
            play_on_phone = True
            resolved_target = "both"
        else:  # "auto": respond on the device where instruction originated
            if str(source).lower() in ("phone", "mobile", "webrtc_phone"):
                play_on_laptop = False
                play_on_phone = True
                resolved_target = "phone"
            else:
                play_on_laptop = True
                play_on_phone = False
                resolved_target = "laptop"

        if self.cfg.tts_enabled:
            # Synthesize in-memory WAV bytes ONLY when targeting phone speaker
            if play_on_phone:
                wav_tuple = self.speaker.synth_wav_bytes(reply)
                if wav_tuple:
                    wav_bytes, _ = wav_tuple
                    b64_wav = base64.b64encode(wav_bytes).decode("ascii")
                    audio_data_url = f"data:audio/wav;base64,{b64_wav}"
                    self._latest_reply_audio = wav_bytes
            else:
                self._latest_reply_audio = None

        # Broadcast reply with audio data URL to clients
        self.broadcast_sync("agent_reply", {
            "item": item or {},
            "request": request_text,
            "reply": reply,
            "latency": item.get("latency", {}) if item else {},
            "source": source,
            "target_device": resolved_target,
            "audio": audio_data_url if play_on_phone else None,
            "audio_url": f"/api/tts/latest?t={int(time.time()*1000)}" if (audio_data_url and play_on_phone) else None,
            "play_on_client": play_on_phone,
            "play_on_laptop": play_on_laptop,
        })
        self.add_timeline("reply", f"Agent responded ({resolved_target}): \"{reply}\"")

        # Spoken output
        if self.cfg.tts_enabled:
            if play_on_laptop:
                self.set_state("speaking", {"text": reply, "target": "laptop"})
                self.speaker.say(reply, block=False)
            else:
                # Spoken audio is playing on phone speaker; set visual state
                self.set_state("speaking", {"text": reply, "target": "phone"})
                word_count = len(reply.split())
                est_sec = max(1.5, word_count / 2.8)
                def _return_idle():
                    time.sleep(est_sec)
                    if self.state == "speaking":
                        self.set_state("idle")
                threading.Thread(target=_return_idle, daemon=True).start()
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
        consecutive_errors = 0
        while self._listen_active:
            if not self.continuous_listening and self.state != "listening":
                consecutive_errors = 0
                time.sleep(0.1)
                continue

            if self.recorder is None or self.stt is None:
                time.sleep(0.5)
                continue

            # Wait if speaker is playing
            if self.speaker and not self.speaker._idle.is_set():
                time.sleep(0.1)
                continue

            if self.state != "listening":
                self.set_state("listening")
                self.broadcast_sync("listen_started", {})

            try:
                audio = self.recorder.record_utterance()
                consecutive_errors = 0
            except Exception as e:
                consecutive_errors += 1
                wait_sec = min(5.0, 1.0 * consecutive_errors)
                print(f"[ui_server] Microphone capture error: {e}. Retrying in {wait_sec:.1f}s...")
                time.sleep(wait_sec)
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
                "speaker_target": getattr(self.cfg, "tts_speaker_target", "auto"),
                "piper_voices": voices_found,
            },
            "microphone": {
                "device_index": self.cfg.input_device,
                "resolved_device": getattr(self.recorder, "resolved_device", None),
                "device_name": getattr(self.recorder, "device_name", "Default"),
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
                api_name = ""
                try:
                    api_name = sd.query_hostapis(dev.get("hostapi", -1)).get("name", "")
                except Exception:
                    pass
                if "wdm" in api_name.lower() or "kernel" in api_name.lower():
                    continue
                devices.append({
                    "index": idx,
                    "name": dev.get("name", f"Device {idx}"),
                    "channels": dev.get("max_input_channels"),
                    "samplerate": dev.get("default_samplerate"),
                    "api": api_name,
                })
    except Exception as e:
        print(f"[ui_server] Devices query failed: {e}")

    active_idx = getattr(manager.recorder, "resolved_device", manager.cfg.input_device) if manager else None
    active_name = getattr(manager.recorder, "device_name", "Default") if manager else "Default"
    return JSONResponse(content={
        "devices": devices,
        "current": manager.cfg.input_device if manager else None,
        "active_index": active_idx,
        "active_name": active_name,
    })


@app.post("/api/test-mic")
def test_mic(payload: Dict[str, Any] = None) -> JSONResponse:
    """Sample audio briefly from the active or requested mic to measure input level."""
    import sounddevice as sd
    import numpy as np
    from audio import resolve_input_device

    device_idx = None
    if payload and "device" in payload:
        dev_val = payload["device"]
        if dev_val is not None and int(dev_val) >= 0:
            device_idx = int(dev_val)

    if device_idx is None:
        if manager and manager.cfg.input_device is not None:
            device_idx = manager.cfg.input_device
        else:
            device_idx, _ = resolve_input_device()

    try:
        dev_info = sd.query_devices(device_idx) if device_idx is not None else sd.query_devices(sd.default.device[0])
        sr = int(dev_info.get("default_samplerate", 16000))
        # Record 0.8 seconds
        rec_data = sd.rec(int(sr * 0.8), samplerate=sr, channels=1, device=device_idx, dtype="float32")
        sd.wait()
        rms = float(np.sqrt(np.mean(np.square(rec_data)) + 1e-12))
        peak = float(np.max(np.abs(rec_data)))
        return JSONResponse(content={
            "success": True,
            "device_index": device_idx,
            "device_name": dev_info.get("name", "Unknown"),
            "rms": round(rms, 5),
            "peak": round(peak, 5),
            "level_percent": min(100, int(peak * 100)),
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@app.post("/api/query")
async def post_query(payload: Dict[str, Any]) -> JSONResponse:
    if manager is None:
        raise HTTPException(status_code=503, detail="Manager not initialized")
    text = payload.get("text", "").strip()
    source = payload.get("client") or payload.get("source") or "laptop"
    if not text:
        raise HTTPException(status_code=400, detail="Empty text")

    # Run in background thread so HTTP response returns immediately
    threading.Thread(target=manager.handle_utterance, args=(text,), kwargs={"source": source}, daemon=True).start()
    return JSONResponse(content={"status": "processing", "query": text, "source": source})


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
    if "tts_speaker_target" in payload:
        cfg.tts_speaker_target = str(payload["tts_speaker_target"]).lower()

    manager.broadcast_sync("settings_updated", manager.get_system_status())
    return JSONResponse(content={"status": "updated", "config": manager.get_system_status()})


@app.post("/api/test-voice")
def post_test_voice(payload: Dict[str, Any]) -> JSONResponse:
    if manager is None:
        raise HTTPException(status_code=503, detail="Manager not initialized")
    text = payload.get("text") or "Hello. System online and voice agent operational."
    voice = payload.get("voice")
    backend = payload.get("backend")
    client = str(payload.get("client", "laptop")).lower()

    # Generate audio for client (phone speaker) as well
    audio_data_url = None
    try:
        wav_tuple = manager.speaker.synth_wav_bytes(text)
        if wav_tuple:
            wav_bytes, _ = wav_tuple
            b64_wav = base64.b64encode(wav_bytes).decode("ascii")
            audio_data_url = f"data:audio/wav;base64,{b64_wav}"
    except Exception:
        pass

    # Only play out of laptop speaker if the request originated from laptop/desktop
    if client != "phone":
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

    return JSONResponse(content={"status": "speaking", "sample": text, "audio": audio_data_url})


@app.get("/api/tts/latest")
def get_latest_tts_audio() -> Response:
    """Returns the most recent synthesized speech WAV audio file."""
    if not manager or not getattr(manager, "_latest_reply_audio", None):
        raise HTTPException(status_code=404, detail="No audio available")
    return Response(content=manager._latest_reply_audio, media_type="audio/wav")


@app.get("/api/tts/speak")
def get_tts_audio_for_text(text: str) -> Response:
    """Dynamically synthesizes any text into a WAV audio stream."""
    if not manager or not manager.speaker:
        raise HTTPException(status_code=503, detail="TTS not ready")
    wav_tuple = manager.speaker.synth_wav_bytes(text)
    if not wav_tuple:
        raise HTTPException(status_code=500, detail="Synthesis failed")
    wav_bytes, _ = wav_tuple
    return Response(content=wav_bytes, media_type="audio/wav")


@app.post("/api/tts/speak-local")
def post_speak_local(payload: Dict[str, Any]) -> JSONResponse:
    """Trigger local laptop playback for replay requests from desktop clients."""
    if not manager or not manager.speaker:
        raise HTTPException(status_code=503, detail="Speaker not ready")
    text = payload.get("text", "").strip()
    if text:
        manager.speaker.say(text, block=False)
    return JSONResponse(content={"status": "ok"})


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


def simulate_screen_click(x_norm: float, y_norm: float, button: str = "left") -> tuple[int, int]:
    """Simulates physical mouse click with per-monitor DPI awareness."""
    try:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass

        user32 = ctypes.windll.user32
        try:
            hWinsta = user32.OpenWindowStationW("winsta0", False, 0x10000000)
            if hWinsta:
                user32.SetProcessWindowStation(hWinsta)
            hDesk = user32.OpenDesktopW("default", 0, False, 0x10000000)
            if hDesk:
                user32.SetThreadDesktop(hDesk)
        except Exception:
            pass

        sw = user32.GetSystemMetrics(0) or 1920
        sh = user32.GetSystemMetrics(1) or 1080
        tx = max(0, min(sw - 1, int(x_norm * sw)))
        ty = max(0, min(sh - 1, int(y_norm * sh)))
        user32.SetCursorPos(tx, ty)
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
        print(f"[Remote Click] Simulated {button} click at ({tx}, {ty}) for normalized ({x_norm:.3f}, {y_norm:.3f})")
        return tx, ty
    except Exception as e:
        print(f"[Remote Click Error] {e}")
        return 0, 0


@app.post("/api/screen/click")
def post_screen_click(payload: Dict[str, Any]) -> JSONResponse:
    """Remote mouse click simulation for tapping on phone screen mirror."""
    x_norm = float(payload.get("x", 0))
    y_norm = float(payload.get("y", 0))
    button = str(payload.get("button", "left")).lower()

    try:
        tx, ty = simulate_screen_click(x_norm, y_norm, button)
        return JSONResponse(content={"status": "ok", "x": tx, "y": ty})
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
                                args=(full_pcm, "phone"),
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
                    simulate_screen_click(x_norm, y_norm, btn)
            except Exception as e:
                print(f"[DataChannel Click Error] {e}")

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

    # Wait briefly for local LAN candidate gathering so phone receives complete SDP
    for _ in range(25):
        if pc.iceGatheringState == "complete":
            break
        await asyncio.sleep(0.015)

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
    if sys.platform == "win32":
        try:
            manager.loop.set_exception_handler(_suppress_win_errors_handler)
        except Exception:
            pass

    queue: asyncio.Queue = asyncio.Queue(maxsize=120)
    with manager._sockets_lock:
        manager.active_sockets.append(websocket)
        manager.socket_queues[websocket] = queue

    # Dedicated sender task: single writer per socket eliminates concurrency collisions
    async def _client_sender():
        try:
            while True:
                msg = await queue.get()
                if msg is None:
                    break
                try:
                    await websocket.send_text(msg)
                except Exception:
                    break
                queue.task_done()
        except (WebSocketDisconnect, ConnectionResetError, ConnectionError, asyncio.CancelledError):
            pass
        except Exception:
            pass
        finally:
            with manager._sockets_lock:
                if websocket in manager.active_sockets:
                    manager.active_sockets.remove(websocket)
                manager.socket_queues.pop(websocket, None)
                manager.socket_clients.pop(websocket, None)

    sender_task = asyncio.create_task(_client_sender())

    local_ip = get_local_ip()
    # Send initial state snapshot with network info via sender queue
    init_msg = json.dumps({
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
    })
    await queue.put(init_msg)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type")
            client_tag = msg.get("client") or msg.get("client_type")
            if client_tag:
                manager.socket_clients[websocket] = str(client_tag).lower()

            if msg_type == "ping":
                await queue.put(json.dumps({"type": "pong"}))

            elif msg_type == "identify":
                # Registered client identity (phone vs laptop)
                pass

            elif msg_type == "start_listening":
                if manager.state in ("idle", "success", "error"):
                    manager.set_state("listening")
                    manager.broadcast_sync("listen_started", {"device": "laptop"})

            elif msg_type == "stop_listening" or msg_type == "commit_listening":
                if manager.recorder:
                    manager.recorder.commit()

            elif msg_type == "cancel_listening":
                if manager.recorder:
                    manager.recorder.cancel()
                manager.set_state("idle")

            elif msg_type == "toggle_listening":
                if manager.state == "listening":
                    if manager.recorder:
                        manager.recorder.commit()
                else:
                    manager.set_state("listening")
                    manager.broadcast_sync("listen_started", {"device": "laptop"})

            elif msg_type == "toggle_continuous":
                manager.continuous_listening = not manager.continuous_listening
                manager.broadcast_sync("continuous_changed", {
                    "enabled": manager.continuous_listening,
                })

            elif msg_type == "stop" or msg_type == "interrupt":
                manager.interrupt()

            elif msg_type == "send_text":
                text = msg.get("text", "").strip()
                source = msg.get("client") or manager.socket_clients.get(websocket, "laptop")
                if text:
                    threading.Thread(
                        target=manager.handle_utterance,
                        args=(text,),
                        kwargs={"source": source},
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
                simulate_screen_click(x_norm, y_norm, btn)

            elif msg_type == "scroll":
                direction = msg.get("direction", "down")
                amount = msg.get("amount", "medium")
                threading.Thread(
                    target=manager.toolbox.call,
                    args=("scroll_page", {"direction": direction, "amount": amount}),
                    daemon=True,
                ).start()

            elif msg_type == "media_control":
                action = msg.get("action", "play_pause")
                threading.Thread(
                    target=manager.toolbox.call,
                    args=("control_media", {"action": action}),
                    daemon=True,
                ).start()

            elif msg_type == "confirm_response":
                cid = msg.get("id", "")
                approved = bool(msg.get("approved", False))
                manager.resolve_confirmation(cid, approved)

            elif msg_type == "clear_history":
                manager.history.clear()
                manager.agent.reset()
                manager.broadcast_sync("history_cleared", {})

            elif msg_type == "get_status":
                await queue.put(json.dumps({
                    "type": "status_update",
                    "system": manager.get_system_status(),
                }))

    except (WebSocketDisconnect, ConnectionResetError, ConnectionError, asyncio.CancelledError):
        pass
    except Exception as exc:
        err_str = str(exc)
        if "10054" not in err_str and "closed" not in err_str.lower() and "dictionary changed size" not in err_str:
            print(f"[ui_server] WebSocket connection closed: {exc}")
    finally:
        with manager._sockets_lock:
            if websocket in manager.active_sockets:
                manager.active_sockets.remove(websocket)
            manager.socket_queues.pop(websocket, None)
        sender_task.cancel()


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
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    print(f"\n=======================================================")
    print(f"  VOICE AGENT COMMAND CENTER & REMOTE CONTROLLER")
    print(f"  [Laptop Display]  {url_local}")
    print(f"  [Phone / Mobile]  {url_phone}")
    print(f"  [Security]        {'HTTPS (Phone Mic & 60 FPS WebRTC Enabled)' if cfg.ui_ssl else 'HTTP'}")
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
