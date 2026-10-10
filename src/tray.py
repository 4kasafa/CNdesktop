"""Entrypoint tray-only CNdesktop (tanpa console/taskbar, hanya tray-icon).

Menu: Buka Dashboard, Test Baca UIA, Keluar (satu-satunya exit).
Tooltip: CNdesktop <IP>:<port>. Single-instance via lock file.
Tanpa-console final via PyInstaller --noconsole (Fase 6); run dev pakai pythonw.
"""
import logging
import msvcrt
import os
import socket
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# ponytail: dijalankan sebagai file (pythonw src/tray.py) -> ROOT wajib di path

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


def make_icon_image():
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (64, 64), "darkgreen")
    d = ImageDraw.Draw(img)
    d.rectangle([8, 20, 56, 44], fill="white")
    d.text((18, 24), "CN", fill="darkgreen")
    return img


def main():
    from src import api
    from src.config import PORT, VERSION
    from src.dashboard import Dashboard
    from src.db import init_db
    from src.log import setup_logging
    from src.watcher import Watcher

    setup_logging()
    log.info("start CNdesktop v%s", VERSION)

    fh = acquire_single_instance()
    if fh is None:
        sys.exit(0)  # ponytail: instance kedua diam-diam keluar, tanpa popup

    import pystray

    db_path = init_db()
    port = PORT
    state = {"port": port, "server": None}

    watcher = Watcher(db_path=db_path)
    threading.Thread(target=watcher.run, daemon=True).start()

    def start_api(p):
        state["server"] = api.start_bg(db_path, p)

    start_api(port)

    def _restart_api(p):
        try:
            state["server"].shutdown()
        except Exception:
            pass
        state["port"] = p
        start_api(p)
        icon.title = f"CNdesktop v{VERSION} {lan_ip()}:{p}"

    dash = Dashboard(
        db_path, port,
        on_port_change=_restart_api,
        watcher_alive=lambda: watcher._run,
    )

    def show_dashboard(icon, item):
        dash.show()

    def test_read(icon, item):
        dash.show()
        dash.root.after(200, dash.run_test)  # ponytail: after refresh selesai

    def quit_app(icon, item):
        try:
            watcher.stop()
        except Exception:
            pass
        try:
            state["server"].shutdown()
        except Exception:
            pass
        icon.stop()
        try:
            dash.root.after(0, dash.root.destroy)
        except Exception:
            pass
        os._exit(0)  # ponytail: pump pesan watcher ikut mati, tanpa gantung

    icon = pystray.Icon(
        "cndesktop", make_icon_image(),
        title=f"CNdesktop v{VERSION} {lan_ip()}:{port}",
        menu=pystray.Menu(
            pystray.MenuItem("Buka Dashboard", show_dashboard,
                             default=True, visible=True),
            pystray.MenuItem("Test Baca UIA", test_read),
            pystray.MenuItem("Keluar", quit_app),
        ),
    )
    threading.Thread(target=icon.run, daemon=True).start()  # ponytail: Tk wajib main thread
    dash.root.mainloop()


if __name__ == "__main__":
    main()
