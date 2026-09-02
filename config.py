"""Central configuration for the voice agent.

Every value can be overridden with an environment variable of the same name
(prefixed with VA_) or with a CLI flag on main.py.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    return os.environ.get(f"VA_{name}", default)


def _env_int(name: str, default: int) -> int:
    return int(_env(name, str(default)))


def _env_float(name: str, default: float) -> float:
    return float(_env(name, str(default)))


@dataclass
class Config:
    # ---------------- LLM (Ollama) ----------------
    ollama_host: str = _env("OLLAMA_HOST", "http://localhost:11434")
    model: str = _env("MODEL", "gemma4:31b-cloud")
    temperature: float = _env_float("TEMPERATURE", 0.3)
    num_ctx: int = _env_int("NUM_CTX", 8192)
    request_timeout: int = _env_int("LLM_TIMEOUT", 180)
    max_tool_rounds: int = _env_int("MAX_TOOL_ROUNDS", 6)
    history_turns: int = _env_int("HISTORY_TURNS", 12)  # user+assistant msgs kept

    # ---------------- Speech to text ----------------
    whisper_model: str = _env("WHISPER_MODEL", "base.en")  # tiny.en/base.en/small.en/medium
    whisper_device: str = _env("WHISPER_DEVICE", "cpu")     # cpu | cuda
    whisper_compute: str = _env("WHISPER_COMPUTE", "int8")  # int8 | float16 | float32
    language: str | None = _env("LANGUAGE", "en") or None

    # ---------------- Microphone / VAD ----------------
    samplerate: int = 16000
    frame_ms: int = 30
    input_device: int | None = (
        int(_env("INPUT_DEVICE", "-1")) if _env("INPUT_DEVICE", "-1") != "-1" else None
    )
    silence_hangover_s: float = _env_float("SILENCE_HANGOVER", 0.9)
    min_speech_s: float = _env_float("MIN_SPEECH", 0.35)
    max_utterance_s: float = _env_float("MAX_UTTERANCE", 30.0)
    energy_multiplier: float = _env_float("ENERGY_MULT", 3.0)   # x measured noise floor
    energy_floor: float = _env_float("ENERGY_FLOOR", 0.012)     # absolute minimum RMS

    # ---------------- Text to speech ----------------
    # backend: auto | piper (offline neural) | edge (online neural) | sapi (robotic)
    tts_backend: str = _env("TTS_BACKEND", "auto")
    tts_enabled: bool = _env("TTS", "1") == "1"
    tts_rate: int = _env_int("TTS_RATE", 185)          # words per minute, mapped per backend
    tts_volume: float = _env_float("TTS_VOLUME", 1.0)
    tts_voice: str = _env("TTS_VOICE", "")             # backend-specific voice name
    edge_voice: str = _env("EDGE_VOICE", "en-US-AvaNeural")
    piper_model: str = _env("PIPER_MODEL", "")         # full path to a .onnx voice
    piper_dir: str = _env("PIPER_DIR", "")             # defaults to ./voices

    # ---------------- Behaviour ----------------
    # terminal = type y/n ; voice = say yes/no ; auto = never ask (dangerous) ; deny = never run
    confirm_mode: str = _env("CONFIRM", "terminal")
    default_shell: str = _env("SHELL", "powershell")  # powershell | cmd
    command_timeout: int = _env_int("CMD_TIMEOUT", 90)
    max_output_chars: int = _env_int("MAX_OUTPUT", 4000)
    working_dir: str = _env("WORKDIR", os.getcwd())
    wake_word: str = _env("WAKE_WORD", "")  # empty = always listening
    stop_words: tuple[str, ...] = ("exit", "quit", "goodbye", "stop listening", "shut down")

    system_prompt: str = field(default="")

    def __post_init__(self) -> None:
        if not self.system_prompt:
            self.system_prompt = DEFAULT_SYSTEM_PROMPT.format(
                shell=self.default_shell, workdir=self.working_dir
            )


DEFAULT_SYSTEM_PROMPT = """You are a hands-free voice assistant running on the user's Windows 11 PC.
Your replies are read aloud by a text-to-speech engine, so:
- Answer in 1-3 short spoken sentences. No markdown, no bullet lists, no code blocks, no emoji.
- Never read long command output verbatim. Summarise it ("I found 14 files, the largest is setup.log").
- Spell out only what matters; skip paths and flags unless the user asked for them.

You can operate the computer with the run_command tool.
- The default shell is {shell} and the working directory is {workdir}.
- Use one command per call, and prefer read-only commands when they answer the question.
- If the user asks for something you can check on the machine, check it instead of guessing.
- Dangerous commands may be blocked or need the user's confirmation; if a call comes back
  refused or cancelled, just say so and offer a safer alternative.
- If a command fails, read the error and try once more with a fix before giving up.

If the request is conversational, answer directly without using any tool."""
