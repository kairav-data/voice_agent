# ECOWHISPER — STT → Ollama (ECO) → TTS, with shell control

A hands-free assistant powered by ECO that listens on your mic, thinks with your local Ollama model,
runs commands on your Windows PC when asked, and speaks the answer back.

```
mic ──► faster-whisper ──► Ollama (/api/chat + tools) ──► neural voice ──► speakers
                                        │
                                        └──► run_command ──► safety policy ──► PowerShell / cmd
```

## Files

| File | Purpose |
|---|---|
| `main.py` | CLI, the listen → think → speak loop, confirmation prompts |
| `config.py` | All settings + the system prompt (env vars `VA_*` override) |
| `audio.py` | Mic capture with an energy-gated VAD, and the TTS backends + worker thread |
| `voices/` | Downloaded piper `.onnx` voice models |
| `stt.py` | faster-whisper transcription |
| `llm.py` | Ollama client and the tool-calling loop |
| `tools.py` | `run_command` / `change_directory` + the command safety policy |

## Run

```bash
run_ui.bat                                      # launch the futuristic Web Command Center UI
run.bat --ui                                    # same, opens browser / native Edge window
run.bat                                         # CLI console voice loop
```

Other modes:

```bash
run.bat --text                                  # type instead of talking
run.bat --once "how much free disk space do I have"
run.bat --list-devices                          # find your mic index
run.bat --device 15 --confirm voice             # pick a mic, approve by saying "yes"
run.bat --demo-voices                           # hear every voice, then pick one
run.bat --list-voices                           # names you can pass to --voice
```

### UI Features:
- **60 FPS Canvas Voice Orb**: Multi-layered real-time particle and harmonic wave visualization with 11 distinct states (`idle`, `listening`, `hearing`, `processing`, `thinking`, `tool`, `confirmation`, `executing`, `speaking`, `success`, `error`).
- **Low-Latency WebSocket Streaming**: Real-time microphone RMS level meter, transcription typing effect, spoken responses, and activity timeline.
- **Safety First**: Full command previews, risk tier assessment, reversibility indicators, and interactive authorization modal.
- **Keyboard Shortcuts**:
  - `Space`: Push-to-Talk (hold or toggle)
  - `Escape`: Instant Interrupt / Stop
  - `Ctrl + K`: Quick command prompt
  - `Ctrl + L`: Clear conversation history
  - `Ctrl + ,`: Settings & model/voice switcher
  - `Ctrl + T`: Activity stream drawer
  - `Ctrl + H`: Past queries drawer
- **Settings Panel**: Live Ollama model selector, TTS engine & voice tester with sample speech playback, speaking rate slider, shell selection (PowerShell / CMD), and confirmation policy.

Say or type `exit` to quit, `reset` to clear the conversation history.

## Voices

| Backend | Quality | Latency before speech | Needs internet |
|---|---|---|---|
| `piper` (default) | good neural | ~0.4 s | no |
| `edge` | best, closest to human | ~1.7 s | yes |
| `sapi` | robotic | instant | no |

```bash
run.bat --tts-backend edge --voice en-IN-NeerjaNeural   # most human, online
run.bat --voice en_US-ryan-high                         # offline male voice
run.bat --rate 165                                      # slower speech (default 185 wpm)
```

`auto` (the default) tries piper, then edge, then sapi. Make a choice permanent with
environment variables — `VA_TTS_BACKEND=edge`, `VA_TTS_VOICE=en-US-AvaNeural`, `VA_TTS_RATE=170`.

**Edge voices are synthesised by Microsoft's online service**, so reply text (which can
include summaries of command output) leaves your machine. piper runs entirely offline.

More offline voices — anything from the [piper voice list](https://rhasspy.github.io/piper-samples/):

```bash
python -m piper.download_voices --download-dir voices en_GB-alba-medium
```

## Flags

| Flag | Default | Notes |
|---|---|---|
| `--model` | `gemma4:31b-cloud` | any model in `ollama list` that supports tools |
| `--whisper` | `base.en` | `tiny.en` (fastest) · `base.en` · `small.en` (most accurate) |
| `--confirm` | `terminal` | `terminal` (type y/N) · `voice` (say yes/no) · `auto` (never ask) · `deny` |
| `--shell` | `powershell` | or `cmd` |
| `--device` | system default | mic index from `--list-devices` |
| `--wake` | off | e.g. `--wake jarvis` — ignores utterances without the word |
| `--no-tts` | off | silent replies |
| `--tts-backend` | `auto` | `piper` · `edge` · `sapi` |
| `--voice` | first piper model | e.g. `en_US-ryan-high`, `en-IN-NeerjaNeural` |
| `--rate` | 185 | words per minute |

Anything can also be set by environment variable: `VA_MODEL`, `VA_WHISPER_MODEL`,
`VA_CONFIRM`, `VA_TTS_RATE`, `VA_WORKDIR`, `VA_ENERGY_FLOOR`, …

## Safety policy (`tools.py`)

Every command the model proposes is classified before it runs:

1. **blocked** — destructive or system-level patterns (disk format, `diskpart`, shutdown,
   deleting a drive root or `C:\Windows`, `HKLM` registry deletes, firewall/Defender changes,
   download-and-execute pipelines, adding admin users). These never run, in any mode.
2. **safe** — a read-only allowlist (`dir`, `Get-Process`, `ipconfig`, `git status`, …).
   Runs immediately. A chained command is only safe if *every* segment is.
3. **confirm** — everything else, including anything containing a `{ }` script block
   (a script block can hide any command inside a read-only-looking pipeline). You approve
   it per command; the exact command line is printed before you decide.

`--confirm auto` skips step 3 (step 1 still applies). Only use it for a session you are
watching. Widen or tighten the lists by editing `SAFE_PREFIXES` and `BLOCKED_PATTERNS`.

## Notes

- **`gemma4:31b-cloud` is a cloud-proxied model** — Ollama forwards your prompts *and any
  command output the agent reads* to ollama.com. For a fully offline setup, pull a local
  tool-capable model and pass it: `ollama pull qwen3:8b` then `run.bat --model qwen3:8b`.
- First run downloads the whisper weights (~150 MB) to the HuggingFace cache; after that
  STT is fully offline and model load takes a couple of seconds.
- Mic tuning: the agent measures your noise floor at startup. If it triggers on background
  noise raise `VA_ENERGY_FLOOR` (e.g. `0.02`); if it misses quiet speech lower it. Wearing
  headphones avoids the agent hearing its own voice.
- Latency is roughly 0.5–1 s of STT plus whatever the model takes; `tiny.en` shaves the STT
  side if the model is fast.
- Replies are split into sentences and synthesised one ahead of playback, and the output
  stream is kept open between utterances — reopening it per reply cost about 0.5 s.
- `pyttsx3` is deliberately not used: its SAPI driver speaks only the first utterance when
  driven from a worker thread, then `runAndWait()` returns instantly and silently. The
  `sapi` backend talks to `SAPI.SpVoice` over COM instead.
