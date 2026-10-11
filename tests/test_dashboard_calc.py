"""Calculate dashboard: matematika, format Rp, builder struk, validasi.

Tanpa display: hanya fungsi murni src.dashboard (tanpa sentuh printer).
"""
import base64
from datetime import datetime

from src.dashboard import (
    ARABIC_ESC_POS_IMAGE_B64,
    DENOMINATIONS,
    build_escpos_arabic_image,
    build_escpos_receipt,
    build_receipt_text,
    format_rp,
    hitung_total,
    validate_calc,
)


def test_hitung_total_campur():
    assert hitung_total({100000: 2, 5000: 1}) == 205000


def test_hitung_total_kosong_nol():
    assert hitung_total({}) == 0
    assert hitung_total({d: 0 for d in DENOMINATIONS}) == 0


def test_hitung_total_tahan_string_dan_sampah():
    assert hitung_total({100000: "3", 20000: "", 10000: None, 500: "x"}) == 300000


def test_hitung_total_semua_pecahan():
    assert hitung_total({d: 1 for d in DENOMINATIONS}) == sum(DENOMINATIONS)


def test_format_rp():
    assert format_rp(0) == "Rp 0"
    assert format_rp(205000) == "Rp 205.000"
    assert format_rp(100000) == "Rp 100.000"


def _struk(**kw):
    args = dict(kasir="Kasir-1", qty={100000: 2, 5000: 1},
                expense_amount=10000, expense_note="Potongan",
                width=32, now=datetime(2026, 10, 11, 19, 50, 41))
    args.update(kw)
    return build_receipt_text(**args)


def test_struk_memuat_kasir_dan_total():
    t = _struk()
    assert "Kasir-1" in t
    assert "TOTAL FISIK" in t
    assert "Rp 205.000" in t


def test_struk_tanpa_sistem():
    t = _struk()
    assert "Cabang" in t and "-" in t  # Cabang/Shift/User ID strip
    assert "Non Tunai" in t and "Rp 0" in t
    assert "Total Penjualan" in t and "Rp 215.000" in t  # fisik+0+expense


def test_struk_lebar_80_lebih_lebar():
    assert len(_struk(width=48).splitlines()[0]) > len(_struk(width=32).splitlines()[0])


def test_validasi():
    assert validate_calc("", 100) is not None  # kasir kosong ditolak
    assert validate_calc("   ", 100) is not None
    assert validate_calc("Kasir-1", 0) is not None  # total nol ditolak
    assert validate_calc("Kasir-1", 100) is None


def test_arab_image_38x80():
    assert len(base64.b64decode(ARABIC_ESC_POS_IMAGE_B64)) == 38 * 80
    img = build_escpos_arabic_image()
    assert img[:3] == b"\x1b\x61\x01" and b"\x1d\x76\x30\x00" in img


def test_escpos_receipt_tanpa_simpan():
    t = _struk()
    p = build_escpos_receipt(t)
    assert p[:2] == b"\x1b@"  # init printer
    assert build_escpos_arabic_image() in p  # arab via gambar, bukan teks
    assert "calculate_history".encode() not in p  # tanpa simpan history
