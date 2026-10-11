"""Dashboard CNdesktop: UI calculate di depan, admin tersembunyi.

Pola meniru cash_note tabs/calculate_tab.py: satu window berisi view yang
ditukar (input <-> preview), admin dibuka via Ctrl+Shift+Alt+D.
Tanpa Total Sistem (Non Tunai ditulis Rp 0), kasir teks bebas,
preview + Cetak TANPA simpan, sesudah cetak nilai tetap diam di preview.
"""
import base64
import ctypes
import os
import sqlite3
import tempfile
import textwrap
from ctypes import wintypes
from datetime import datetime
from tkinter import messagebox, ttk

import customtkinter as ctk

try:
    import win32print  # type: ignore
except ImportError:
    win32print = None

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

DENOMINATIONS = [100000, 75000, 50000, 20000, 10000, 5000, 2000, 1000, 500, 200, 100]
DEFAULT_KASIR = "Kasir-1"

ARABIC_RECEIPT_TEXT = '"شكراً جزيلاً"'
ARABIC_ESC_POS_IMAGE_B64 = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAfAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAPgAAAAAAAAHwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD4AAAAAAAAAHwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD4AAAAAAAAB8AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA+AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAPeAAcAAAAAAABwAAAAgAAHvAAAAAAAAAAAAAAAAAAAAAAAAAAAA95+BwAAAAAAAHAAAAOAAAe8AAAAAAAAAAAAAAAAAAAAAAAAAAAD3h4HAAAAAAAAcAAAD4AAB7wAAAAAAAAAAAAAAAAAAAAAAAAAAAPeDwcAAAAAAABwAAA/AAAHvAAAAAAAAAAAAAAAAAAAAAAAAAAAA94HhwAAAAAAAHAAAPwAAAe8AAAAAAAAAAAAAAAAAAAAAAAAAAAD3gPHAAAAAAAAcAAD8AA4B7wAAAAAAAAAAAAAAAAAAAAAAAAAAAHcAecAAAAAAABwAAPgADgDuAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAB5wAAAAAAAHAAA8AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD3AAAAH4AAcAAD4ADuAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAHcAADwf4ABwAAHwAO4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAfwOAPB/wAHAAAPgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA/A4AAAfwAcAAAPAAA4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD8DgAAAPgBwAAAeAADgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAPwOAPgAPAHAB4A8AAOAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAB/A4AeAB8AcADwB4c84AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAPcDgA4B/wBwAHADhzzgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAB5weADw//AHAAcAfPPOAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAPn/4AP//wAcAB/////4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAB8f/AA//wABwAH/////gAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAPg/4AD/wAAHAAf/9//8AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAeAAAAAADwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADwAcAAAAeAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD+B/ABwAAAP4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP5/4AAAAAP/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAH/AAAAAA/wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAfgAAAAAD8AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=="
ARABIC_ESC_POS_IMAGE_WIDTH = 300
ARABIC_ESC_POS_IMAGE_HEIGHT = 80
ARABIC_ESC_POS_IMAGE_BYTES_PER_ROW = 38


# --- fungsi murni (tanpa GUI, bisa unit-test) ---

def format_rp(n) -> str:
    return f"Rp {int(n):,}".replace(",", ".")


def hitung_total(qty: dict) -> int:
    """Total fisik = sum(qty[denom] * denom). qty boleh str/int/kosong."""
    total = 0
    for d in DENOMINATIONS:
        try:
            total += int(qty.get(d, 0) or 0) * d
        except (ValueError, TypeError):
            pass
    return total


def validate_calc(kasir_name: str, total: int) -> str | None:
    """Return pesan error, atau None jika valid (mirip show_preview cash_note)."""
    if not (kasir_name or "").strip():
        return "Silakan isi nama kasir terlebih dahulu."
    if total == 0:
        return "Total perhitungan tidak boleh nol."
    return None


def format_key_value_line(label, value, width):
    left, right = str(label), str(value)
    space = width - len(left) - len(right)
    if space < 1:
        return f"{left} {right}"
    return f"{left}{' ' * space}{right}"


def format_amount_line(label, amount, width):
    right = f"Rp {amount:,}".replace(",", ".")
    space = width - len(label) - len(right)
    if space < 2:
        words = label.split(" ", 1)
        if len(words) == 2:
            first, rest = words
            space1 = width - len(first) - len(right)
            if space1 >= 1:
                return f"{first}{' ' * space1}{right}\n{rest}"
        return f"{label} {right}"
    return f"{label}{' ' * space}{right}"


