"""Dashboard minimal PRD §7 (tray-only). Tkinter stdlib, hide-bukan-exit.

Isi: status watcher, Ketoko terdeteksi/tidak, No Transaksi terakhir,
tabel 20 transaksi terakhir, setting port, tombol Test Baca UIA.
Tanpa laporan/reprint/hapus-edit.
"""
import ctypes
import sqlite3
import tkinter as tk
from tkinter import ttk
from ctypes import wintypes


def find_pembayaran_dialog():
    """hwnd dialog 'Pembayaran' milik KetokoD.exe, 0 jika tidak ada."""
    from src.pos_reader import KETOKO_PROCESS_NAME, get_window_process_name
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd, _):
        try:
            buf = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
            if buf.value == "Pembayaran" \
                    and get_window_process_name(hwnd).lower() == KETOKO_PROCESS_NAME.lower():
                found.append(hwnd)
        except Exception:
            pass
        return True

    try:
        ctypes.windll.user32.EnumWindows(_cb, 0)
    except Exception:
        pass
    return found[0] if found else 0


def ketoko_detected() -> bool:
    """True jika ada top-level window milik KetokoD.exe yang visible."""
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

    try:
        ctypes.windll.user32.EnumWindows(_cb, 0)
    except Exception:
        pass
    return bool(hit)


def default_test_read() -> dict:
    """Baca 4 field mentah dialog Pembayaran. '' per field jika tak ada."""
    from src.pos_reader import read_dialog
    hwnd = find_pembayaran_dialog()
    if not hwnd:
        return {"total_raw": "", "tunai_raw": "", "debit_raw": "", "bank_raw": "",
                "_note": "dialog Pembayaran tidak terbuka"}
    out = read_dialog(hwnd)
    out["_note"] = f"hwnd={hwnd}"
    return out


def last_no_transaksi(db_path: str) -> str:
    try:
        with sqlite3.connect(db_path) as c:
            row = c.execute(
                "SELECT no_transaksi FROM transactions ORDER BY id DESC LIMIT 1").fetchone()
            return row[0] if row else "-"
    except Exception:
        return "-"


def last_20(db_path: str) -> list[dict]:
    try:
        with sqlite3.connect(db_path) as c:
            c.row_factory = sqlite3.Row
            return [dict(r) for r in c.execute(
                "SELECT id,no_transaksi,total,tunai,nontunai,bank,kategori,created_at"
                " FROM transactions ORDER BY id DESC LIMIT 20")]
    except Exception:
        return []


class Dashboard:
    def __init__(self, db_path, port, on_port_change=None,
                 watcher_alive=None, test_read=None):
        self.db_path = db_path
        self.port = port
        self.on_port_change = on_port_change  # fn(new_port) -> None
        self.watcher_alive = watcher_alive or (lambda: True)
        self.test_read = test_read or default_test_read
        self.root = tk.Tk()
        self.root.title(f"CNdesktop :{port}")
        self.root.geometry("720x480")
        self.root.protocol("WM_DELETE_WINDOW", self.hide)  # tutup = hide
        self.root.withdraw()
        self._build()

    def _build(self):
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill="x")
        self.lbl_watcher = ttk.Label(top, text="watcher: ?")
        self.lbl_watcher.pack(side="left", padx=(0, 12))
        self.lbl_ketoko = ttk.Label(top, text="ketoko: ?")
        self.lbl_ketoko.pack(side="left", padx=(0, 12))
        self.lbl_last = ttk.Label(top, text="no terakhir: -")
        self.lbl_last.pack(side="left")

        tbl = ttk.Frame(self.root, padding=(8, 0))
        tbl.pack(fill="both", expand=True)
        cols = ("id", "no", "total", "tunai", "nontunai", "bank", "kategori", "created_at")
        self.tree = ttk.Treeview(tbl, columns=cols, show="headings", height=12)
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=80 if c != "created_at" else 140)
        self.tree.pack(fill="both", expand=True)

        bot = ttk.Frame(self.root, padding=8)
        bot.pack(fill="x")
        ttk.Label(bot, text="port:").pack(side="left")
        self.ent_port = ttk.Entry(bot, width=8)
        self.ent_port.insert(0, str(self.port))
        self.ent_port.pack(side="left", padx=4)
        ttk.Button(bot, text="Terapkan", command=self.apply_port).pack(side="left")
        ttk.Button(bot, text="Test Baca UIA", command=self.run_test).pack(side="left", padx=8)
        ttk.Button(bot, text="Refresh", command=self.refresh).pack(side="left")
        self.txt_test = tk.Text(self.root, height=5)
        self.txt_test.pack(fill="x", padx=8, pady=(0, 8))

    def apply_port(self):
        try:
            new = int(self.ent_port.get())
            if not 1 <= new <= 65535:
                raise ValueError
        except ValueError:
            self.txt_test.delete("1.0", "end")
            self.txt_test.insert("end", "port harus 1-65535")
            return
        self.port = new
        self.root.title(f"CNdesktop :{new}")
        if self.on_port_change:
            self.on_port_change(new)

    def run_test(self):
        try:
            out = self.test_read()
        except Exception as e:
            out = {"error": repr(e)}
        self.txt_test.delete("1.0", "end")
        for k in ("total_raw", "tunai_raw", "debit_raw", "bank_raw", "_note", "error"):
            if k in out:
                self.txt_test.insert("end", f"{k} = {out[k]!r}\n")

    def refresh(self):
        try:
            alive = self.watcher_alive()
        except Exception:
            alive = False
        self.lbl_watcher.config(text=f"watcher: {'jalan' if alive else 'mati'}")
        try:
            det = ketoko_detected()
        except Exception:
            det = False
        self.lbl_ketoko.config(text=f"ketoko: {'terdeteksi' if det else 'tidak'}")
        self.lbl_last.config(text=f"no terakhir: {last_no_transaksi(self.db_path)}")
        for r in self.tree.get_children():
            self.tree.delete(r)
        for t in last_20(self.db_path):
            self.tree.insert("", "end", values=(
                t["id"], t["no_transaksi"], t["total"], t["tunai"],
                t["nontunai"], t["bank"], t["kategori"], t["created_at"]))

    # ponytail: after(0) agar aman dipanggil dari thread tray-icon
    def show(self):
        self.root.after(0, self._show_ui)

    def _show_ui(self):
        self.refresh()
        self.root.deiconify()
        self.root.lift()

    def hide(self):
        self.root.after(0, self.root.withdraw)
