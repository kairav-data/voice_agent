"""Ollama chat client with a tool-calling loop."""

from __future__ import annotations

import json
from typing import Any, Callable

import requests

from config import Config
from tools import ToolBox


class OllamaAgent:
    def __init__(self, cfg: Config, toolbox: ToolBox):
        self.cfg = cfg
        self.toolbox = toolbox
        self.url = cfg.ollama_host.rstrip("/") + "/api/chat"
        self.messages: list[dict[str, Any]] = [
            {"role": "system", "content": cfg.system_prompt}
        ]

    # -- infrastructure ----------------------------------------------------- #
    def check(self) -> tuple[bool, str]:
        """Verify Ollama is up and the configured model exists."""
        try:
            resp = requests.get(self.cfg.ollama_host.rstrip("/") + "/api/tags", timeout=10)
            resp.raise_for_status()
        except Exception as exc:
            return False, f"Cannot reach Ollama at {self.cfg.ollama_host}: {exc}"
        names = [m.get("name", "") for m in resp.json().get("models", [])]
        if self.cfg.model not in names and self.cfg.model.split(":")[0] not in [
            n.split(":")[0] for n in names
        ]:
            return False, (
                f"Model '{self.cfg.model}' is not installed. Available: "
                + (", ".join(names) or "none")
            )
        return True, "ok"

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        resp = requests.post(self.url, json=payload, timeout=self.cfg.request_timeout)
        if resp.status_code >= 400:
            raise RuntimeError(f"Ollama {resp.status_code}: {resp.text[:300]}")
        return resp.json()

    # -- history ------------------------------------------------------------ #
    def _trim(self) -> None:
        """Keep the system prompt plus the most recent turns, cutting only at
        user-message boundaries so tool calls stay paired with their results."""
        keep = self.cfg.history_turns
        user_idx = [i for i, m in enumerate(self.messages) if m["role"] == "user"]
        if len(user_idx) <= keep:
            return
        cut = user_idx[-keep]
        self.messages = [self.messages[0]] + self.messages[cut:]

    def reset(self) -> None:
        self.messages = [{"role": "system", "content": self.cfg.system_prompt}]

    # -- main loop ----------------------------------------------------------- #
    def ask(self, user_text: str, on_tool: Callable[[str, dict], None] | None = None) -> str:
        self.messages.append({"role": "user", "content": user_text})
        self._trim()

        for _round in range(self.cfg.max_tool_rounds):
            data = self._post({
                "model": self.cfg.model,
                "messages": self.messages,
                "tools": self.toolbox.specs,
                "stream": False,
                "options": {
                    "temperature": self.cfg.temperature,
                    "num_ctx": self.cfg.num_ctx,
                },
            })
            message = data.get("message", {}) or {}
            self.messages.append(message)

            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                return (message.get("content") or "").strip()

            for call in tool_calls:
                fn = call.get("function", {}) or {}
                name = fn.get("name", "")
                raw_args = fn.get("arguments", {})
                if isinstance(raw_args, str):
                    try:
                        raw_args = json.loads(raw_args)
                    except json.JSONDecodeError:
                        raw_args = {"command": raw_args}
                if not isinstance(raw_args, dict):
                    raw_args = {}

                if on_tool:
                    on_tool(name, raw_args)
                result = self.toolbox.call(name, raw_args)
                self.messages.append({
                    "role": "tool",
                    "name": name,
                    "tool_name": name,
                    "content": result,
                })

        return (
            "I used several tools but could not finish that in the allowed number of steps. "
            "Try asking for one thing at a time."
        )