def add_receipt_margin(lines, width, margin=2):
    inner_width = max(width - (margin * 2), 10)
    pad = " " * margin
    padded = []
    for line in lines:
        if not line:
            padded.append("")
            continue
        padded.append(f"{pad}{line[:inner_width].ljust(inner_width)}{pad}")
    return padded, inner_width


def build_receipt_text(*, kasir, qty, expense_amount=0, expense_note="", width, now=None):
    """Struk ala cash_note; Cabang/Shift/UserID '-', Non Tunai Rp 0 (tanpa sistem)."""
    now = now or datetime.now()
    margin = 2
    inner_width = max(width - (margin * 2), 10)
    physical_lines = []
    physical_total = 0
    for denom in DENOMINATIONS:
        try:
            q = int(qty.get(denom, 0) or 0)
        except (ValueError, TypeError):
            q = 0
        if q > 0:
            subtotal = q * denom
            physical_total += subtotal
            left = f"{denom:,} x {q}".replace(",", ".")
            right = f"Rp {subtotal:,}".replace(",", ".")
            space = inner_width - len(left) - len(right)
            if space < 1:
                physical_lines.append(left)
                physical_lines.append(right.rjust(inner_width))
            else:
                physical_lines.append(f"{left}{' ' * space}{right}")

    non_cash_total = 0  # ponytail: tanpa Total Sistem, ditulis Rp 0
    sales_total = physical_total + non_cash_total + expense_amount

    lines = []
    lines.append("TOKO LAY".center(inner_width))
    lines.append("Laporan Penjualan".center(inner_width))
    lines.append("-" * inner_width)
    lines.append(format_key_value_line("Tanggal", now.strftime('%d/%m/%Y'), inner_width))
    lines.append(format_key_value_line("Cabang", "-", inner_width))
    lines.append(format_key_value_line("Shift", "-", inner_width))
    lines.append(format_key_value_line("Kasir", kasir, inner_width))
    lines.append(format_key_value_line("User ID", "-", inner_width))
    lines.append("-" * inner_width)
    for sub in format_amount_line("Total Penjualan", sales_total, inner_width).split("\n"):
        lines.append(sub)
    lines.append(format_amount_line("Non Tunai", non_cash_total, inner_width))
    lines.append(format_amount_line("Pengeluaran", expense_amount, inner_width))
    lines.append("-" * inner_width)
    lines.append("-- Rincian Uang Fisik --".center(inner_width))
    lines.extend(physical_lines)
    lines.append("-" * inner_width)
    lines.append(format_amount_line("TOTAL FISIK", physical_total, inner_width))
    lines.append("-" * inner_width)
    if (expense_note or "").strip():
        first = True
        for raw in expense_note.strip().splitlines():
            prefix = "Ket: " if first else ""
            first = False
            for w in textwrap.wrap(f"{prefix}{raw}".strip(), width=inner_width):
                lines.append(w.center(inner_width))
    lines.append(now.strftime('%d/%m/%Y %H:%M:%S').center(inner_width))
    lines.append(ARABIC_RECEIPT_TEXT.center(inner_width))
    lines, _ = add_receipt_margin(lines, width, margin)
    return "\n".join(lines)


def build_escpos_arabic_image():
    image_bytes = base64.b64decode(ARABIC_ESC_POS_IMAGE_B64)
    header = bytearray()
    header.extend(b"\x1b\x61\x01")
    header.extend(
        b"\x1d\x76\x30\x00"
        + bytes([ARABIC_ESC_POS_IMAGE_BYTES_PER_ROW & 0xFF,
                 (ARABIC_ESC_POS_IMAGE_BYTES_PER_ROW >> 8) & 0xFF])
        + bytes([ARABIC_ESC_POS_IMAGE_HEIGHT & 0xFF,
                 (ARABIC_ESC_POS_IMAGE_HEIGHT >> 8) & 0xFF])
    )
    return bytes(header) + image_bytes + b"\n\x1b\x61\x00"


