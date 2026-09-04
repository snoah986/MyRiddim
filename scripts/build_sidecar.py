#!/usr/bin/env python3
"""Build the PyInstaller sidecar that ships with the Tauri desktop app.

Usage:  python scripts/build_sidecar.py

Output: src-tauri/binaries/ytm-backend-<target-triple>(.exe) — the exact name
Tauri's externalBin configuration expects. PyInstaller is imported lazily so
the error message stays actionable on machines without it.
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIDECAR_DIR = ROOT / "src-tauri" / "binaries"


def main() -> int:
    if shutil.which("pyinstaller") is None:
        print("pyinstaller is not installed. Run: pip install pyinstaller", file=sys.stderr)
        return 1

    SIDECAR_DIR.mkdir(parents=True, exist_ok=True)

    # Target triple must match the building machine; Tauri appends it to
    # externalBin names at bundle time.
    import platform

    machine = platform.machine().lower()
    arch = "aarch64" if "arm" in machine else "x86_64"
    triple = f"{arch}-pc-windows-msvc" if sys.platform == "win32" else f"{arch}-unknown-linux-gnu"
    name = f"ytm-backend-{triple}" + (".exe" if sys.platform == "win32" else "")

    command = [
        "pyinstaller",
        "--noconfirm",
        "--onedir",
        "--name", f"ytm-backend-{triple}",
        "--distpath", str(SIDECAR_DIR),
        "--workpath", str(ROOT / "build" / "sidecar"),
        "--specpath", str(ROOT / "build" / "sidecar"),
        "--paths", str(ROOT / "backend"),
        # backend/ is also bundled as a Tauri resource (dev fallback + assets).
        "--add-data", f"{ROOT / 'backend' / 'static'}{';' if sys.platform == 'win32' else ':'}{ROOT / 'backend' / 'static'}",
        str(ROOT / "backend" / "app.py"),
    ]
    print("Running:", " ".join(command))
    result = subprocess.run(command)
    if result.returncode != 0:
        return result.returncode

    # PyInstaller appends .exe to the --name; the onedir output lives in a
    # folder of the same name. Tauri expects the executable file itself.
    produced = SIDECAR_DIR / f"ytm-backend-{triple}" / f"ytm-backend-{triple}{'.exe' if sys.platform == 'win32' else ''}"
    final = SIDECAR_DIR / f"ytm-backend-{triple}{'.exe' if sys.platform == 'win32' else ''}"
    if produced.is_file():
        shutil.move(produced, final)
        shutil.rmtree(SIDECAR_DIR / f"ytb-backend-{triple}", ignore_errors=True)
        shutil.rmtree(SIDECAR_DIR / f"ytm-backend-{triple}", ignore_errors=True)
    if not final.is_file():
        print(f"Expected sidecar not found at {final}", file=sys.stderr)
        return 1
    print(f"Sidecar ready: {final}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
