"""Pasang CNdesktop ke Startup folder Windows (tray otomatis tiap login).

Target: dist/CNdesktop.exe bila ada (hasil build Fase 6),
fallback dev: pythonw.exe src/tray.py. Stdlib saja (via PowerShell COM).
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = "CNdesktop.lnk"


def startup_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Microsoft", "Windows", "Start Menu",
                        "Programs", "Startup")


def target() -> tuple[str, str]:
    """(exe_target, workdir). EXE bila sudah di-build, else pythonw dev."""
    exe = os.path.join(ROOT, "dist", "CNdesktop.exe")
    if os.path.exists(exe):
        return exe, ROOT
    venv_py = os.path.join(ROOT, "venv", "Scripts", "pythonw.exe")
    if os.path.exists(venv_py):  # ponytail: deps hanya ada di venv
        return venv_py, ROOT
    return os.path.join(sys.base_prefix, "pythonw.exe"), ROOT


def install() -> str:
    exe, workdir = target()
    args = "" if exe.lower().endswith(".exe") and "pythonw" not in exe.lower() \
        else f'"{os.path.join(ROOT, "src", "tray.py")}"'
    lnk = os.path.join(startup_dir(), NAME)
    ps = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}');"
          f"$s.TargetPath='{exe}';$s.Arguments='{args}';"
          f"$s.WorkingDirectory='{workdir}';$s.Save()")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
    return f"{lnk} -> {exe} {args}".strip()


if __name__ == "__main__":
    print(install())