def build_escpos_receipt(receipt_text):
    payload = bytearray()
    payload.extend(b"\x1b@")
    payload.extend(b"\x1b\x61\x00")
    for line in receipt_text.splitlines():
        stripped = line.strip()
        if not stripped:
            payload.extend(b"\n")
            continue
        if stripped == ARABIC_RECEIPT_TEXT:
            payload.extend(build_escpos_arabic_image())
        else:
            payload.extend(line.encode("ascii", errors="replace") + b"\n")
    payload.extend(b"\n")
    return bytes(payload)


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


class Dashboard:
    def __init__(self, db_path, port, on_port_change=None,
                 watcher_alive=None, test_read=None):
        from src.config import VERSION
        self.db_path = db_path
        self.port = port
        self.on_port_change = on_port_change  # fn(new_port) -> None
        self.watcher_alive = watcher_alive or (lambda: True)
        self.test_read = test_read or default_test_read

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
        self.vcmd = (self.root.register(self.validate_numeric), "%P")
        self.print_size_var = ctk.StringVar(value="58")

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

        self.ent_kasir = ctk.CTkEntry(header, height=38, font=("Segoe UI", 11),
                                      fg_color=CONSOLE_COLOR, border_color=BORDER_COLOR,
                                      text_color=TEXT_COLOR, corner_radius=10)
        self.ent_kasir.pack(pady=(0, 8), padx=20, fill="x")
        self.ent_kasir.insert(0, DEFAULT_KASIR)

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

    def kasir_name(self) -> str:
        try:
            return self.ent_kasir.get().strip()
        except Exception:
            return ""

    def show_preview(self):
        err = validate_calc(self.kasir_name(), hitung_total(self._qty_map()))
        if err:
            messagebox.showwarning("Data Tidak Lengkap", err)
            return
        self._show_only(self.preview_view)
        self.update_receipt_preview()

    def show_input_view(self):
        self._show_only(self.input_view)

    def get_receipt_char_width(self, for_print=False):
        size = self.print_size_var.get()
        if for_print:
            return 30 if size == "58" else 40
        return 32 if size == "58" else 48

    def update_receipt_preview(self):
        size = self.print_size_var.get()
        self.receipt_paper.configure(width=280 if size == "58" else 420)
        self.lbl_receipt_text.configure(text=build_receipt_text(
            kasir=self.kasir_name() or DEFAULT_KASIR, qty=self._qty_map(),
            expense_amount=self.expense_amount, expense_note=self.expense_note,
            width=self.get_receipt_char_width(for_print=False)))

    def cetak(self):
        """Cetak ala cash_note save_and_print, TANPA simpan; diam di preview."""
        char_width = self.get_receipt_char_width(for_print=True)
        receipt_text = build_receipt_text(
            kasir=self.kasir_name() or DEFAULT_KASIR, qty=self._qty_map(),
            expense_amount=self.expense_amount, expense_note=self.expense_note,
            width=char_width)
        if win32print:
            try:
                printer_name = win32print.GetDefaultPrinter()
                if not printer_name:
                    raise Exception("Printer default tidak ditemukan. "
                                    "Silakan set printer di Windows.")
                hPrinter = win32print.OpenPrinter(printer_name)
                try:
                    win32print.StartDocPrinter(hPrinter, 1, ("Struk Kasir", None, "RAW"))
                    try:
                        win32print.StartPagePrinter(hPrinter)
                        win32print.WritePrinter(hPrinter,
                                                build_escpos_receipt(receipt_text))
                        win32print.EndPagePrinter(hPrinter)
                    finally:
                        win32print.EndDocPrinter(hPrinter)
                finally:
                    win32print.ClosePrinter(hPrinter)
                messagebox.showinfo("Sukses", f"Data berhasil dicetak ke {printer_name}")
            except Exception as e:
                messagebox.showerror("Error Cetak", f"Gagal mencetak: {e}")
        else:
            messagebox.showwarning("Modul Hilang", "Modul win32print tidak terdeteksi. "
                                                   "Menggunakan metode sistem...")
            fd, path = tempfile.mkstemp(suffix=".txt")
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as tmp:
                    tmp.write(receipt_text)
                os.startfile(path, "print")
            except Exception as e:
                messagebox.showerror("Error Cetak", f"Gagal mengirim ke printer: {e}")
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

    def refresh(self):
        try:
            alive = self.watcher_alive()
        except Exception:
            alive = False
        self.lbl_watcher.configure(text=f"watcher: {'jalan' if alive else 'mati'}")
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
