"""Core headless CNdesktop: lock + watcher + API tanpa GUI.

Dipakai mode tray (tray.py) dan --headless. Tanpa import pystray/customtkinter.
"""
import logging
import msvcrt
import os
import socket
import sqlite3
import threading
import time

log = logging.getLogger("cndesktop")


def lock_path() -> str:
    from src.config import LOCK_NAME
    from src.db import default_path
    return os.path.join(os.path.dirname(default_path()), LOCK_NAME)


def acquire_single_instance():
    """Return handle terkunci, atau None jika sudah ada instance jalan."""
    os.makedirs(os.path.dirname(lock_path()), exist_ok=True)
    fh = open(lock_path(), "w")
    try:
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        fh.close()
        return None
    return fh  # ponytail: tahan handle selama proses hidup


def lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # ponytail: tanpa kirim paket, cuma pilih route
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def ketoko_detected() -> bool:
    """Best-effort tanpa GUI: True jika window KetokoD.exe visible. Gagal = False."""
    try:
        import ctypes
        from ctypes import wintypes
        from src.pos_reader import KETOKO_PROCESS_NAME, get_window_process_name
        hit = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def _cb(hwnd, _):
            try:
                if ctypes.windll.user32.IsWindowVisible(hwnd) \
                        and get_window_process_name(hwnd).lower() == KETOKO_PROCESS_NAME.lower():
                    hit.append(hwnd)
            except Exception:
                pass
            return True

        ctypes.windll.user32.EnumWindows(_cb, 0)
        return bool(hit)
    except Exception:
        return False


def _db_stats(db_path: str) -> tuple:
    """(last_no, count_today). Gagal = ('-', 0). Tanpa import dashboard."""
    last, today = "-", 0
    try:
        with sqlite3.connect(db_path) as c:
            try:
                row = c.execute(
                    "SELECT no_transaksi FROM transactions ORDER BY id DESC LIMIT 1").fetchone()
                last = row[0] if row else "-"
            except Exception:
                pass
            try:
                row = c.execute(
                    "SELECT COUNT(*) FROM transactions "
                    "WHERE date(created_at) = date('now','localtime')").fetchone()
                today = int(row[0]) if row else 0
            except Exception:
                pass
    except Exception:
        pass
    return last, today


class Service:
    """Hidupkan watcher + HTTP API. restart_port dipakai tray dan POST /api/port."""

    def __init__(self, db_path=None, port=None):
        from src.config import PORT
        self.db_path = db_path
        self.port = port or PORT
        self.watcher = None
        self.server = None
        self._lock = threading.Lock()
        self._t0 = time.monotonic()

    def start(self):
        from src import api
        from src.db import init_db
        from src.watcher import Watcher
        self.db_path = init_db(self.db_path)
        self.watcher = Watcher(db_path=self.db_path)
        self.server = api.start_bg(self.db_path, self.port, watcher=self.watcher,
                                   service=self)
        return self

    def run_forever(self, background=False):
        """Jalankan pump watcher. background=True untuk mode tray (daemon thread).

        Wajib dipanggil SEKALI per Service: tiap run() pasang hook+worker baru,
        dan pemanggilan ganda membuat ref callback pertama ter-GC -> crash
        STATUS_FATAL_USER_CALLBACK_EXCEPTION.
        """
        if background:
            threading.Thread(target=self.watcher.run, daemon=True).start()
        else:
            self.watcher.run()  # ponytail: pump pesan di main thread

    def restart_port(self, new_port: int):
        from src import api
        new_port = int(new_port)
        if not 1 <= new_port <= 65535:
            raise ValueError("port harus 1-65535")
        with self._lock:
            try:
                if self.server is not None:
                    self.server.shutdown()
            except Exception:
                pass
            self.port = new_port
            self.server = api.start_bg(self.db_path, new_port,
                                       watcher=self.watcher, service=self)
        return new_port

    def uptime_s(self) -> float:
        try:
            return max(0.0, time.monotonic() - self._t0)
        except Exception:
            return 0.0

    def status(self) -> dict:
        from src.config import VERSION
        try:
            enabled = self.watcher.is_enabled() if self.watcher is not None else True
        except Exception:
            enabled = True
        try:
            alive = bool(self.watcher._run and self.watcher.is_enabled()) \
                if self.watcher is not None else False
        except Exception:
            alive = False
        try:
            busy = bool(self.watcher.db_busy()) if self.watcher is not None else False
        except Exception:
            busy = False
        last, today = _db_stats(self.db_path) if self.db_path else ("-", 0)
        return {
            "version": VERSION,
            "ip": lan_ip(),
            "port": self.port,
            "watcher_enabled": bool(enabled),
            "watcher_alive": bool(alive),
            "db_busy": bool(busy),
            "ketoko": ketoko_detected(),
            "last_no": last,
            "count_today": today,
            "uptime_s": round(self.uptime_s(), 1),
        }

    def shutdown(self):
        try:
            if self.watcher is not None:
                self.watcher.stop()
        except Exception:
            pass
        try:
            if self.server is not None:
                self.server.shutdown()
        except Exception:
            pass


def run_headless(port=None):
    """Blokir: watcher pump di main thread, API di bg. Ctrl+C / POST shutdown keluar."""
    import os
    import sys
    from src.config import PORT, VERSION
    from src.log import setup_logging
    setup_logging()
    svc = Service(port=port or PORT)
    fh = acquire_single_instance()
    if fh is None:
        print("CNdesktop sudah jalan (lock aktif).", flush=True)
        sys.exit(0)
    svc.start()
    log.info("start CNdesktop v%s --headless %s:%s", VERSION, lan_ip(), svc.port)
    print(f"CNdesktop v{VERSION} headless {lan_ip()}:{svc.port}", flush=True)
    try:
        svc.run_forever()  # ponytail: pump pesan di main thread, worker ikut hidup
    except KeyboardInterrupt:
        pass
    finally:
        svc.shutdown()
        os._exit(0)
