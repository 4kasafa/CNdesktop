"""Dashboard CNdesktop: UI calculate di depan, admin tersembunyi.

Pola meniru cash_note tabs/calculate_tab.py: satu window berisi view yang
ditukar (input <-> preview), admin dibuka via Ctrl+Shift+Alt+D.
Total Penjualan = Fisik+Nontunai+Pengeluaran; kasir dropdown dari tabel
SQLite cashiers + tombol Kasir membuka modal kelola (tambah/edit/hapus);
preview + Cetak TANPA simpan, sesudah cetak nilai tetap diam di preview.
"""
import ctypes
import os
import sqlite3
import tempfile
from ctypes import wintypes
from datetime import datetime
from tkinter import messagebox, ttk

import customtkinter as ctk

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

# Palet ala cash_note/constants.py (disalin agar mirip, tanpa file baru).
BG_COLOR = "#f8f9fc"
SIDEBAR_COLOR = "#ffffff"
CONSOLE_COLOR = "#ffffff"
TEXT_COLOR = "#2d2d2d"
ACCENT_COLOR = "#4e73df"
BORDER_COLOR = "#d1d3e2"
STATUS_PAID_BG = "#90ee90"
HEADER_FONT = ("Segoe UI", 16, "bold")
MAIN_FONT = ("Segoe UI", 11)
SMALL_FONT = ("Segoe UI", 10)

from src.receipt import (  # ponytail: murni headless, dipakai api juga + re-ekspor test
    ARABIC_ESC_POS_IMAGE_B64, DENOMINATIONS, KASIR_EMPTY, KASIR_PLACEHOLDER,
    build_escpos_arabic_image, build_escpos_receipt, build_receipt_text,
    format_rp, hitung_total, print_width, process_print_job, validate_calc,
)
from src import receipt


# --- fungsi lama (dipakai admin_view, logika tak berubah) ---

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
            try:
                rows = c.execute(
                    "SELECT id,no_transaksi,no_urut,total,tunai,nontunai,bank,kategori,created_at"
                    " FROM transactions ORDER BY id DESC LIMIT 20")
            except sqlite3.OperationalError:  # ponytail: DB skema lama pra-v1.1.0
                rows = c.execute(
                    "SELECT id,no_transaksi,total,tunai,nontunai,bank,kategori,created_at"
                    " FROM transactions ORDER BY id DESC LIMIT 20")
            return [dict(r) for r in rows]
    except Exception:
        return []


def check_watcher_pin(db_path: str, pin: str) -> bool:
    """True jika PIN cocok dengan PIN tersimpan (default 363636). Murni, tanpa GUI."""
    from src.db import get_wipe_pin
    try:
        return (pin or "").strip() == get_wipe_pin(db_path)
    except Exception:
        return (pin or "").strip() == "363636"


def validate_new_pin(pin: str) -> str | None:
    """Return pesan error, atau None jika PIN 6-digit valid. Murni."""
    from src.db import validate_pin
    return validate_pin(pin)


def watcher_status_text(enabled: bool, alive: bool) -> str:
    """Teks lbl_watcher: mati jika paused, walau thread hidup. Murni."""
    if not enabled:
        return "watcher: mati"
    return f"watcher: {'jalan' if alive else 'mati'}"


