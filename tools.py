"""Tools the LLM can call, plus the safety policy that gates shell execution.

Policy, in order:
  1. BLOCKED   - matches a destructive pattern, never runs.
  2. SAFE      - matches a read-only allowlist, runs without asking.
  3. otherwise - needs confirmation (typed, spoken, auto-approved or denied,
                 depending on cfg.confirm_mode).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import webbrowser
from typing import Any, Callable

from config import Config

# --------------------------------------------------------------------------- #
# Safety policy
# --------------------------------------------------------------------------- #
BLOCKED_PATTERNS: list[tuple[str, str]] = [
    (r"\bformat\s+[a-z]:", "disk format"),
    (r"\bdiskpart\b", "disk partitioning"),
    (r"\bmkfs\b", "filesystem creation"),
    (r"\bbcdedit\b", "boot configuration change"),
    (r"\bvssadmin\b.*\bdelete\b", "shadow copy deletion"),
    (r"\bcipher\b.*\s/w", "free-space wipe"),
    (r"\b(shutdown|restart-computer|stop-computer)\b", "shutdown or restart"),
    (r"\breg(\.exe)?\s+delete\b.*\bHKLM\b", "registry deletion under HKLM"),
    (r"\b(remove-item|ri|rmdir|rd|del|erase)\b[^\n]*\s-?/?(recurse|force|s|q)\b[^\n]*\s\"?[a-z]:\\?(\s|$|\*|\")",
     "recursive delete of a drive root"),
    (r"\bremove-item\b[^\n]*\s(c:\\windows|c:\\program files|\$env:systemroot|\$env:userprofile)\b",
     "delete inside a protected system location"),
    (r"\brm\s+-[a-z]*r[a-z]*f?\s+/(\s|$)", "recursive delete of the filesystem root"),
    (r"\bnet\s+user\b.*\s/add\b", "local account creation"),
    (r"\bnet\s+localgroup\b.*\badministrators\b.*\s/add\b", "privilege escalation"),
    (r"\bset-executionpolicy\b", "PowerShell execution policy change"),
    (r"\b(netsh\s+advfirewall|set-mppreference|add-mppreference)\b", "security setting change"),
    (r"\b(iwr|irm|invoke-webrequest|invoke-restmethod|curl|wget)\b[^\n]*\|\s*(iex|invoke-expression)",
     "download-and-execute"),
    (r"\bcertutil\b.*-urlcache", "download helper commonly used to stage payloads"),
    (r":\(\)\s*\{.*\}\s*;\s*:", "fork bomb"),
]

SAFE_PREFIXES: tuple[str, ...] = (
    "dir", "ls", "get-childitem", "gci", "tree",
    "echo", "write-output", "write-host",
    "type", "cat", "get-content", "more",
    "cd", "pwd", "get-location", "set-location",
    "whoami", "hostname", "date", "time", "get-date",
    "systeminfo", "get-computerinfo", "get-process", "ps", "tasklist",
    "get-service", "ipconfig", "ifconfig", "ping", "nslookup", "tracert",
    "get-volume", "get-psdrive", "get-disk", "get-item", "get-itemproperty",
    "get-ciminstance", "get-hotfix", "get-netipaddress", "get-netadapter",
    "select-object", "select ", "sort-object", "sort ", "where-object",
    "format-table", "format-list", "ft ", "fl ", "out-string", "convertto-json",
    "git status", "git log", "git diff", "git branch", "git remote",
    "python --version", "python -v", "pip list", "pip show", "node -v", "npm list",
    "claude", "claude -p", "claude --version", "agy", "agy run", "agy chat", "agy -p", "agy --print",
    "start", "start-process", "start agy", "start powershell", "start cmd", "start wt",
    "powershell", "cmd",
    "where", "which", "get-command", "measure-object", "select-string", "findstr",
    "help", "man", "get-help", "clear", "cls",
)

_CHAIN = re.compile(r"[;&|]{1,2}|\n")


def classify(command: str) -> tuple[str, str]:
    """Return (verdict, reason) where verdict is 'blocked' | 'safe' | 'confirm'."""
    low = " ".join(command.lower().split())

    for pattern, reason in BLOCKED_PATTERNS:
        if re.search(pattern, low):
            return "blocked", reason

    # A script block can hide anything, so it always needs confirmation.
    if "{" in low:
        return "confirm", "contains a script block"

    # A chained command is only auto-safe if every segment is auto-safe.
    # Leading "(", "&", "$(" etc. are common PowerShell idioms, not extra commands.
    segments = [s.strip().lstrip("(&$ \t") for s in _CHAIN.split(low)]
    segments = [s for s in segments if s]
    if segments and all(s.startswith(SAFE_PREFIXES) for s in segments):
        return "safe", "read-only command"

    return "confirm", "not on the read-only allowlist"


def assess_command_risk(command: str, cwd: str = "") -> dict[str, Any]:
    """Provide a structured safety assessment for the UI command preview."""
    verdict, reason = classify(command)
    cmd_low = command.lower().strip()

    # Risk level hierarchy
    if verdict == "blocked":
        risk = "destructive"
    elif verdict == "safe":
        risk = "low"
    else:
        # Check for dangerous or high impact operations
        if any(w in cmd_low for w in (
            "remove-item", "del ", "rmdir", "rd ", "drop ", "truncate", "kill ",
            "stop-process", "kill-process", "taskkill", "format", "wipe"
        )):
            risk = "high"
        elif any(w in cmd_low for w in ("install", "uninstall", "update", "set-", "new-item", "mkdir", "write-")):
            risk = "medium"
        else:
            risk = "medium"

    # Determine reversibility
    reversible = False
    if verdict == "safe":
        reversible = True
    elif any(cmd_low.startswith(p) for p in ("git checkout", "git switch", "git stash", "cd ", "mkdir")):
        reversible = True

    # Identify affected category and location
    category = "Command Runner"
    if any(k in cmd_low for k in ("chrome", "browser", "curl", "iwr", "http")):
        category = "Network / Browser"
    elif any(k in cmd_low for k in ("agy", "claude", "git", "python", "node", "npm")):
        category = "Developer Tools"
    elif any(k in cmd_low for k in ("dir", "ls", "get-childitem", "remove-item", "copy", "move")):
        category = "Local Filesystem"
    elif any(k in cmd_low for k in ("process", "tasklist", "taskkill", "service")):
        category = "System Processes"

    return {
        "command": command,
        "verdict": verdict,
        "reason": reason,
        "risk": risk,
        "reversible": reversible,
        "category": category,
        "affected": cwd or os.getcwd(),
    }


# --------------------------------------------------------------------------- #
# Web and Media Automation Helpers
# --------------------------------------------------------------------------- #
WEB_APPS: dict[str, str] = {
    "youtube": "https://www.youtube.com",
    "spotify": "https://open.spotify.com",
    "netflix": "https://www.netflix.com",
    "github": "https://github.com",
    "gmail": "https://mail.google.com",
    "google": "https://www.google.com",
    "chatgpt": "https://chatgpt.com",
    "claude": "https://claude.ai",
    "reddit": "https://www.reddit.com",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "amazon": "https://www.amazon.com",
    "maps": "https://maps.google.com",
    "google maps": "https://maps.google.com",
    "whatsapp": "https://web.whatsapp.com",
    "whatsapp web": "https://web.whatsapp.com",
    "notion": "https://www.notion.so",
    "canva": "https://www.canva.com",
    "instagram": "https://www.instagram.com",
    "facebook": "https://www.facebook.com",
    "twitch": "https://www.twitch.tv",
    "discord": "https://discord.com/app",
    "figma": "https://www.figma.com",
    "linkedin": "https://www.linkedin.com",
    "wikipedia": "https://www.wikipedia.org",
    "duckduckgo": "https://duckduckgo.com",
    "prime video": "https://www.primevideo.com",
    "hulu": "https://www.hulu.com",
    "disney": "https://www.disneyplus.com",
    "disney plus": "https://www.disneyplus.com",
}


def search_and_play_youtube(query: str, autoplay: bool = True) -> dict[str, Any]:
    """Search YouTube for a query, extract top video ID, and open in default browser with autoplay."""
    clean_q = query.strip()
    low = clean_q.lower()

    if not clean_q or low in ("youtube", "open youtube", "yt", "youtube.com"):
        webbrowser.open("https://www.youtube.com")
        return {
            "status": "opened_home",
            "url": "https://www.youtube.com",
            "message": "Opened YouTube homepage.",
        }

    search_term = clean_q
    for prefix in ("play ", "search for ", "find and play ", "stream ", "listen to ", "watch "):
        if low.startswith(prefix):
            search_term = search_term[len(prefix):].strip()
            low = search_term.lower()
            break
    for suffix in (" on youtube", " in youtube", " youtube video", " video on youtube", " on yt"):
        if low.endswith(suffix):
            search_term = search_term[:-len(suffix)].strip()
            break

    search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(search_term)}"
    target_url = search_url
    video_id = None

    try:
        req = urllib.request.Request(
            search_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            vids = re.findall(r"/watch\?v=([a-zA-Z0-9_-]{11})", html)
            if vids:
                video_id = vids[0]
                target_url = f"https://www.youtube.com/watch?v={video_id}"
                if autoplay:
                    target_url += "&autoplay=1"
    except Exception as exc:
        print(f"[tools] YouTube search fallback: {exc}", file=sys.stderr)
        target_url = search_url

    webbrowser.open(target_url)
    return {
        "status": "playing" if video_id else "opened_search",
        "query": search_term,
        "video_id": video_id,
        "url": target_url,
        "message": f"Playing '{search_term}' on YouTube." if video_id else f"Searching YouTube for '{search_term}'.",
    }


def open_web_application(app_or_url: str) -> dict[str, Any]:
    """Open a web application, website, or search query in the user's default browser."""
    target = app_or_url.strip()
    low = target.lower()

    for prefix in ("open ", "launch ", "goto ", "go to "):
        if low.startswith(prefix):
            target = target[len(prefix):].strip()
            low = target.lower()
            break

    if low in WEB_APPS:
        target_url = WEB_APPS[low]
        webbrowser.open(target_url)
        return {"status": "opened", "app": low, "url": target_url, "message": f"Opened {low}."}

    if target.startswith("http://") or target.startswith("https://"):
        target_url = target
    elif "." in target and " " not in target:
        target_url = f"https://{target}"
    else:
        target_url = f"https://www.google.com/search?q={urllib.parse.quote(target)}"

    webbrowser.open(target_url)
    return {"status": "opened", "target": target, "url": target_url, "message": f"Opened {target}."}


