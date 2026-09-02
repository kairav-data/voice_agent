"""Voice agent: speech -> local Ollama LLM -> speech, with shell control.

  python main.py                    # voice loop
  python main.py --text             # type instead of talking (no mic needed)
  python main.py --once "what is my ip address"
  python main.py --list-devices
"""

from __future__ import annotations

import argparse
import sys
import time

from config import Config

YES = {"yes", "yeah", "yep", "yup", "sure", "ok", "okay", "go ahead", "do it",
       "confirm", "affirmative", "please do", "y"}
NO = {"no", "nope", "cancel", "stop", "don't", "do not", "negative", "abort", "n"}


class VoiceAgent:
    def __init__(self, cfg: Config, text_mode: bool = False):
        self.cfg = cfg
        self.text_mode = text_mode
        self.recorder = None
        self.stt = None

        from audio import Speaker
        from llm import OllamaAgent
        from tools import ToolBox

        self.speaker = Speaker(cfg)
        self.toolbox = ToolBox(cfg, confirm_cb=self.confirm)
        self.agent = OllamaAgent(cfg, self.toolbox)

        ok, msg = self.agent.check()
        if not ok:
            print(f"[error] {msg}")
            sys.exit(1)
        print(f"[llm] {cfg.model} @ {cfg.ollama_host}")

        if not text_mode:
            from audio import Recorder
            from stt import Transcriber

            print(f"[stt] loading whisper '{cfg.whisper_model}' ({cfg.whisper_device})...")
            self.stt = Transcriber(cfg)
            self.recorder = Recorder(cfg)
            print("[mic] calibrating noise floor, stay quiet for a second...")
            level = self.recorder.calibrate()
            print(f"[mic] speech threshold = {level:.4f}")

    # -- input -------------------------------------------------------------- #
    def listen(self) -> str:
        """One utterance -> text. Empty string if nothing was heard."""
        if self.text_mode:
            try:
                return input("you> ").strip()
            except EOFError:
                return "exit"

        print("\n[listening]")
        audio = self.recorder.record_utterance()
        if audio is None:
            return ""
        t0 = time.monotonic()
        text = self.stt.transcribe(audio)
        if text:
            print(f"you> {text}   ({len(audio) / self.cfg.samplerate:.1f}s audio, "
                  f"{time.monotonic() - t0:.1f}s stt)")
        return text

    # -- confirmation gate ---------------------------------------------------- #
    def confirm(self, command: str, shell: str) -> bool:
        print(f"\n  !! wants to run [{shell}]: {command}")
        mode = self.cfg.confirm_mode

        if mode == "voice" and not self.text_mode:
            self.speaker.say(f"May I run {command}? Say yes or no.")
            for _ in range(2):
                answer = self.listen().lower().strip(" .!?")
                if not answer:
                    continue
                if any(w in answer for w in YES):
                    print("  -> approved (voice)")
                    return True
                if any(w in answer for w in NO):
                    print("  -> declined (voice)")
                    return False
                self.speaker.say("Please say yes or no.")
            print("  -> declined (no clear answer)")
            return False

        self.speaker.say("May I run that command?", block=True)
        try:
            answer = input("  approve? [y/N] ").strip().lower()
        except EOFError:
            answer = ""
        return answer in ("y", "yes")

    # -- loop ----------------------------------------------------------------- #
    def handle(self, text: str) -> None:
        def on_tool(name: str, args: dict) -> None:
            purpose = args.get("purpose")
            if purpose:
                print(f"  [tool] {name}: {purpose}")

        t0 = time.monotonic()
        try:
            reply = self.agent.ask(text, on_tool=on_tool)
        except Exception as exc:
            reply = f"Sorry, the language model failed: {exc}"
            print(f"[error] {exc}")
        if not reply:
            reply = "I didn't get a response from the model."
        print(f"bot> {reply}   ({time.monotonic() - t0:.1f}s)")
        self.speaker.say(reply)

    def run(self) -> None:
        cfg = self.cfg
        greeting = "Ready." if self.text_mode else "Voice agent ready. What do you need?"
        print(f"\n{greeting}  (say/type 'exit' to quit, 'reset' to clear history)\n")
        if not self.text_mode:
            self.speaker.say(greeting)

        while True:
            try:
                text = self.listen()
            except KeyboardInterrupt:
                break
            if not text:
                continue

            normalised = text.lower().strip(" .!?,")
            if normalised in cfg.stop_words or normalised in ("exit", "quit"):
                self.speaker.say("Goodbye.")
                break
            if normalised in ("reset", "new chat", "clear history"):
                self.agent.reset()
                self.speaker.say("History cleared.")
                continue
            if cfg.wake_word:
                wake = cfg.wake_word.lower()
                if wake not in normalised:
                    print(f"[ignored - no wake word '{cfg.wake_word}']")
                    continue
                text = normalised.split(wake, 1)[1].strip(" ,.") or text

            try:
                self.handle(text)
            except KeyboardInterrupt:
                print("\n[interrupted]")

        self.speaker.close()
        print("\nbye.")