class Dashboard:
    def __init__(self, db_path, port, on_port_change=None,
                 watcher_alive=None, test_read=None, watcher=None):
        from src.config import VERSION
        self.db_path = db_path
        self.port = port
        self.on_port_change = on_port_change  # fn(new_port) -> None
        self.watcher_alive = watcher_alive or (lambda: True)
        self.test_read = test_read or default_test_read
        self._watcher = watcher  # ponytail: toggle persist via watcher.set_enabled

        self.root = ctk.CTk()
        self.root.title(f"CNdesktop v{VERSION} :{port}")
        self.root.geometry("400x550")
        self.root.minsize(400, 550)
        self.root.configure(fg_color=BG_COLOR)
        self.root.protocol("WM_DELETE_WINDOW", self.hide)  # tutup = hide
        self.root.withdraw()

        self.inputs = {}
        self.subtotal_labels = {}
        self.expense_amount = 0
        self.expense_note = ""
        self.nontunai_amount = 0
        self.vcmd = (self.root.register(self.validate_numeric), "%P")
        self.print_size_var = ctk.StringVar(value="58")
        self.cashier_var = ctk.StringVar(value=KASIR_PLACEHOLDER)
        self.cashiers = []  # list dict rowid/kasir_id/name/branch/shift (SQLite)
        self.active_cashier = None
        self._editing_rowid = None
        self.kasir_dialog = None

        self._build()
        # Ctrl+Shift+Alt+D (juga tanpa Shift): buka/tutup admin tersembunyi.
        self.root.bind_all("<Control-Alt-D>", lambda e: self.toggle_admin())
        self.root.bind_all("<Control-Alt-d>", lambda e: self.toggle_admin())
        self.root.bind("<Escape>", self.handle_escape)

    @staticmethod
    def validate_numeric(P):
        return P == "" or P.isdigit()

    # --- view switching (mirip show_tab / show_preview cash_note) ---

    def _show_only(self, view):
        for v in (self.calc_view, self.admin_view):
            v.pack_forget()
        for v in (self.input_view, self.preview_view):
            v.pack_forget()
        if view in (self.input_view, self.preview_view):
            self.calc_view.pack(fill="both", expand=True)
            view.pack(fill="both", expand=True)
        else:
            view.pack(fill="both", expand=True)

    def show_calc(self):
        self.root.after(0, self._show_calc_ui)

    def _show_calc_ui(self):
        self._refresh_date()
        self.load_cashiers()
        self._show_only(self.input_view)
        self.root.deiconify()
        self.root.lift()

    def show(self):
        """Kompatibel tray lama: buka calculate depan."""
        self.show_calc()

    def show_admin(self):
        self.root.after(0, self._show_admin_ui)

    def _show_admin_ui(self):
        self.refresh()
        self._show_only(self.admin_view)
        self.root.deiconify()
        self.root.lift()

    def toggle_admin(self):
        if self.admin_view.winfo_ismapped():
            self._show_calc_ui()
        else:
            self._show_admin_ui()

    def handle_escape(self, event=None):
        if self.admin_view.winfo_ismapped():
            self._show_calc_ui()
        elif self.preview_view.winfo_ismapped():
            self.show_input_view()

    def hide(self):
        self.root.after(0, self.root.withdraw)

    # --- build ---

    def _build(self):
        self.main_container = ctk.CTkFrame(self.root, fg_color="transparent", corner_radius=0)
        self.main_container.pack(fill="both", expand=True)
        self.calc_view = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.admin_view = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.input_view = ctk.CTkFrame(self.calc_view, fg_color="transparent")
        self.preview_view = ctk.CTkFrame(self.calc_view, fg_color="transparent")
        self._build_calc()
        self._build_preview()
        self._build_admin()
        self._show_only(self.input_view)

    def _build_calc(self):
        header = ctk.CTkFrame(self.input_view, fg_color=SIDEBAR_COLOR,
                              border_width=1, border_color=BORDER_COLOR, corner_radius=8)
        header.pack(fill="x", padx=20, pady=10)
        top = ctk.CTkFrame(header, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(12, 6))
        self.lbl_date = ctk.CTkLabel(top, text="Tanggal: -",
                                     font=("Segoe UI", 11, "bold"), text_color=ACCENT_COLOR)
        self.lbl_date.pack(side="left")
        self._refresh_date()

        kasir_row = ctk.CTkFrame(header, fg_color="transparent")
        kasir_row.pack(fill="x", padx=20, pady=(0, 8))
        self.cashier_menu = ctk.CTkOptionMenu(
            kasir_row, variable=self.cashier_var, values=[KASIR_PLACEHOLDER],
            fg_color=SIDEBAR_COLOR, text_color=TEXT_COLOR,
            button_color="#f0f0f0", button_hover_color="#e0e0e0",
            dropdown_fg_color=SIDEBAR_COLOR, dropdown_text_color=TEXT_COLOR,
            dropdown_hover_color="#f5f5f5", corner_radius=10, anchor="w",
            height=38, font=("Segoe UI", 11), command=self.on_select_cashier)
        self.cashier_menu.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(kasir_row, text="Kasir", width=80, height=38,
                      fg_color=ACCENT_COLOR, hover_color="#375a7f",
                      text_color="white", corner_radius=10,
                      font=("Segoe UI", 11, "bold"),
                      command=self.show_kasir_modal).pack(side="left", padx=(8, 0))
        self.load_cashiers()

        self.expense_container = ctk.CTkFrame(header, fg_color="transparent")
        self.expense_container.pack(fill="x", padx=20, pady=(0, 12))
        self.render_expense_section()

        scroll = ctk.CTkScrollableFrame(self.input_view, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=15)
        for denom in DENOMINATIONS:
            row = ctk.CTkFrame(scroll, fg_color=SIDEBAR_COLOR, border_width=1,
                               border_color=BORDER_COLOR, corner_radius=8)
            row.pack(fill="x", pady=3, padx=5)
            ctk.CTkLabel(row, text=f"{denom:,}".replace(",", "."),
                         font=("Segoe UI", 12, "bold"),
                         width=80, anchor="w").pack(side="left", padx=15, pady=10)
            entry = ctk.CTkEntry(row, placeholder_text="0", width=80, justify="center",
                                 fg_color=CONSOLE_COLOR, border_color=BORDER_COLOR,
                                 validate="key", validatecommand=self.vcmd)
            entry.pack(side="left", padx=10)
            entry.bind("<KeyRelease>", lambda e, d=denom: self.update_subtotal(d))
            self.inputs[denom] = entry
            sub = ctk.CTkLabel(row, text="Rp 0", font=("Segoe UI", 11, "bold"),
                               text_color=ACCENT_COLOR, anchor="e")
            sub.pack(side="right", padx=15)
            self.subtotal_labels[denom] = sub

        footer = ctk.CTkFrame(self.input_view, fg_color="transparent")
        footer.pack(fill="x", padx=20, pady=10)
        total_frame = ctk.CTkFrame(footer, fg_color=STATUS_PAID_BG, border_width=1,
                                   border_color=BORDER_COLOR, corner_radius=8)
        total_frame.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(total_frame, text="Total Keseluruhan:",
                     font=("Segoe UI", 14, "bold"), text_color="black").pack(
                         side="left", padx=15, pady=10)
        self.lbl_grand_total = ctk.CTkLabel(total_frame, text="Rp 0",
                                            font=("Segoe UI", 16, "bold"),
                                            text_color="black")
        self.lbl_grand_total.pack(side="right", padx=15, pady=10)

        nontunai_frame = ctk.CTkFrame(footer, fg_color=SIDEBAR_COLOR, border_width=1,
                                      border_color=BORDER_COLOR, corner_radius=8)
        nontunai_frame.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(nontunai_frame, text="Nontunai:",
                     font=("Segoe UI", 12, "bold"), text_color=TEXT_COLOR).pack(
                         side="left", padx=15, pady=8)
        self.nontunai_entry = ctk.CTkEntry(nontunai_frame, placeholder_text="0",
                                           width=120, justify="center",
                                           fg_color=CONSOLE_COLOR,
                                           border_color=BORDER_COLOR,
                                           validate="key", validatecommand=self.vcmd)
        self.nontunai_entry.pack(side="right", padx=15, pady=8)
        self.nontunai_entry.bind("<KeyRelease>", self.update_nontunai)

        btn_box = ctk.CTkFrame(footer, fg_color="transparent")
        btn_box.pack(fill="x")
        ctk.CTkButton(btn_box, text="Pratinjau", fg_color=ACCENT_COLOR,
                      text_color="white", corner_radius=5,
                      command=self.show_preview).pack(side="left", expand=True, padx=5)
        ctk.CTkButton(btn_box, text="Reset Semua", fg_color="#666666",
                      text_color="white", corner_radius=5,
                      command=self.clear_all).pack(side="left", expand=True, padx=5)

    def _build_preview(self):
        phead = ctk.CTkFrame(self.preview_view, fg_color="transparent")
        phead.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(phead, text="Pratinjau Struk", font=HEADER_FONT,
                     text_color=TEXT_COLOR).pack(side="left")
        ctk.CTkButton(phead, text="Kembali", width=60, fg_color="#666666",
                      text_color="white",
                      command=self.show_input_view).pack(side="right")

        receipt_scroll = ctk.CTkScrollableFrame(self.preview_view, fg_color="#e0e0e0",
                                                corner_radius=0)
        receipt_scroll.pack(fill="both", expand=True, padx=20)
        self.receipt_paper = ctk.CTkFrame(receipt_scroll, fg_color="white",
                                          corner_radius=0, border_width=1,
                                          border_color="#ccc")
        self.receipt_paper.pack(pady=20)
        self.lbl_receipt_text = ctk.CTkLabel(self.receipt_paper, text="",
                                             font=("Courier New", 12), justify="left",
                                             text_color="black", padx=0, pady=20)
        self.lbl_receipt_text.pack()

        pfoot = ctk.CTkFrame(self.preview_view, fg_color=SIDEBAR_COLOR,
                             border_width=1, border_color=BORDER_COLOR)
        pfoot.pack(fill="x", side="bottom")
        size_frame = ctk.CTkFrame(pfoot, fg_color="transparent")
        size_frame.pack(pady=5)
        ctk.CTkLabel(size_frame, text="Ukuran Cetak:",
                     font=SMALL_FONT).pack(side="left", padx=10)
        ctk.CTkRadioButton(size_frame, text="58mm", variable=self.print_size_var,
                           value="58",
                           command=self.update_receipt_preview).pack(side="left", padx=5)
        ctk.CTkRadioButton(size_frame, text="80mm", variable=self.print_size_var,
                           value="80",
                           command=self.update_receipt_preview).pack(side="left", padx=5)
        ctk.CTkButton(pfoot, text="Cetak", fg_color="#2e7d32", text_color="white",
                      height=45, corner_radius=5, font=("Segoe UI", 12, "bold"),
                      command=self.cetak).pack(fill="x", padx=40, pady=10)

    def _build_admin(self):
        """Isi dashboard lama, dipindah ke view tersembunyi."""
        top = ctk.CTkFrame(self.admin_view, fg_color=SIDEBAR_COLOR, border_width=1,
                           border_color=BORDER_COLOR, corner_radius=8)
        top.pack(fill="x", padx=12, pady=8)
        self.lbl_watcher = ctk.CTkLabel(top, text="watcher: ?")
        self.lbl_watcher.pack(side="left", padx=(12, 12), pady=8)
        self.lbl_ketoko = ctk.CTkLabel(top, text="ketoko: ?")
        self.lbl_ketoko.pack(side="left", padx=(0, 12))
        self.lbl_last = ctk.CTkLabel(top, text="no terakhir: -")
        self.lbl_last.pack(side="left")

        tbl = ctk.CTkFrame(self.admin_view, fg_color="transparent")
        tbl.pack(fill="both", expand=True, padx=12)
        cols = ("id", "no", "urut", "total", "tunai", "nontunai",
                "bank", "kategori", "created_at")
        self.tree = ttk.Treeview(tbl, columns=cols, show="headings", height=12)
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=80 if c != "created_at" else 140)
        self.tree.pack(fill="both", expand=True)

        bot = ctk.CTkFrame(self.admin_view, fg_color=SIDEBAR_COLOR, border_width=1,
                           border_color=BORDER_COLOR, corner_radius=8)
        bot.pack(fill="x", padx=12, pady=8)
        row1 = ctk.CTkFrame(bot, fg_color="transparent")
        row1.pack(fill="x", padx=8, pady=(8, 4))
        ctk.CTkLabel(row1, text="port:").pack(side="left")
        self.ent_port = ctk.CTkEntry(row1, width=80)
        self.ent_port.insert(0, str(self.port))
        self.ent_port.pack(side="left", padx=4)
        ctk.CTkButton(row1, text="Terapkan", width=80,
                      command=self.apply_port).pack(side="left")
        ctk.CTkButton(row1, text="Test Baca UIA",
                      command=self.run_test).pack(side="left", padx=8)
        ctk.CTkButton(row1, text="Refresh",
                      command=self.refresh).pack(side="left")
        ctk.CTkButton(row1, text="Buka Log",
                      command=self.open_log).pack(side="left", padx=8)
        row2 = ctk.CTkFrame(bot, fg_color="transparent")
        row2.pack(fill="x", padx=8, pady=(0, 8))
        ctk.CTkButton(row2, text="Hapus Transaksi", fg_color="#d32f2f",
                      hover_color="#b71c1c", text_color="white",
                      command=self.confirm_clear_transactions).pack(side="left")
        ctk.CTkButton(row2, text="Watcher On/Off",
                      command=self.toggle_watcher).pack(side="left", padx=8)
        row3 = ctk.CTkFrame(bot, fg_color="transparent")
        row3.pack(fill="x", padx=8, pady=(0, 8))
        ctk.CTkLabel(row3, text="PIN baru:").pack(side="left")
        self.ent_pin = ctk.CTkEntry(row3, width=100, show="*")
        self.ent_pin.pack(side="left", padx=4)
        ctk.CTkButton(row3, text="Simpan PIN", width=90,
                      command=self.change_pin).pack(side="left")
        self.txt_test = ctk.CTkTextbox(bot, height=90)
        self.txt_test.pack(fill="x", padx=8, pady=(0, 8))

    # --- calculate logic ---

    def _refresh_date(self):
        try:
            self.lbl_date.configure(
                text=f"Tanggal: {datetime.now().strftime('%d/%m/%Y')}")
        except Exception:
            pass

    def _qty_map(self) -> dict:
        out = {}
        for d in DENOMINATIONS:
            try:
                out[d] = int(self.inputs[d].get() or 0)
            except (ValueError, TypeError):
                out[d] = 0
        return out

    def update_subtotal(self, denom):
        try:
            qty = int(self.inputs[denom].get() or 0)
        except (ValueError, TypeError):
            qty = 0
        self.subtotal_labels[denom].configure(text=format_rp(qty * denom))
        self.lbl_grand_total.configure(text=format_rp(hitung_total(self._qty_map())))

    def _nontunai_amount(self) -> int:
        try:
            return int((self.nontunai_entry.get() or 0))
        except (ValueError, TypeError, AttributeError):
            try:
                return int(self.nontunai_amount or 0)
            except (ValueError, TypeError):
                return 0

    def update_nontunai(self, event=None):
        try:
            self.nontunai_amount = int(self.nontunai_entry.get() or 0)
        except (ValueError, TypeError):
            self.nontunai_amount = 0
        try:
            self.update_receipt_preview()
        except Exception:
            pass

    # --- kasir (dropdown SQLite + modal kelola) ---

    def load_cashiers(self):
        from src.db import list_cashiers
        try:
            self.cashiers = list_cashiers(self.db_path)
        except Exception:
            self.cashiers = []
        names = [c["name"] for c in self.cashiers]
        try:
            if names:
                self.cashier_menu.configure(values=names)
                if self.cashier_var.get() not in names:
                    self.cashier_var.set(KASIR_PLACEHOLDER)
            else:
                self.cashier_menu.configure(values=[KASIR_EMPTY])
                self.cashier_var.set(KASIR_EMPTY)
        except Exception:
            pass
        self._sync_active_cashier()

    def on_select_cashier(self, name):
        self._sync_active_cashier()

    def _sync_active_cashier(self):
        sel = self.cashier_var.get()
        # ponytail: nama boleh kembar -> cocok pertama menang
        self.active_cashier = next((c for c in self.cashiers if c["name"] == sel),
                                   None)

    def kasir_name(self) -> str:
        if self.cashier_var.get() in (KASIR_PLACEHOLDER, KASIR_EMPTY):
            return ""
        ac = self.active_cashier
        return (ac["name"] if ac else "").strip()

    def receipt_identity(self) -> tuple:
        """(kasir, branch, shift, user_id) untuk struk; default '-'."""
        ac = self.active_cashier
        if not ac:
            return ("-", "-", "-", "-")
        return (ac["name"] or "-", ac.get("branch") or "-",
                ac.get("shift") or "-", ac.get("kasir_id") or "-")

    def show_preview(self):
        err = validate_calc(self.kasir_name(),
                            hitung_total(self._qty_map()) + self._nontunai_amount())
        if err:
            messagebox.showwarning("Data Tidak Lengkap", err)
            return
        self._show_only(self.preview_view)
        self.update_receipt_preview()

    def show_input_view(self):
        self._show_only(self.input_view)

    # --- modal kelola kasir (mirip UserTab cash_note: list <-> form) ---

    def show_kasir_modal(self):
        try:
            if self.kasir_dialog is not None and self.kasir_dialog.winfo_exists():
                self.kasir_dialog.lift()
                self.kasir_dialog.focus()
                return
        except Exception:
            pass
        from src.db import list_cashiers
        try:
            self.cashiers = list_cashiers(self.db_path)
        except Exception:
            self.cashiers = []
        dialog = ctk.CTkToplevel(self.root)
        self.kasir_dialog = dialog
        dialog.title("Kelola Kasir")
        dialog.geometry("380x480")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - 380) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - 480) // 2
        dialog.geometry(f"+{max(0, x)}+{max(0, y)}")
        dialog.protocol("WM_DELETE_WINDOW", self.close_kasir_modal)
        dialog.bind("<Escape>", lambda e: self.close_kasir_modal())

        self.kasir_list_view = ctk.CTkFrame(dialog, fg_color="transparent")
        self.kasir_list_view.pack(fill="both", expand=True)
        top = ctk.CTkFrame(self.kasir_list_view, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(15, 5))
        ctk.CTkLabel(top, text="Data Kasir", font=HEADER_FONT,
                     text_color=TEXT_COLOR).pack(side="left")
        ctk.CTkButton(top, text="+ Tambah", width=100, height=30,
                      fg_color=ACCENT_COLOR, hover_color="#375a7f",
                      text_color="white", corner_radius=6, font=SMALL_FONT,
                      command=self.show_kasir_add_form).pack(side="right")
        self.kasir_scroll = ctk.CTkScrollableFrame(
            self.kasir_list_view, fg_color=CONSOLE_COLOR, border_width=1,
            border_color=BORDER_COLOR, corner_radius=0)
        self.kasir_scroll.pack(fill="both", expand=True, padx=20, pady=(5, 10))
        ctk.CTkButton(self.kasir_list_view, text="Tutup", fg_color="#666666",
                      text_color="white", corner_radius=5,
                      command=self.close_kasir_modal).pack(fill="x", padx=20,
                                                           pady=(0, 15))

        self.kasir_form_view = ctk.CTkFrame(dialog, fg_color="transparent")
        self.kasir_form_title = ctk.CTkLabel(self.kasir_form_view,
                                             text="Tambah Kasir",
                                             font=HEADER_FONT, text_color=ACCENT_COLOR)
        self.kasir_form_title.pack(pady=(15, 10))
        self.kasir_entries = {}
        for label, key in (("Nama Kasir:", "name"), ("ID Kasir:", "kasir_id"),
                           ("Cabang:", "branch"), ("Shift:", "shift")):
            f = ctk.CTkFrame(self.kasir_form_view, fg_color="transparent")
            f.pack(fill="x", padx=40, pady=4)
            ctk.CTkLabel(f, text=label, font=("Segoe UI", 11, "bold"),
                         text_color=TEXT_COLOR).pack(anchor="w")
            ent = ctk.CTkEntry(f, fg_color=CONSOLE_COLOR, border_color=BORDER_COLOR,
                               corner_radius=5)
            ent.pack(fill="x", pady=(2, 0))
            self.kasir_entries[key] = ent
        btn_box = ctk.CTkFrame(self.kasir_form_view, fg_color="transparent")
        btn_box.pack(fill="x", padx=40, pady=25)
        ctk.CTkButton(btn_box, text="Simpan", fg_color=ACCENT_COLOR,
                      text_color="white", corner_radius=5,
                      command=self.save_kasir_form).pack(side="left", expand=True,
                                                        padx=5)
        ctk.CTkButton(btn_box, text="Batal", fg_color="#666666",
                      text_color="white", corner_radius=5,
                      command=self.show_kasir_list).pack(side="left", expand=True,
                                                        padx=5)
        self.refresh_kasir_list()

    def close_kasir_modal(self):
        try:
            if self.kasir_dialog is not None and self.kasir_dialog.winfo_exists():
                self.kasir_dialog.destroy()
        except Exception:
            pass
        self.kasir_dialog = None
        self.load_cashiers()

    def show_kasir_list(self):
        self.kasir_form_view.pack_forget()
        self.kasir_list_view.pack(fill="both", expand=True)
        self.refresh_kasir_list()

    def refresh_kasir_list(self):
        from src.db import list_cashiers
        try:
            self.cashiers = list_cashiers(self.db_path)
        except Exception:
            self.cashiers = []
        for w in self.kasir_scroll.winfo_children():
            w.destroy()
        if not self.cashiers:
            ctk.CTkLabel(self.kasir_scroll, text="Belum ada data kasir.",
                         font=MAIN_FONT, text_color="grey").pack(pady=20)
            return
        for c in self.cashiers:
            row = ctk.CTkFrame(self.kasir_scroll, fg_color="white", border_width=1,
                               border_color=BORDER_COLOR, corner_radius=5)
            row.pack(fill="x", pady=5, padx=5)
            info = ctk.CTkFrame(row, fg_color="transparent")
            info.pack(side="left", fill="both", expand=True, padx=10, pady=8)
            ctk.CTkLabel(info, text=c["name"], font=("Segoe UI", 12, "bold"),
                         text_color=TEXT_COLOR, anchor="w").pack(fill="x")
            ctk.CTkLabel(
                info,
                text=f"ID: {c['kasir_id'] or '-'} | Cabang: {c['branch'] or '-'}"
                     f" | Shift: {c['shift'] or '-'}",
                font=("Segoe UI", 9), text_color="grey", anchor="w").pack(fill="x")
            btns = ctk.CTkFrame(row, fg_color="transparent")
            btns.pack(side="right", padx=10)
            ctk.CTkButton(btns, text="Edit", width=50, height=25, corner_radius=5,
                          font=SMALL_FONT, fg_color="#f5f5f5", text_color="black",
                          command=lambda r=c["rowid"]: self.show_kasir_edit_form(r)
                          ).pack(side="left", padx=2)
            ctk.CTkButton(btns, text="Hapus", width=50, height=25, corner_radius=5,
                          font=SMALL_FONT, fg_color="#ffebee", text_color="#d32f2f",
                          hover_color="#ffcdd2",
                          command=lambda r=c["rowid"],
                          n=c["name"]: self.delete_kasir(r, n)
                          ).pack(side="left", padx=2)

    def show_kasir_add_form(self):
        self._editing_rowid = None
        self.kasir_form_title.configure(text="Tambah Kasir")
        for ent in self.kasir_entries.values():
            ent.delete(0, "end")
        self.kasir_list_view.pack_forget()
        self.kasir_form_view.pack(fill="both", expand=True)

    def show_kasir_edit_form(self, rowid):
        c = next((x for x in self.cashiers if x["rowid"] == rowid), None)
        if not c:
            return
        self._editing_rowid = rowid
        self.kasir_form_title.configure(text="Edit Kasir")
        for key, ent in self.kasir_entries.items():
            ent.delete(0, "end")
            ent.insert(0, c.get(key) or "")
        self.kasir_list_view.pack_forget()
        self.kasir_form_view.pack(fill="both", expand=True)

    def save_kasir_form(self):
        from src.db import save_cashier
        vals = {k: e.get().strip() for k, e in self.kasir_entries.items()}
        if not vals["name"]:
            messagebox.showwarning("Peringatan", "Nama kasir wajib diisi.")
            return
        rowid = save_cashier(self.db_path, vals["name"], vals["kasir_id"],
                             vals["branch"], vals["shift"],
                             rowid=self._editing_rowid)
        if rowid is None:
            messagebox.showwarning("Peringatan", "Nama kasir wajib diisi.")
            return
        self._editing_rowid = None
        self.load_cashiers()
        try:
            self.cashier_var.set(vals["name"])
            self._sync_active_cashier()
        except Exception:
            pass
        self.show_kasir_list()

    def delete_kasir(self, rowid, name):
        from src.db import delete_cashier
        if messagebox.askyesno("Konfirmasi", f"Hapus kasir '{name}'?"):
            delete_cashier(self.db_path, rowid)
            self.load_cashiers()
            self.refresh_kasir_list()

    def get_receipt_char_width(self, for_print=False):
        size = self.print_size_var.get()
        if for_print:
            return 30 if size == "58" else 40
        return 32 if size == "58" else 48

    def update_receipt_preview(self):
        size = self.print_size_var.get()
        self.receipt_paper.configure(width=280 if size == "58" else 420)
        kasir, branch, shift, user_id = self.receipt_identity()
        self.lbl_receipt_text.configure(text=build_receipt_text(
            kasir=kasir, branch=branch, shift=shift, user_id=user_id,
            qty=self._qty_map(),
            expense_amount=self.expense_amount, expense_note=self.expense_note,
            nontunai_amount=self._nontunai_amount(),
            width=self.get_receipt_char_width(for_print=False)))

    def cetak(self):
        """Tombol Cetak: tanpa simpan; diam di preview."""
        if receipt.win32print is None:
            messagebox.showwarning("Modul Hilang",
                                   "Modul win32print tidak terdeteksi. "
                                   "Menggunakan metode sistem...")
            fd, path = tempfile.mkstemp(suffix=".txt")
            try:
                kasir, branch, shift, user_id = self.receipt_identity()
                with os.fdopen(fd, 'w', encoding='utf-8') as tmp:
                    tmp.write(build_receipt_text(
                        kasir=kasir, branch=branch, shift=shift, user_id=user_id,
                        qty=self._qty_map(), expense_amount=self.expense_amount,
                        expense_note=self.expense_note,
                        nontunai_amount=self._nontunai_amount(),
                        width=self.get_receipt_char_width(for_print=True)))
                os.startfile(path, "print")
            except Exception as e:
                messagebox.showerror("Error Cetak", f"Gagal mengirim ke printer: {e}")
            return
        ac = self.active_cashier or {}
        try:
            out = process_print_job({
                "kasir": self.kasir_name(), "branch": ac.get("branch") or "-",
                "shift": ac.get("shift") or "-", "user_id": ac.get("kasir_id") or "-",
                "qty": self._qty_map(), "expense_amount": self.expense_amount,
                "expense_note": self.expense_note,
                "nontunai_amount": self._nontunai_amount(),
                "size": self.print_size_var.get()})
        except (ValueError, RuntimeError) as e:
            messagebox.showerror("Error Cetak", str(e))
            return
        messagebox.showinfo("Sukses", f"Data berhasil dicetak ke {out['printer']}")
        # ponytail: nilai tetap + diam di preview (keputusan ronde 3/4)

    def clear_all(self):
        if messagebox.askyesno("Reset Semua", "Reset semua input ke nol?"):
            self.clear_all_silent()

    def clear_all_silent(self):
        self.clear_expense(silent=True)
        for denom in DENOMINATIONS:
            self.inputs[denom].delete(0, "end")
            self.subtotal_labels[denom].configure(text="Rp 0")
        self.lbl_grand_total.configure(text="Rp 0")
        self.nontunai_amount = 0
        try:
            self.nontunai_entry.delete(0, "end")
        except Exception:
            pass

    # --- expense (meniru render_expense_section cash_note) ---

    def render_expense_section(self):
        for widget in self.expense_container.winfo_children():
            widget.destroy()
        if self.expense_amount == 0 and not self.expense_note:
            ctk.CTkButton(self.expense_container, text="+ Pengeluaran & Keterangan",
                          fg_color="#eef2fb", hover_color="#dde6f9",
                          text_color=ACCENT_COLOR, border_width=1,
                          border_color="#c7d7fa", corner_radius=8, height=32,
                          font=("Segoe UI", 11, "bold"),
                          command=self.show_expense_popup).pack(fill="x")
            return
        card = ctk.CTkFrame(
            self.expense_container,
            fg_color="#fff9f9" if self.expense_amount > 0 else "#f8faff",
            border_width=1,
            border_color="#ffcdd2" if self.expense_amount > 0 else "#dbe4fb",
            corner_radius=8)
        card.pack(fill="x")
        info_box = ctk.CTkFrame(card, fg_color="transparent")
        info_box.pack(side="left", fill="both", expand=True, padx=(12, 5), pady=6)
        ctk.CTkLabel(info_box, text=f"Pengeluaran: {format_rp(self.expense_amount)}",
                     font=("Segoe UI", 11, "bold"),
                     text_color="#d32f2f" if self.expense_amount > 0 else TEXT_COLOR,
                     anchor="w").pack(fill="x")
        if self.expense_note:
            ctk.CTkLabel(info_box, text=f"Ket: {self.expense_note}",
                         font=SMALL_FONT, text_color="#555555",
                         anchor="w").pack(fill="x")
        btn_box = ctk.CTkFrame(card, fg_color="transparent")
        btn_box.pack(side="right", padx=(5, 8), pady=6)
        ctk.CTkButton(btn_box, text="Ubah", width=45, height=26, fg_color=ACCENT_COLOR,
                      hover_color="#375a7f", text_color="white", corner_radius=5,
                      font=("Segoe UI", 10, "bold"),
                      command=self.show_expense_popup).pack(side="left", padx=2)
        ctk.CTkButton(btn_box, text="✕", width=26, height=26, fg_color="#e0e0e0",
                      hover_color="#d0d0d0", text_color="#333333", corner_radius=5,
                      font=("Segoe UI", 10, "bold"),
                      command=self.clear_expense).pack(side="left", padx=2)

    def show_expense_popup(self):
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Pengeluaran & Keterangan")
        dialog.geometry("380x300")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - 380) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - 300) // 2
        dialog.geometry(f"+{max(0, x)}+{max(0, y)}")

        container = ctk.CTkFrame(dialog, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=15)
        ctk.CTkLabel(container, text="Input Pengeluaran & Keterangan",
                     font=HEADER_FONT, text_color=TEXT_COLOR).pack(anchor="w",
                                                                   pady=(0, 10))
        ctk.CTkLabel(container, text="Nominal Pengeluaran (Rp):",
                     font=("Segoe UI", 11, "bold"),
                     text_color=TEXT_COLOR).pack(anchor="w", pady=(5, 2))
        entry_amount = ctk.CTkEntry(container, placeholder_text="0", height=38,
                                    font=("Segoe UI", 14, "bold"), justify="right",
                                    fg_color=CONSOLE_COLOR, border_color=BORDER_COLOR,
                                    text_color=TEXT_COLOR, corner_radius=6)
        entry_amount.pack(fill="x", pady=(0, 10))
        if self.expense_amount > 0:
            entry_amount.insert(0, f"{self.expense_amount:,}".replace(",", "."))

        def format_currency_input(event=None):
            val = "".join(filter(str.isdigit,
                                 entry_amount.get().replace(".", "").strip()))
            if not val:
                entry_amount.delete(0, "end")
                return
            entry_amount.delete(0, "end")
            entry_amount.insert(0, "{:,}".format(int(val)).replace(",", "."))

        entry_amount.bind("<KeyRelease>", format_currency_input)
        ctk.CTkLabel(container, text="Keterangan:", font=("Segoe UI", 11, "bold"),
                     text_color=TEXT_COLOR).pack(anchor="w", pady=(5, 2))
        entry_note = ctk.CTkEntry(container,
                                  placeholder_text="Contoh: Potongan refund",
                                  height=38, font=MAIN_FONT, fg_color=CONSOLE_COLOR,
                                  border_color=BORDER_COLOR, text_color=TEXT_COLOR,
                                  corner_radius=6)
        entry_note.pack(fill="x", pady=(0, 15))
        if self.expense_note:
            entry_note.insert(0, self.expense_note)

        def on_save(event=None):
            val_str = entry_amount.get().replace(".", "").strip()
            self.expense_amount = int(val_str) if val_str else 0
            self.expense_note = entry_note.get().strip()
            self.render_expense_section()
            dialog.destroy()

        def on_clear():
            self.expense_amount = 0
            self.expense_note = ""
            self.render_expense_section()
            dialog.destroy()

        def on_cancel(event=None):
            dialog.destroy()

        entry_amount.bind("<Return>", lambda e: entry_note.focus())
        entry_note.bind("<Return>", on_save)
        dialog.bind("<Escape>", on_cancel)

        btn_box = ctk.CTkFrame(container, fg_color="transparent")
        btn_box.pack(fill="x", pady=(5, 0))
        ctk.CTkButton(btn_box, text="Simpan", fg_color=ACCENT_COLOR,
                      hover_color="#375a7f", text_color="white", corner_radius=6,
                      font=("Segoe UI", 11, "bold"), height=34,
                      command=on_save).pack(side="left", expand=True, fill="x",
                                            padx=(0, 4))
        if self.expense_amount > 0 or self.expense_note:
            ctk.CTkButton(btn_box, text="Hapus", fg_color="#d32f2f",
                          hover_color="#b71c1c", text_color="white", corner_radius=6,
                          font=MAIN_FONT, height=34,
                          command=on_clear).pack(side="left", expand=True, fill="x",
                                                 padx=4)
        ctk.CTkButton(btn_box, text="Batal", fg_color="#666666",
                      hover_color="#555555", text_color="white", corner_radius=6,
                      font=MAIN_FONT, height=34,
                      command=on_cancel).pack(side="left", expand=True, fill="x",
                                              padx=(4, 0))
        entry_amount.focus()

    def clear_expense(self, silent=False):
        self.expense_amount = 0
        self.expense_note = ""
        try:
            self.render_expense_section()
        except Exception:
            pass  # ponytail: dipanggil clear_all_silent sebelum build selesai

    # --- admin (dashboard lama) ---

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
        from src.config import VERSION
        self.root.title(f"CNdesktop v{VERSION} :{new}")
        if self.on_port_change:
            self.on_port_change(new)

    def open_log(self):
        from src.config import LOG_FILE, LOG_SUBDIR, app_dir
        try:
            os.startfile(os.path.join(app_dir(), LOG_SUBDIR, LOG_FILE))
        except Exception:
            pass  # ponytail: tombol diagnosis, gagal diam-diam

    def run_test(self):
        try:
            out = self.test_read()
        except Exception as e:
            out = {"error": repr(e)}
        self.txt_test.delete("1.0", "end")
        for k in ("total_raw", "tunai_raw", "debit_raw", "bank_raw", "_note", "error"):
            if k in out:
                self.txt_test.insert("end", f"{k} = {out[k]!r}\n")

    def confirm_clear_transactions(self):
        from src.db import clear_transactions
        try:
            with sqlite3.connect(self.db_path) as c:
                n = c.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        except Exception:
            n = "?"
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Hapus Transaksi")
        dialog.geometry("360x220")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        box = ctk.CTkFrame(dialog, fg_color="transparent")
        box.pack(fill="both", expand=True, padx=20, pady=15)
        ctk.CTkLabel(box, text=f"Hapus {n} transaksi?\nBackup otomatis dibuat dulu.",
                     font=MAIN_FONT, text_color=TEXT_COLOR,
                     justify="left").pack(anchor="w", pady=(0, 8))
        ctk.CTkLabel(box, text='Ketik HAPUS untuk lanjut:',
                     font=("Segoe UI", 11, "bold"),
                     text_color=TEXT_COLOR).pack(anchor="w")
        entry = ctk.CTkEntry(box, fg_color=CONSOLE_COLOR,
                             border_color=BORDER_COLOR, corner_radius=5)
        entry.pack(fill="x", pady=(4, 12))
        entry.focus()

        def on_ok(event=None):
            if entry.get().strip() != "HAPUS":
                return  # ponytail: salah ketik = batal diam-diam
            dialog.destroy()
            try:
                count, bak = clear_transactions(self.db_path, backup=True)
            except Exception as e:
                messagebox.showerror("Gagal", f"Hapus gagal: {e}")
                return
            import logging
            logging.getLogger("cndesktop").warning(
                "clear transaksi: %s baris, backup %s", count, bak)
            self.refresh()
            messagebox.showinfo("Selesai",
                                f"{count} transaksi dihapus.\nBackup: {bak}")

        def on_cancel(event=None):
            dialog.destroy()

        entry.bind("<Return>", on_ok)
        dialog.bind("<Escape>", on_cancel)
        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkButton(row, text="Hapus", fg_color="#d32f2f",
                      hover_color="#b71c1c", text_color="white", corner_radius=5,
                      command=on_ok).pack(side="left", expand=True, padx=(0, 4))
        ctk.CTkButton(row, text="Batal", fg_color="#666666",
                      text_color="white", corner_radius=5,
                      command=on_cancel).pack(side="left", expand=True,
                                              padx=(4, 0))

    def watcher_enabled_state(self) -> bool:
        try:
            if self._watcher is not None:
                return bool(self._watcher.is_enabled())
            from src.db import get_watcher_enabled
            return bool(get_watcher_enabled(self.db_path))
        except Exception:
            return True

    def _prompt_pin(self, title="PIN") -> str | None:
        """Popup input PIN, return PIN atau None jika batal. Tiap toggle wajib lewat sini."""
        out = {"pin": None}
        dialog = ctk.CTkToplevel(self.root)
        dialog.title(title)
        dialog.geometry("300x170")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        box = ctk.CTkFrame(dialog, fg_color="transparent")
        box.pack(fill="both", expand=True, padx=20, pady=15)
        ctk.CTkLabel(box, text="Masukkan PIN 6-digit:",
                     font=("Segoe UI", 11, "bold"),
                     text_color=TEXT_COLOR).pack(anchor="w")
        entry = ctk.CTkEntry(box, show="*", fg_color=CONSOLE_COLOR,
                             border_color=BORDER_COLOR, corner_radius=5)
        entry.pack(fill="x", pady=(4, 12))
        entry.focus()

        def on_ok(event=None):
            out["pin"] = entry.get().strip()
            dialog.destroy()

        def on_cancel(event=None):
            dialog.destroy()

        entry.bind("<Return>", on_ok)
        dialog.bind("<Escape>", on_cancel)
        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkButton(row, text="OK", corner_radius=5,
                      command=on_ok).pack(side="left", expand=True, padx=(0, 4))
        ctk.CTkButton(row, text="Batal", fg_color="#666666",
                      text_color="white", corner_radius=5,
                      command=on_cancel).pack(side="left", expand=True,
                                              padx=(4, 0))
        dialog.wait_window()
        return out["pin"]

    def toggle_watcher(self):
        """Tombol Watcher On/Off: tiap klik wajib PIN benar, salah = batal."""
        pin = self._prompt_pin("Watcher On/Off")
        if pin is None:
            return
        if not check_watcher_pin(self.db_path, pin):
            messagebox.showwarning("PIN Salah", "PIN salah, status tidak diubah.")
            return
        target = not self.watcher_enabled_state()
        try:
            if self._watcher is not None:
                self._watcher.set_enabled(target)
            else:
                from src.db import set_watcher_enabled
                set_watcher_enabled(self.db_path, target)
        except Exception as e:
            messagebox.showerror("Gagal", f"Gagal ubah watcher: {e}")
            return
        self.refresh()

    def change_pin(self):
        """Simpan PIN baru (lokal saja, tanpa endpoint remote)."""
        try:
            new = self.ent_pin.get().strip()
        except Exception:
            return
        err = validate_new_pin(new)
        if err:
            messagebox.showwarning("PIN Invalid", err)
            return
        from src.db import set_wipe_pin
        try:
            set_wipe_pin(self.db_path, new)
        except ValueError as e:
            messagebox.showwarning("PIN Invalid", str(e))
            return
        messagebox.showinfo("Selesai", "PIN baru tersimpan.")
        try:
            self.ent_pin.delete(0, "end")
        except Exception:
            pass

    def refresh(self):
        try:
            alive = self.watcher_alive()
        except Exception:
            alive = False
        self.lbl_watcher.configure(
            text=watcher_status_text(self.watcher_enabled_state(), alive))
        try:
            det = ketoko_detected()
        except Exception:
            det = False
        self.lbl_ketoko.configure(text=f"ketoko: {'terdeteksi' if det else 'tidak'}")
        self.lbl_last.configure(text=f"no terakhir: {last_no_transaksi(self.db_path)}")
        for r in self.tree.get_children():
            self.tree.delete(r)
        for t in last_20(self.db_path):
            self.tree.insert("", "end", values=(
                t["id"], t["no_transaksi"], t.get("no_urut", ""), t["total"], t["tunai"],
                t["nontunai"], t["bank"], t["kategori"], t["created_at"]))
