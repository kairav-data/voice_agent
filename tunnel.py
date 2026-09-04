"""Tunnel manager for Voice Agent remote access from anywhere.

Uses Cloudflare Quick Tunnel (cloudflared) to provide a zero-configuration,
free, encrypted HTTPS tunnel with a valid SSL certificate. Bypasses CGNAT,
firewalls, and carrier restrictions, allowing users to connect from cellular data
or any remote Wi-Fi securely.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from typing import Any, Dict, Optional


CLOUDFLARED_DOWNLOAD_URL = (
    "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
)

TRYCLOUDFLARE_REGEX = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")


class TunnelManager:
    """Manages the lifecycle of the Cloudflare Quick Tunnel process."""

    def __init__(self, binary_path: Optional[str] = None) -> None:
        self.custom_path = binary_path
        self.process: Optional[subprocess.Popen] = None
        self.public_url: Optional[str] = None
        self.status: str = "stopped"  # stopped | starting | active | error
        self.error_message: Optional[str] = None
        self._lock = threading.RLock()
        self._monitor_thread: Optional[threading.Thread] = None
        self.on_change: Optional[Any] = None

    def _notify(self) -> None:
        cb = self.on_change
        if cb:
            try:
                info = self.get_info()
                cb(info)
            except Exception as e:
                print(f"[Tunnel] Error in on_change callback: {e}")

    def find_binary(self) -> Optional[str]:
        """Locates cloudflared executable on system or in project directory."""
        if self.custom_path and os.path.exists(self.custom_path):
            return self.custom_path

        # 1. PATH lookup
        found = shutil.which("cloudflared")
        if found:
            return found

        # 2. Common Windows Program Files locations
        candidates = [
            os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "cloudflared", "cloudflared.exe"),
            os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), "cloudflared", "cloudflared.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Links", "cloudflared.exe"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "cloudflared.exe"),
        ]
        for c in candidates:
            if c and os.path.exists(c):
                return c

        return None

    def download_binary(self) -> Optional[str]:
        """Downloads standalone cloudflared binary to project directory if not installed."""
        target_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cloudflared.exe")
        if os.path.exists(target_path):
            return target_path

        try:
            print("[Tunnel] Downloading cloudflared standalone binary for secure remote access...")
            urllib.request.urlretrieve(CLOUDFLARED_DOWNLOAD_URL, target_path)
            if os.path.exists(target_path):
                print(f"[Tunnel] Successfully downloaded cloudflared to {target_path}")
                return target_path
        except Exception as e:
            print(f"[Tunnel] Failed to download cloudflared: {e}")
        return None

    def start(self, local_port: int, ssl: bool = True, timeout: float = 30.0) -> Optional[str]:
        """Starts the Cloudflare Quick Tunnel and waits for the public HTTPS URL."""
        with self._lock:
            if self.status == "active" and self.public_url:
                return self.public_url
            if self.status == "starting":
                return self.public_url

            self.status = "starting"
            self.public_url = None
            self.error_message = None

        self._notify()

        exe = self.find_binary() or self.download_binary()
        if not exe:
            with self._lock:
                self.status = "error"
                self.error_message = "cloudflared binary not found and automatic download failed."
            print(f"[Tunnel Error] {self.error_message}")
            self._notify()
            return None

        proto = "https" if ssl else "http"
        local_target = f"{proto}://localhost:{local_port}"

        cmd = [
            exe,
            "tunnel",
            "--url",
            local_target,
            "--no-autoupdate",
        ]
        if ssl:
            cmd.append("--no-tls-verify")

        url_event = threading.Event()

        with self._lock:
            if self.process:
                try:
                    self.process.terminate()
                except Exception:
                    pass
                self.process = None

            try:
                print(f"[Tunnel] Launching Cloudflare Tunnel to {local_target}...")
                # Redirect stderr to stdout to prevent pipe buffer deadlock
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
            except Exception as e:
                self.status = "error"
                self.error_message = f"Failed to launch cloudflared: {e}"
                print(f"[Tunnel Error] {self.error_message}")
                self._notify()
                return None

        # Start thread to monitor output and extract public URL
        def _reader():
            p = self.process
            if not p or not p.stdout:
                return

            try:
                for line in p.stdout:
                    if not line:
                        continue
                    line_str = line.strip()
                    match = TRYCLOUDFLARE_REGEX.search(line_str)
                    if match:
                        with self._lock:
                            self.public_url = match.group(0)
                            self.status = "active"
                            self.error_message = None
                        print(f"\n[Tunnel Active] Public Remote URL: {self.public_url}\n")
                        self._notify()
                        url_event.set()
                    elif "Registered tunnel connection" in line_str:
                        url_event.set()
            except Exception as e:
                print(f"[Tunnel] Reader error: {e}")

            # Process exited
            with self._lock:
                if self.status != "stopped":
                    if not self.public_url:
                        self.status = "error"
                        if not self.error_message:
                            self.error_message = "Tunnel process terminated unexpectedly."
                    else:
                        self.status = "stopped"
                        self.public_url = None
            self._notify()
            url_event.set()

        self._monitor_thread = threading.Thread(target=_reader, daemon=True)
        self._monitor_thread.start()

        # Wait for public URL
        if not url_event.wait(timeout=timeout):
            with self._lock:
                if self.status == "starting":
                    self.status = "error"
                    self.error_message = "Tunnel timed out while connecting to Cloudflare edge."
                    if self.process:
                        try:
                            self.process.terminate()
                        except Exception:
                            pass
                        self.process = None
            print(f"[Tunnel Error] {self.error_message}")
            self._notify()

        return self.public_url

    def stop(self) -> None:
        """Stops the active tunnel process."""
        with self._lock:
            self.status = "stopped"
            self.public_url = None
            self.error_message = None
            proc = self.process
            self.process = None

        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=2.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        print("[Tunnel] Cloudflare remote tunnel stopped.")
        self._notify()

    def get_info(self) -> Dict[str, Any]:
        """Returns the current state and public URL of the tunnel."""
        with self._lock:
            return {
                "active": self.status == "active" and bool(self.public_url),
                "status": self.status,
                "public_url": self.public_url,
                "error": self.error_message,
            }


# Global singleton instance
tunnel_manager = TunnelManager()
