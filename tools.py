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
            "run_command": self._run_command,
            "change_directory": self._change_directory,
        }.get(name)
        if handler is None:
            return json.dumps({"error": f"unknown tool '{name}'"})
        try:
            return handler(args)
        except Exception as exc:  # never let a tool kill the loop
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"})

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
