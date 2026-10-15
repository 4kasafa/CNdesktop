"""Entrypoint CNdesktop: tray GUI (default) atau --headless, plus `cnd` CLI.

CNdesktop.exe [--headless] [--port P] | CNdesktop.exe cnd <status|data|...>
Tanpa-console final via PyInstaller --noconsole; run dev pakai pythonw.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# ponytail: dijalankan sebagai file (pythonw src/tray.py) -> ROOT wajib di path

from src.service import (  # ponytail: re-ekspor kompatibel, tanpa GUI
    acquire_single_instance,
    lan_ip,
    lock_path,
)

__all__ = ["lock_path", "acquire_single_instance", "lan_ip", "main"]


def _pre_dispatch(argv):
    """Return 'cli'|'headless'|'tray'. Tanpa import GUI."""
    if "cnd" in argv[1:]:
        return "cli"
    if "--headless" in argv:
        return "headless"
    return "tray"


def _cli_args(argv):
    """Argumen sesudah kata cnd (flag tray sebelum cnd diabaikan mode CLI)."""
    return argv[argv.index("cnd") + 1:]


def _cli_port(argv, default):
    if "--port" not in argv:
        return default
    try:
        p = int(argv[argv.index("--port") + 1])
    except (ValueError, IndexError):
        p = -1
    if not 1 <= p <= 65535:
        print("GAGAL: --port harus integer 1-65535", file=sys.stderr)
        raise SystemExit(2)  # ponytail: typo port = teriak, bukan jalan di port salah
    return p


def main():
    from src.config import PORT
    mode = _pre_dispatch(sys.argv)
    if mode == "cli":
        from src.cli import main as cli_main
        sys.exit(cli_main(_cli_args(sys.argv)))
    if "--help" in sys.argv or "-h" in sys.argv:
        print("pakai: CNdesktop.exe [--headless] [--port P] | CNdesktop.exe cnd <cmd>")
        print("  cnd status|data|log|port|watcher|wipe|quit|pin  (cnd --help untuk detail)")
        return
    if mode == "headless":
        from src.service import run_headless
        run_headless(_cli_port(sys.argv, PORT))
        return

    import logging
    import threading
    from src.config import VERSION
    from src.dashboard import Dashboard
    from src.log import setup_logging
    from src.service import Service

    setup_logging()
    log = logging.getLogger("cndesktop")
    log.info("start CNdesktop v%s", VERSION)

    fh = acquire_single_instance()
    if fh is None:
        sys.exit(0)  # ponytail: instance kedua diam-diam keluar, tanpa popup

    import pystray

    svc = Service(port=_cli_port(sys.argv, PORT)).start()
    svc.run_forever(background=True)
    port = svc.port

    def _restart_api(p):
        svc.restart_port(p)
        icon.title = f"CNdesktop v{VERSION} {lan_ip()}:{svc.port}"

    dash = Dashboard(
        svc.db_path, port,
        on_port_change=_restart_api,
        watcher_alive=lambda: svc.watcher._run and svc.watcher.is_enabled(),
        watcher=svc.watcher,
    )

    def show_dashboard(icon, item):
        dash.show_calc()  # ponytail: depan = calculate, admin via Ctrl+Shift+Alt+D

    def test_read(icon, item):
        dash.show_admin()
        dash.root.after(200, dash.run_test)  # ponytail: after refresh selesai

    def quit_app(icon, item):
        try:
            svc.shutdown()
        except Exception:
            pass
        try:
            icon.stop()
        except Exception:
            pass
        try:
            dash.root.after(0, dash.root.destroy)
        except Exception:
            pass
        os._exit(0)  # ponytail: pump pesan watcher ikut mati, tanpa gantung

    icon = pystray.Icon(
        "cndesktop", _make_icon_image(),
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


def _make_icon_image():
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (64, 64), "darkgreen")
    d = ImageDraw.Draw(img)
    d.rectangle([8, 20, 56, 44], fill="white")
    d.text((18, 24), "CN", fill="darkgreen")
    return img


# ponytail: nama lama dipakai test/grep
def make_icon_image():
    return _make_icon_image()


if __name__ == "__main__":
    main()
