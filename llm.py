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
        """Verify the active provider is configured and available."""
        provider = self.cfg.provider
        if provider == "ollama":
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
                    f"Model '{self.cfg.model}' is not installed in Ollama. Available: "
                    + (", ".join(names) or "none")
                )
            return True, "ok"

        elif provider == "gemini":
            if not self.cfg.gemini_api_key:
                return False, "Google Gemini API key not configured. Please add it in Settings."
            return True, "ok"

        elif provider == "openai":
            if not self.cfg.openai_api_key:
                return False, "OpenAI API key not configured. Please add it in Settings."
            return True, "ok"

        elif provider == "anthropic":
            if not self.cfg.anthropic_api_key:
                return False, "Anthropic Claude API key not configured. Please add it in Settings."
            return True, "ok"

        return True, "ok"

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
        self.anthropic_messages: list[dict[str, Any]] = []

    # -- main loop ----------------------------------------------------------- #
    def ask(
        self,
        user_text: str,
        on_tool: Callable[[str, dict], None] | None = None,
        on_status: Callable[[str, dict], None] | None = None,
    ) -> str:
        provider = self.cfg.provider
        if provider == "gemini":
            return self._ask_openai_compatible(
                user_text=user_text,
                endpoint="https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                api_key=self.cfg.gemini_api_key,
                provider_name="Google Gemini",
                on_tool=on_tool,
                on_status=on_status,
            )
        elif provider == "openai":
            return self._ask_openai_compatible(
                user_text=user_text,
                endpoint="https://api.openai.com/v1/chat/completions",
                api_key=self.cfg.openai_api_key,
                provider_name="OpenAI",
                on_tool=on_tool,
                on_status=on_status,
            )
        elif provider == "anthropic":
            return self._ask_anthropic(
                user_text=user_text,
                on_tool=on_tool,
                on_status=on_status,
            )
        else:
            return self._ask_ollama(
                user_text=user_text,
                on_tool=on_tool,
                on_status=on_status,
            )

    # -- Ollama backend ----------------------------------------------------- #
    def _ask_ollama(
        self,
        user_text: str,
        on_tool: Callable[[str, dict], None] | None = None,
        on_status: Callable[[str, dict], None] | None = None,
    ) -> str:
        url = self.cfg.ollama_host.rstrip("/") + "/api/chat"
        self.messages.append({"role": "user", "content": user_text})
        self._trim()

        for _round in range(self.cfg.max_tool_rounds):
            if on_status:
                try:
                    on_status("thinking", {"round": _round})
                except Exception:
                    pass

            payload = {
                "model": self.cfg.model,
                "messages": self.messages,
                "tools": self.toolbox.specs,
                "stream": False,
                "options": {
                    "temperature": self.cfg.temperature,
                    "num_ctx": self.cfg.num_ctx,
                },
            }

            try:
                resp = requests.post(url, json=payload, timeout=self.cfg.request_timeout)
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                return f"Error communicating with Ollama: {exc}"

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
                if on_status:
                    try:
                        on_status("tool_start", {"name": name, "args": raw_args})
                    except Exception:
                        pass

                result = self.toolbox.call(name, raw_args)

                if on_status:
                    try:
                        on_status("tool_result", {"name": name, "args": raw_args, "result": result})
                    except Exception:
                        pass

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

    # -- OpenAI / Google Gemini (OpenAI-compatible) backend ----------------- #
    def _ask_openai_compatible(
        self,
        user_text: str,
        endpoint: str,
        api_key: str,
        provider_name: str,
        on_tool: Callable[[str, dict], None] | None = None,
        on_status: Callable[[str, dict], None] | None = None,
    ) -> str:
        if not api_key:
            return f"No API key provided for {provider_name}. Please set your API key in Settings."

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        self.messages.append({"role": "user", "content": user_text})
        self._trim()

        for _round in range(self.cfg.max_tool_rounds):
            if on_status:
                try:
                    on_status("thinking", {"round": _round})
                except Exception:
                    pass

            payload = {
                "model": self.cfg.model,
                "messages": self.messages,
                "tools": self.toolbox.specs,
                "temperature": self.cfg.temperature,
            }

            try:
                resp = requests.post(endpoint, headers=headers, json=payload, timeout=self.cfg.request_timeout)
                if resp.status_code != 200:
                    err_detail = ""
                    try:
                        err_json = resp.json()
                        if isinstance(err_json, list) and err_json and "error" in err_json[0]:
                            err_detail = err_json[0]["error"].get("message") or str(err_json[0])
                        elif isinstance(err_json, dict) and "error" in err_json:
                            err_err = err_json["error"]
                            if isinstance(err_err, dict):
                                err_detail = err_err.get("message") or str(err_err)
                            else:
                                err_detail = str(err_err)
                    except Exception:
                        err_detail = resp.text[:200]
                    if resp.status_code in (401, 403) or "API key" in err_detail or "API_KEY" in err_detail:
                        return f"Authentication failed for {provider_name}: {err_detail}. Please verify your API key in Settings."
                    return f"{provider_name} API returned error ({resp.status_code}): {err_detail}"
                data = resp.json()
            except Exception as exc:
                return f"Error communicating with {provider_name}: {exc}"

            choices = data.get("choices") or []
            if not choices:
                return f"No response received from {provider_name}."

            message = choices[0].get("message", {}) or {}
            self.messages.append(message)

            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                return (message.get("content") or "").strip()

            for call in tool_calls:
                call_id = call.get("id") or f"call_{_round}"
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
                if on_status:
                    try:
                        on_status("tool_start", {"name": name, "args": raw_args})
                    except Exception:
                        pass

                result = self.toolbox.call(name, raw_args)

                if on_status:
                    try:
                        on_status("tool_result", {"name": name, "args": raw_args, "result": result})
                    except Exception:
                        pass

                self.messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": name,
                    "content": str(result),
                })

        return (
            "I used several tools but could not finish that in the allowed number of steps. "
            "Try asking for one thing at a time."
        )

    # -- Anthropic Claude backend ------------------------------------------- #
    def _ask_anthropic(
        self,
        user_text: str,
        on_tool: Callable[[str, dict], None] | None = None,
        on_status: Callable[[str, dict], None] | None = None,
    ) -> str:
        api_key = self.cfg.anthropic_api_key
        if not api_key:
            return "No Anthropic Claude API key configured. Please add it in Settings."

        endpoint = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        anthropic_tools = []
        for spec in self.toolbox.specs:
            fn = spec.get("function", {})
            anthropic_tools.append({
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
            })

        if not hasattr(self, "anthropic_messages") or not isinstance(self.anthropic_messages, list):
            self.anthropic_messages = []

        self.anthropic_messages.append({
            "role": "user",
            "content": user_text,
        })

        if len(self.anthropic_messages) > self.cfg.history_turns * 2:
            self.anthropic_messages = self.anthropic_messages[-(self.cfg.history_turns * 2):]

        for _round in range(self.cfg.max_tool_rounds):
            if on_status:
                try:
                    on_status("thinking", {"round": _round})
                except Exception:
                    pass

            payload = {
                "model": self.cfg.model,
                "max_tokens": 2048,
                "system": self.cfg.system_prompt,
                "messages": self.anthropic_messages,
                "tools": anthropic_tools,
                "temperature": self.cfg.temperature,
            }

            try:
                resp = requests.post(endpoint, headers=headers, json=payload, timeout=self.cfg.request_timeout)
                if resp.status_code != 200:
                    err_detail = ""
                    try:
                        err_json = resp.json()
                        if isinstance(err_json, dict) and "error" in err_json:
                            err_err = err_json["error"]
                            if isinstance(err_err, dict):
                                err_detail = err_err.get("message") or str(err_err)
                            else:
                                err_detail = str(err_err)
                    except Exception:
                        err_detail = resp.text[:200]
                    if resp.status_code in (401, 403) or "api_key" in err_detail or "API key" in err_detail:
                        return f"Authentication failed for Anthropic Claude: {err_detail}. Please check your API key in Settings."
                    return f"Anthropic Claude API returned error ({resp.status_code}): {err_detail}"
                data = resp.json()
            except Exception as exc:
                return f"Error communicating with Anthropic Claude: {exc}"

            content_blocks = data.get("content") or []
            self.anthropic_messages.append({
                "role": "assistant",
                "content": content_blocks,
            })

            tool_uses = [b for b in content_blocks if b.get("type") == "tool_use"]
            if not tool_uses:
                text_parts = [b.get("text", "") for b in content_blocks if b.get("type") == "text"]
                return "".join(text_parts).strip()

            tool_results = []
            for t_use in tool_uses:
                tool_id = t_use.get("id")
                name = t_use.get("name", "")
                raw_args = t_use.get("input") or {}
                if not isinstance(raw_args, dict):
                    raw_args = {}

                if on_tool:
                    on_tool(name, raw_args)
                if on_status:
                    try:
                        on_status("tool_start", {"name": name, "args": raw_args})
                    except Exception:
                        pass

                result = self.toolbox.call(name, raw_args)

                if on_status:
                    try:
                        on_status("tool_result", {"name": name, "args": raw_args, "result": result})
                    except Exception:
                        pass

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": str(result),
                })

            self.anthropic_messages.append({
                "role": "user",
                "content": tool_results,
            })

        return (
            "I used several tools but could not finish that in the allowed number of steps. "
            "Try asking for one thing at a time."
        )


LLMAgent = OllamaAgent