def scroll_window(direction: str = "down", amount: str = "medium") -> dict[str, Any]:
    """Scrolls the active window using native Windows user32 mouse wheel or keyboard events."""
    dir_low = direction.lower().strip()
    amt_low = amount.lower().strip()

    try:
        import ctypes
        user32 = ctypes.windll.user32
        MOUSEEVENTF_WHEEL = 0x0800
        KEYEVENTF_KEYUP = 0x0002
        VK_NEXT = 0x22   # Page Down
        VK_PRIOR = 0x21  # Page Up
        VK_HOME = 0x24
        VK_END = 0x23
        VK_CONTROL = 0x11

        if dir_low in ("top", "to top", "beginning"):
            user32.keybd_event(VK_CONTROL, 0, 0, 0)
            user32.keybd_event(VK_HOME, 0, 0, 0)
            user32.keybd_event(VK_HOME, 0, KEYEVENTF_KEYUP, 0)
            user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
            return {"action": "scrolled", "direction": "top", "message": "Scrolled to the top."}

        if dir_low in ("bottom", "to bottom", "end"):
            user32.keybd_event(VK_CONTROL, 0, 0, 0)
            user32.keybd_event(VK_END, 0, 0, 0)
            user32.keybd_event(VK_END, 0, KEYEVENTF_KEYUP, 0)
            user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
            return {"action": "scrolled", "direction": "bottom", "message": "Scrolled to the bottom."}

        if amt_low in ("page", "full", "screen"):
            vk = VK_NEXT if dir_low in ("down", "forward") else VK_PRIOR
            user32.keybd_event(vk, 0, 0, 0)
            user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
            return {"action": "scrolled", "direction": dir_low, "amount": "page", "message": f"Scrolled page {dir_low}."}

        multiplier = {"small": 2, "medium": 5, "large": 10}.get(amt_low, 5)
        delta = 120 * multiplier
        if dir_low in ("down", "forward"):
            delta = -delta

        user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, delta, 0)
        return {"action": "scrolled", "direction": dir_low, "amount": amt_low, "message": f"Scrolled {dir_low}."}
    except Exception as exc:
        return {"error": f"Scroll failed: {exc}"}


