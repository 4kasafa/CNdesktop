"""State machine watcher, hwnd fake tanpa UIA asli."""
import logging
import os
import tempfile

from src.db import list_since
from src.watcher import Watcher

TUNAI = {"total_raw": "150.000,00", "tunai_raw": "200.000,00", "debit_raw": "0", "bank_raw": ""}


def _watcher(snap=None, nos=None):
    t = [0.0]
    nos = nos if nos is not None else {}
    w = Watcher(db_path=os.path.join(tempfile.mkdtemp(), "w.db"),
                read_dialog_fn=lambda h: dict(snap or TUNAI),
                read_no_fn=lambda m: (nos.get(m, ["Auto"])[0]
                                      if len(nos.get(m, ["Auto"])) == 1
                                      else nos[m].pop(0)),
                enum_fn=lambda: [], clock=lambda: t[0])
    w._tick_time = t
    return w


def _run(w, steps=30):
    for _ in range(steps):
        w.tick()
        w._tick_time[0] += 0.1
        if not w.sessions:
            break


def test_save_flow(caplog):
    w = _watcher(nos={"m1": ["Auto", "7788"]})
    w.on_dialog_open(111, "m1")
    with caplog.at_level(logging.INFO, logger="cndesktop"):
        w.on_invoked(111)
        _run(w)
    rows = list_since(w.db)
    assert len(rows) == 1 and rows[0]["kategori"] == "Tunai" and rows[0]["total"] == 150000
    assert 111 not in w.sessions


def test_timeout_discards(caplog):
    w = _watcher(nos={"m1": ["Auto"] * 100})
    w.on_dialog_open(111, "m1")
    with caplog.at_level(logging.WARNING, logger="cndesktop"):
        w.on_invoked(111)
        _run(w, steps=70)
    assert list_since(w.db) == [] and 111 not in w.sessions
    assert "needs_review" in caplog.text


def test_close_with_number_saves():
    """Tutup-dialog + no sudah angka (hook INVOKED mati) -> tetap tersimpan."""
    w = _watcher(nos={"m1": ["9001"]})
    w.on_dialog_open(111, "m1")
    _run(w, steps=5)
    w.on_dialog_close(111)
    rows = list_since(w.db)
    assert len(rows) == 1 and rows[0]["no_transaksi"] == "9001"


def test_close_auto_discards_silent(caplog):
    """Tutup-dialog + masih Auto (= Batal) -> discard tanpa warning."""
    w = _watcher()
    w.on_dialog_open(111, "m1")
    _run(w, steps=5)
    with caplog.at_level(logging.WARNING, logger="cndesktop"):
        w.on_dialog_close(111)
    assert list_since(w.db) == [] and "needs_review" not in caplog.text


def test_close_without_save():
    w = _watcher()
    w.on_dialog_open(111, "m1")
    _run(w, steps=5)
    w.on_dialog_close(111)
    assert list_since(w.db) == []


def test_multi_hwnd():
    w = _watcher(nos={"m1": ["9001"], "m2": ["9002"]})
    w.on_dialog_open(111, "m1")
    w.on_dialog_open(222, "m2")
    w.on_invoked(111)
    w.on_invoked(222)
    _run(w)
    assert len(list_since(w.db)) == 2


def test_double_invoked_one_row():
    w = _watcher(nos={"m1": ["9001", "9001"]})
    w.on_dialog_open(111, "m1")
    w.on_invoked(111)
    w.on_invoked(111)
    _run(w)
    assert len(list_since(w.db)) == 1


def test_reattach_after_kill():
    """Simulasi kill Ketoko -> buka lagi: sesi dibersihkan lalu terdeteksi ulang."""
    import tempfile
    t = [0.0]
    wins = [(555, "Pembayaran")]
    w = Watcher(db_path=os.path.join(tempfile.mkdtemp(), "r.db"),
                read_dialog_fn=lambda h: dict(TUNAI),
                read_no_fn=lambda m: "Auto",
                enum_fn=lambda: list(wins), clock=lambda: t[0])
    w._reconcile()
    assert 555 in w.sessions  # dialog terdeteksi
    wins.clear()  # kill: semua window hilang (hwnd fake -> _alive False)
    t[0] += 10.0
    w.tick()  # tutup -> closed-watch
    assert 555 in w.sessions
    t[0] += 10.0
    w.tick()  # deadline lewat -> dibersihkan, tanpa crash
    assert 555 not in w.sessions
    wins.append((555, "Pembayaran"))  # buka lagi
    w._reconcile()
    assert 555 in w.sessions  # terdeteksi ulang


def test_close_watch_late_number_saves():
    """Nomor muncul SETELAH tutup (timing kasir) -> watch pasca-tutup simpan."""
    w = _watcher(nos={"m1": ["Auto"] * 10 + ["9001"] * 60})
    w.on_dialog_open(111, "m1")
    _run(w, steps=5)
    w.on_dialog_close(111)
    assert 111 in w.sessions  # closed-watch, belum discard
    _run(w, steps=60)
    rows = list_since(w.db)
    assert len(rows) == 1 and rows[0]["no_transaksi"] == "9001"


def test_no_transition_logged(caplog):
    """Transisi Auto->angka->Auto tercatat di log (peta timing nomor)."""
    w = _watcher(nos={"m1": ["Auto", "Auto", "9001", "Auto", "Auto"]})
    w.on_dialog_open(111, "m1")
    with caplog.at_level(logging.INFO, logger="cndesktop"):
        _run(w, steps=15)
    assert "'Auto' -> '9001'" in caplog.text and "'9001' -> 'Auto'" in caplog.text


def test_mismatch_review(caplog):
    """Pola tak dikenal (ala Deposit/Kredit/E-Money): needs_review, tanpa save/crash."""
    w = _watcher(snap={"total_raw": "100.000,00", "tunai_raw": "0",
                       "debit_raw": "30.000,00", "bank_raw": "BCA"},
                 nos={"m1": ["9001"]})
    w.on_dialog_open(111, "m1")
    with caplog.at_level(logging.WARNING, logger="cndesktop"):
        w.on_invoked(111)
        _run(w)
    assert list_since(w.db) == [] and "needs_review" in caplog.text


def test_incomplete_data_review(caplog):
    w = _watcher(snap={"total_raw": "", "tunai_raw": "", "debit_raw": "", "bank_raw": ""},
                 nos={"m1": ["9001"]})
    w.on_dialog_open(111, "m1")
    with caplog.at_level(logging.WARNING, logger="cndesktop"):
        w.on_invoked(111)
        _run(w)
    assert list_since(w.db) == [] and "needs_review" in caplog.text
