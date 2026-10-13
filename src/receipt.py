"""Struk + cetak headless CNdesktop (tanpa GUI).

Meniru alur halaman calculate: hitung_total -> validate_calc ->
build_receipt_text -> build_escpos_receipt -> kirim printer.
Dipakai dashboard (tombol Cetak) dan api (POST /api/print dari HP).
"""
import base64
import textwrap
from datetime import datetime

try:
    import win32print  # type: ignore
except ImportError:
    win32print = None

DENOMINATIONS = [100000, 75000, 50000, 20000, 10000, 5000, 2000, 1000, 500, 200, 100]
KASIR_PLACEHOLDER = "Pilih data Kasir"
KASIR_EMPTY = "Data Kasir Kosong"

ARABIC_RECEIPT_TEXT = '"شكراً جزيلاً"'
ARABIC_ESC_POS_IMAGE_B64 = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAfAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAPgAAAAAAAAHwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD4AAAAAAAAAHwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD4AAAAAAAAB8AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA+AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAPeAAcAAAAAAABwAAAAgAAHvAAAAAAAAAAAAAAAAAAAAAAAAAAAA95+BwAAAAAAAHAAAAOAAAe8AAAAAAAAAAAAAAAAAAAAAAAAAAAD3h4HAAAAAAAAcAAAD4AAB7wAAAAAAAAAAAAAAAAAAAAAAAAAAAPeDwcAAAAAAABwAAA/AAAHvAAAAAAAAAAAAAAAAAAAAAAAAAAAA94HhwAAAAAAAHAAAPwAAAe8AAAAAAAAAAAAAAAAAAAAAAAAAAAD3gPHAAAAAAAAcAAD8AA4B7wAAAAAAAAAAAAAAAAAAAAAAAAAAAHcAecAAAAAAABwAAPgADgDuAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAB5wAAAAAAAHAAA8AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD3AAAAH4AAcAAD4ADuAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAHcAADwf4ABwAAHwAO4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAfwOAPB/wAHAAAPgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA/A4AAAfwAcAAAPAAA4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD8DgAAAPgBwAAAeAADgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAPwOAPgAPAHAB4A8AAOAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAB/A4AeAB8AcADwB4c84AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAPcDgA4B/wBwAHADhzzgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAB5weADw//AHAAcAfPPOAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAPn/4AP//wAcAB/////4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAB8f/AA//wABwAH/////gAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAPg/4AD/wAAHAAf/9//8AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAeAAAAAADwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADwAcAAAAeAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD+B/ABwAAAP4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP5/4AAAAAP/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAH/AAAAAA/wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAfgAAAAAD8AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=="
ARABIC_ESC_POS_IMAGE_WIDTH = 300
ARABIC_ESC_POS_IMAGE_HEIGHT = 80
ARABIC_ESC_POS_IMAGE_BYTES_PER_ROW = 38


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
        return "Silakan pilih data kasir terlebih dahulu (tambah via tombol Kasir)."
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


def build_receipt_text(*, kasir, branch="-", shift="-", user_id="-",
                       qty, expense_amount=0, expense_note="", nontunai_amount=0,
                       width, now=None):
    """Struk ala cash_note; Non Tunai dari nontunai_amount (default 0)."""
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

    try:
        non_cash_total = int(nontunai_amount or 0)
    except (ValueError, TypeError):
        non_cash_total = 0
    sales_total = physical_total + non_cash_total + expense_amount

    lines = []
    lines.append("TOKO LAY".center(inner_width))
    lines.append("Laporan Penjualan".center(inner_width))
    lines.append("-" * inner_width)
    lines.append(format_key_value_line("Tanggal", now.strftime('%d/%m/%Y'), inner_width))
    lines.append(format_key_value_line("Cabang", branch or "-", inner_width))
    lines.append(format_key_value_line("Shift", shift or "-", inner_width))
    lines.append(format_key_value_line("Kasir", kasir, inner_width))
    lines.append(format_key_value_line("User ID", user_id or "-", inner_width))
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


def print_width(size) -> int:
    """Lebar kolom cetak fisik: 58mm -> 30, 80mm -> 40."""
    return 30 if str(size or "58") == "58" else 40


def send_to_printer(payload: bytes) -> str:
    """Kirim payload ESC/POS ke printer default. Return nama printer.

    Raise RuntimeError (pesan siap tampil) jika modul/printer/cetak gagal.
    """
    if not win32print:
        raise RuntimeError("Modul win32print tidak terdeteksi di PC ini.")
    try:
        printer_name = win32print.GetDefaultPrinter()
    except Exception as e:
        raise RuntimeError(f"Gagal membaca printer default: {e}")
    if not printer_name:
        raise RuntimeError("Printer default tidak ditemukan. "
                           "Silakan set printer di Windows.")
    try:
        hPrinter = win32print.OpenPrinter(printer_name)
        try:
            win32print.StartDocPrinter(hPrinter, 1, ("Struk Kasir", None, "RAW"))
            try:
                win32print.StartPagePrinter(hPrinter)
                win32print.WritePrinter(hPrinter, payload)
                win32print.EndPagePrinter(hPrinter)
            finally:
                win32print.EndDocPrinter(hPrinter)
        finally:
            win32print.ClosePrinter(hPrinter)
    except Exception as e:
        raise RuntimeError(f"Gagal mencetak: {e}")
    return printer_name


def _norm_qty(raw) -> dict:
    """Normalisasi qty JSON {str(denom): qty} -> {int(denom): int}. Asing dibuang."""
    out = {}
    if not isinstance(raw, dict):
        return out
    for d in DENOMINATIONS:
        for key in (d, str(d)):
            if key in raw:
                try:
                    out[d] = int(raw[key] or 0)
                except (ValueError, TypeError):
                    out[d] = 0
                break
    return out


def _norm_nontunai(raw) -> int:
    """Normalisasi nontunai_amount: str angka→int, kosong/invalid→0, negatif→raise."""
    try:
        v = int(raw or 0)
    except (ValueError, TypeError):
        return 0
    if v < 0:
        raise ValueError("nontunai_amount tidak boleh negatif.")
    return v


def process_print_job(data: dict | None, sender=None) -> dict:
    """Simulasi halaman calculate secara headless + cetak.

    data: {kasir, branch, shift, user_id, qty, expense_amount, expense_note,
        nontunai_amount, size}.
    Return {"printer", "total" (fisik), "nontunai", "sales_total"}.
    Raise ValueError (validasi) / RuntimeError (printer).
    """
    data = data if isinstance(data, dict) else {}
    kasir = (data.get("kasir") or "").strip()
    qty = _norm_qty(data.get("qty"))
    try:
        expense = int(data.get("expense_amount") or 0)
    except (ValueError, TypeError):
        expense = 0
    nontunai = _norm_nontunai(data.get("nontunai_amount"))
    note = data.get("expense_note") or ""
    size = str(data.get("size") or "58")
    if size not in ("58", "80"):
        raise ValueError("size harus 58 atau 80.")
    total = hitung_total(qty)
    err = validate_calc(kasir, total + nontunai)
    if err:
        raise ValueError(err)
    text = build_receipt_text(
        kasir=kasir, branch=data.get("branch") or "-",
        shift=data.get("shift") or "-", user_id=data.get("user_id") or "-",
        qty=qty, expense_amount=expense, expense_note=note,
        nontunai_amount=nontunai, width=print_width(size))
    payload = build_escpos_receipt(text)
    printer = (sender or send_to_printer)(payload)
    return {"printer": printer, "total": total, "nontunai": nontunai,
            "sales_total": total + nontunai + expense}