def control_playback(action: str) -> dict[str, Any]:
    """Sends native media control keyboard shortcuts for web video and audio players."""
    act = action.lower().strip()
    try:
        import ctypes
        user32 = ctypes.windll.user32
        KEYEVENTF_KEYUP = 0x0002

        VK_SPACE = 0x20
        VK_LEFT = 0x25
        VK_UP = 0x26
        VK_RIGHT = 0x27
        VK_DOWN = 0x28
        VK_M = 0x4D
        VK_F = 0x46
        VK_J = 0x4A
        VK_L = 0x4C

        def _press(vk: int):
            user32.keybd_event(vk, 0, 0, 0)
            time.sleep(0.02)
            user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)

        if act in ("play", "pause", "play_pause", "toggle"):
            _press(VK_SPACE)
            return {"action": "play_pause", "message": "Toggled play/pause."}

        elif act in ("mute", "unmute", "toggle_mute"):
            _press(VK_M)
            return {"action": "mute_toggle", "message": "Toggled mute."}

        elif act in ("fullscreen", "toggle_fullscreen"):
            _press(VK_F)
            return {"action": "fullscreen", "message": "Toggled fullscreen."}

        elif act in ("volume_up", "louder", "up"):
            for _ in range(3):
                _press(VK_UP)
                time.sleep(0.02)
            return {"action": "volume_up", "message": "Turned volume up."}

        elif act in ("volume_down", "quieter", "down"):
            for _ in range(3):
                _press(VK_DOWN)
                time.sleep(0.02)
            return {"action": "volume_down", "message": "Turned volume down."}

        elif act in ("forward", "seek_forward", "skip"):
            _press(VK_L)
            return {"action": "seek_forward", "message": "Skipped forward 10 seconds."}

        elif act in ("backward", "seek_backward", "rewind"):
            _press(VK_J)
            return {"action": "seek_backward", "message": "Rewound 10 seconds."}

        return {"error": f"Unknown media action: {action}"}
    except Exception as exc:
        return {"error": f"Playback control failed: {exc}"}


