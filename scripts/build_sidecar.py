import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
backend_dir = ROOT / "backend"
static_dir = backend_dir / "static"

cmd = [
    "pyinstaller",
    "--noconfirm",
    "--onefile",
    "--name", "ytm-backend-x86_64-pc-windows-msvc",
    "--distpath", str(ROOT / "src-tauri" / "binaries"),
    "--paths", str(backend_dir),
    f"--add-data={static_dir}{os.pathsep}static",
    str(backend_dir / "app.py"),
]

print(f"Running sidecar build: {' '.join(cmd)}")
subprocess.run(cmd, check=True)