def build_config(args: argparse.Namespace) -> Config:
    cfg = Config()
    if args.model:
        cfg.model = args.model
    if args.host:
        cfg.ollama_host = args.host
    if args.whisper:
        cfg.whisper_model = args.whisper
    if args.confirm:
        cfg.confirm_mode = args.confirm
    if args.shell:
        cfg.default_shell = args.shell
    if args.device is not None:
        cfg.input_device = args.device
    if args.no_tts:
        cfg.tts_enabled = False
    if args.tts_backend:
        cfg.tts_backend = args.tts_backend
    if args.voice:
        cfg.tts_voice = args.voice
    if args.rate:
        cfg.tts_rate = args.rate
    if args.wake:
        cfg.wake_word = args.wake
    cfg.__post_init__()
    return cfg


def main() -> None:
    p = argparse.ArgumentParser(description="STT -> Ollama -> TTS agent with shell control")
    p.add_argument("--text", action="store_true", help="type instead of speaking")
    p.add_argument("--once", metavar="TEXT", help="run a single instruction and exit")
    p.add_argument("--list-devices", action="store_true", help="show audio input devices")
    p.add_argument("--model", help="Ollama model name")
    p.add_argument("--host", help="Ollama host URL")
    p.add_argument("--whisper", help="faster-whisper model size (tiny.en/base.en/small.en)")
    p.add_argument("--confirm", choices=["terminal", "voice", "auto", "deny"],
                   help="how risky commands are approved (default: terminal)")
    p.add_argument("--shell", choices=["powershell", "cmd"], help="default shell")
    p.add_argument("--device", type=int, help="microphone device index")
    p.add_argument("--no-tts", action="store_true", help="disable spoken replies")
    p.add_argument("--tts-backend", choices=["auto", "piper", "edge", "sapi"],
                   help="voice engine: piper=offline neural, edge=online neural, sapi=robotic")
    p.add_argument("--voice", metavar="NAME",
                   help="voice name, e.g. en_US-ryan-high (piper) or en-IN-NeerjaNeural (edge)")
    p.add_argument("--rate", type=int, metavar="WPM", help="speaking speed, default 185")
    p.add_argument("--list-voices", action="store_true", help="show available voices")
    p.add_argument("--demo-voices", action="store_true",
                   help="speak a sample line through every voice so you can pick one")
    p.add_argument("--wake", metavar="WORD", help="only act on utterances containing this word")
    args = p.parse_args()

    if args.list_devices:
        from audio import Recorder
        print(Recorder.list_devices())
        return

    cfg = build_config(args)

    if args.list_voices:
        from audio import list_voices
        print(list_voices(cfg))
        return

    if args.demo_voices:
        from audio import demo_voices
        demo_voices(cfg)
        return

    if args.once:
        agent = VoiceAgent(cfg, text_mode=True)
        agent.handle(args.once)
        agent.speaker.wait()
        agent.speaker.close()
        return

    VoiceAgent(cfg, text_mode=args.text).run()


if __name__ == "__main__":
    main()
