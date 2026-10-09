"""Konfigurasi terpusat CNdesktop (proc/port/path DB/timing/log)."""
import os

APP_NAME = "CNdesktop"
PORT = 8765

KETOKO_PROCESS_NAME = "KetokoD.exe"
KETOKO_WINDOW_TITLE = "Ketoko.co.id"

LOCK_NAME = "cndesktop.lock"

# Watcher (PRD §2): idle hook + baca 250ms + worker 100ms + enum 5 dtk
READ_EVERY, BURST_EVERY, ENUM_EVERY = 0.25, 0.1, 5.0

# Logging geser (PRD §9)
LOG_FILE, LOG_MAX_BYTES, LOG_BACKUPS = "cndesktop.log", 512 * 1024, 5
LOG_SUBDIR = "logs"  # ponytail: join dengan app_dir() saat dipakai, tanpa side-effect import


def app_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, APP_NAME)
    os.makedirs(d, exist_ok=True)
    return d


DB_FILE = "data.db"  # ponytail: nama saja; path penuh via db.default_path()
