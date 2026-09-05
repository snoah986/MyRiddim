"""Best-effort public tunnel lifecycle for Party Mode guests.

The tunnel is intentionally optional. The desktop app remains usable without
cloudflared/localtunnel; the frontend then falls back to its current origin.
"""
from __future__ import annotations

import atexit
import os
import re
import shutil
import subprocess
import threading
import time
from typing import Optional


_PUBLIC_URL_RE = re.compile(
    r"https://[a-z0-9][a-z0-9-]*\.(?:trycloudflare\.com|loca\.lt)(?:/[^\s]*)?",
    re.IGNORECASE,
)


class TunnelManager:
    """Own one optional public tunnel process and its discovered URL."""

    def __init__(self, port: int = 5193) -> None:
        self.port = int(port)
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._process: Optional[subprocess.Popen] = None
        self._public_url: Optional[str] = None
        self._provider: Optional[str] = None

    @property
    def public_url(self) -> Optional[str]:
        with self._lock:
            return self._public_url

    @property
    def provider(self) -> Optional[str]:
        with self._lock:
            return self._provider

    def _set_url(self, url: str, provider: str) -> None:
        with self._lock:
            self._public_url = url.rstrip("/")
            self._provider = provider
        print(f"Party tunnel ready: {self._public_url}", flush=True)

    def _commands(self):
        mode = os.environ.get("YTM_TUNNEL", "auto").strip().lower()
        if mode in {"off", "none", "disabled", "0"}:
            return []
        commands = []
        cloudflared = shutil.which("cloudflared") or shutil.which("cloudflared.exe")
        npx = shutil.which("npx") or shutil.which("npx.cmd")
        target = f"http://127.0.0.1:{self.port}"
        if mode in {"auto", "cloudflared"} and cloudflared:
            commands.append(("cloudflared", [cloudflared, "tunnel", "--url", target, "--no-autoupdate"]))
        if mode in {"auto", "localtunnel", "loca.lt"} and npx:
            commands.append(("localtunnel", [npx, "--yes", "localtunnel", "--port", str(self.port)]))
        return commands

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        commands = self._commands()
        if not commands:
            print("Party tunnel unavailable: install cloudflared or enable npx localtunnel", flush=True)
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, args=(commands,), name="party-tunnel", daemon=True)
        self._thread.start()

    def _run(self, commands) -> None:
        for provider, command in commands:
            if self._stop_event.is_set():
                return
            process = None
            try:
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                with self._lock:
                    self._process = process
                while not self._stop_event.is_set():
                    line = process.stdout.readline() if process.stdout else ""
                    if line:
                        match = _PUBLIC_URL_RE.search(line)
                        if match and not self.public_url:
                            self._set_url(match.group(0), provider)
                    elif process.poll() is not None:
                        break
                    else:
                        time.sleep(0.1)
            except (OSError, ValueError) as exc:
                print(f"Party {provider} tunnel failed: {exc}", flush=True)
            finally:
                if process is not None:
                    self._terminate_process(process)
                with self._lock:
                    if self._process is process:
                        self._process = None
            if self.public_url or self._stop_event.is_set():
                return

    @staticmethod
    def _terminate_process(process) -> None:
        if process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            try:
                process.kill()
                process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                pass

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            process = self._process
        if process is not None:
            self._terminate_process(process)
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=4)
        with self._lock:
            self._process = None
            self._thread = None
            self._public_url = None
            self._provider = None


TUNNEL_MANAGER = TunnelManager(int(os.environ.get("YTM_VITE_PORT", "5193")))
atexit.register(TUNNEL_MANAGER.stop)
