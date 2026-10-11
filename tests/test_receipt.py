"""process_print_job headless: simulasi calculate + cetak via sender injeksi."""
import pytest

from src.receipt import (
    build_escpos_arabic_image,
    print_width,
    process_print_job,
)


def _job(**kw):
    d = dict(kasir="Surjo", branch="Cabang A", shift="Pagi", user_id="K01",
             qty={"100000": 2, "5000": 1}, expense_amount=10000,
             expense_note="Potongan", size="58")
    d.update(kw)
    return d


def test_valid_mock_sender():
    kirim = []
    out = process_print_job(_job(), sender=lambda p: kirim.append(p) or "MockPrinter")
    assert out == {"printer": "MockPrinter", "total": 205000}
    assert len(kirim) == 1
    payload = kirim[0]
    assert payload[:2] == b"\x1b@"
    assert build_escpos_arabic_image() in payload
    assert "Surjo".encode() in payload and "Cabang A".encode() in payload


def test_size_80_lebar_40():
    texts = []

    def sender(p):
        texts.append(p)
        return "P"

    process_print_job(_job(size="80"), sender=sender)
    assert print_width("58") == 30 and print_width("80") == 40
    assert len(texts[0]) > 0


def test_kasir_kosong_ditolak():
    with pytest.raises(ValueError):
        process_print_job(_job(kasir="   "), sender=lambda p: "P")


def test_total_nol_ditolak():
    with pytest.raises(ValueError):
        process_print_job(_job(qty={}), sender=lambda p: "P")


def test_denom_asing_diabaikan():
    out = process_print_job(_job(qty={"100000": 1, "999": 5, "xx": 1}),
                            sender=lambda p: "P")
    assert out["total"] == 100000


def test_expense_masuk_total_penjualan():
    kirim = []
    process_print_job(_job(qty={"100000": 1}, expense_amount=5000),
                      sender=lambda p: kirim.append(p) or "P")
    assert "Rp 105.000".encode() in kirim[0]  # Total Penjualan = fisik+0+expense


def test_size_invalid_ditolak():
    with pytest.raises(ValueError):
        process_print_job(_job(size="A4"), sender=lambda p: "P")


def test_sender_gagal_menggelembung():
    def rusak(p):
        raise RuntimeError("printer macet")

    with pytest.raises(RuntimeError, match="macet"):
        process_print_job(_job(), sender=rusak)