# --------------------------------------------------------------------------- #
# Tool implementations
# --------------------------------------------------------------------------- #
class ToolBox:
    """Executes tool calls. `confirm_cb(command, shell) -> bool` asks the user."""

    def __init__(self, cfg: Config, confirm_cb: Callable[[str, str], bool] | None = None):
        self.cfg = cfg
        self.confirm_cb = confirm_cb
        self.cwd = os.path.abspath(cfg.working_dir)

    # -- schema shown to the model ----------------------------------------- #
    @property
    def specs(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "play_youtube_video",
                    "description": (
                        "Search YouTube for any video, song, music, trailer, tutorial, or topic, "
                        "and immediately open and play the top matching video in the web browser."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The video name, song title, artist, or topic to search and play on YouTube.",
                            },
                            "autoplay": {
                                "type": "boolean",
                                "description": "Whether to auto-start playing the video directly. Defaults to true.",
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "open_web_app",
                    "description": (
                        "Open any web application, website, or URL in the default browser on Windows. "
                        "Supports popular apps (youtube, spotify, netflix, github, gmail, chatgpt, reddit, etc.) "
                        "or any web address."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "app_name_or_url": {
                                "type": "string",
                                "description": "Name of the web app (e.g. 'youtube', 'spotify', 'netflix', 'github', 'gmail', 'chatgpt') or any URL.",
                            },
                        },
                        "required": ["app_name_or_url"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "scroll_page",
                    "description": (
                        "Scroll the active window or web browser page down, up, to the top, or to the bottom."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "direction": {
                                "type": "string",
                                "enum": ["down", "up", "top", "bottom"],
                                "description": "Direction to scroll: 'down', 'up', 'top', or 'bottom'. Defaults to 'down'.",
                            },
                            "amount": {
                                "type": "string",
                                "enum": ["small", "medium", "large", "page"],
                                "description": "Amount to scroll: 'small', 'medium', 'large', or 'page'. Defaults to 'medium'.",
                            },
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "control_media",
                    "description": (
                        "Control media playback (video/audio) in the active web browser or player. "
                        "Supports play/pause toggle, mute/unmute, fullscreen, volume adjustments, and 10s skip."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": [
                                    "play_pause",
                                    "mute",
                                    "unmute",
                                    "fullscreen",
                                    "volume_up",
                                    "volume_down",
                                    "forward",
                                    "backward",
                                ],
                                "description": "The media control action to perform.",
                            },
                        },
                        "required": ["action"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "run_command",
                    "description": (
                        "Run a single shell command on the user's Windows PC and return its "
                        "output. Use PowerShell syntax unless cmd is requested. Prefer "
                        "read-only commands; anything that changes the system needs the "
                        "user's confirmation and may be refused."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "The command line to execute.",
                            },
                            "shell": {
                                "type": "string",
                                "enum": ["powershell", "cmd"],
                                "description": "Which shell to use. Defaults to powershell.",
                            },
                            "purpose": {
                                "type": "string",
                                "description": "Short plain-English reason, shown to the user.",
                            },
                        },
                        "required": ["command"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "change_directory",
                    "description": "Change the working directory used by run_command.",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                },
            },
        ]

    # -- dispatch ----------------------------------------------------------- #
    def call(self, name: str, args: dict[str, Any]) -> str:
        handler = {
            "play_youtube_video": self._play_youtube_video,
            "open_web_app": self._open_web_app,
            "scroll_page": self._scroll_page,
            "control_media": self._control_media,
            "run_command": self._run_command,
            "change_directory": self._change_directory,
        }.get(name)
        if handler is None:
            return json.dumps({"error": f"unknown tool '{name}'"})
        try:
            return handler(args)
        except Exception as exc:  # never let a tool kill the loop
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"})

    def _play_youtube_video(self, args: dict[str, Any]) -> str:
        query = str(args.get("query", "")).strip()
        autoplay = bool(args.get("autoplay", True))
        res = search_and_play_youtube(query, autoplay=autoplay)
        return json.dumps(res)

    def _open_web_app(self, args: dict[str, Any]) -> str:
        app_or_url = str(args.get("app_name_or_url", "")).strip()
        res = open_web_application(app_or_url)
        return json.dumps(res)

    def _scroll_page(self, args: dict[str, Any]) -> str:
        direction = str(args.get("direction", "down")).strip()
        amount = str(args.get("amount", "medium")).strip()
        res = scroll_window(direction=direction, amount=amount)
        return json.dumps(res)

    def _control_media(self, args: dict[str, Any]) -> str:
        action = str(args.get("action", "play_pause")).strip()
        res = control_playback(action)
        return json.dumps(res)

    def _change_directory(self, args: dict[str, Any]) -> str:
        path = os.path.abspath(os.path.expandvars(os.path.expanduser(str(args.get("path", "")))))
        if not os.path.isdir(path):
            return json.dumps({"error": f"not a directory: {path}"})
        self.cwd = path
        return json.dumps({"cwd": self.cwd})

    def _run_command(self, args: dict[str, Any]) -> str:
        command = str(args.get("command", "")).strip()
        shell = str(args.get("shell") or self.cfg.default_shell).lower()
        if not command:
            return json.dumps({"error": "empty command"})
        if shell not in ("powershell", "cmd"):
            shell = self.cfg.default_shell

        verdict, reason = classify(command)
        if verdict == "blocked":
            print(f"  [blocked] {command}  ({reason})")
            return json.dumps({
                "refused": True,
                "reason": f"Blocked by the local safety policy: {reason}. "
                          "The user must run this manually if they really want it.",
            })

        if verdict == "confirm":
            mode = self.cfg.confirm_mode
            if mode == "deny":
                return json.dumps({"refused": True, "reason": "Confirmation mode is 'deny'."})
            if mode != "auto":
                approved = self.confirm_cb(command, shell) if self.confirm_cb else False
                if not approved:
                    return json.dumps({"refused": True, "reason": "The user declined this command."})

        cmd_low = command.lower().strip()
        if shell == "powershell":
            if cmd_low.startswith("start powershell -"):
                args_part = command[len("start powershell "):].strip()
                command = f'Start-Process powershell -ArgumentList "{args_part}"'
            elif cmd_low in ("agy", "claude"):
                command = f"Start-Process {command}"
            elif cmd_low.startswith(("powershell -noexit", "powershell.exe -noexit")):
                command = f'Start-Process powershell -ArgumentList "{command[len("powershell "):].strip()}"'
        elif shell == "cmd":
            if cmd_low in ("agy", "claude"):
                command = f"start {command}"

        argv = (
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command]
            if shell == "powershell"
            else ["cmd", "/c", command]
        )

        print(f"  [run:{shell}] {command}")
        try:
            proc = subprocess.run(
                argv,
                cwd=self.cwd,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=self.cfg.command_timeout,
            )
            out, err, code = proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired:
            return json.dumps({
                "error": f"command timed out after {self.cfg.command_timeout}s",
                "command": command,
            })

        limit = self.cfg.max_output_chars
        if len(out) > limit:
            out = out[:limit] + f"\n...[truncated, {len(out)} chars total]"
        if len(err) > limit:
            err = err[:limit] + f"\n...[truncated]"

        stdout_text = out.strip()
        if not stdout_text and not err.strip() and code == 0:
            if command.lower().startswith(("start", "start-process")):
                stdout_text = "Process launched successfully in a new window."
            else:
                stdout_text = "(command completed with no output)"

        return json.dumps({
            "command": command,
            "shell": shell,
            "cwd": self.cwd,
            "exit_code": code,
            "stdout": stdout_text,
            "stderr": err.strip(),
        })
