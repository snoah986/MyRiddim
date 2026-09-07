import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
backend_dir = ROOT / "backend"
static_dir = backend_dir / "static"

# Tauri's externalBin requires the target triple as a file-name suffix.
# Map the running machine to the triple expected by src-tauri/tauri.conf.json
# and the CI rename step so the script works on the machine it runs on.
TRIPLES = {
    ("win32", "AMD64"): "x86_64-pc-windows-msvc.exe",
    ("darwin", "arm64"): "aarch64-apple-darwin",
    ("darwin", "x86_64"): "x86_64-apple-darwin",
    ("linux", "x86_64"): "x86_64-unknown-linux-gnu",
}

key = (sys.platform, platform.machine())
triple = TRIPLES.get(key, "x86_64-pc-windows-msvc.exe")
if key not in TRIPLES:
    print(
        f"[build_sidecar] No known Tauri triple for {sys.platform}/{platform.machine()}; "
        f"defaulting to {triple}. Add your platform to TRIPLES."
    )

name = f"ytm-backend-{triple}"

cmd = [
    "pyinstaller",
    "--noconfirm",
    "--onefile",
    "--name", name,
    "--distpath", str(ROOT / "src-tauri" / "binaries"),
    "--paths", str(backend_dir),
    f"--add-data={static_dir}{os.pathsep}static",
    str(backend_dir / "app.py"),
]

print(f"Running sidecar build for {triple}: {' '.join(cmd)}")
subprocess.run(cmd, check=True)
