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
        if not w.sessions and not w.pending:
            break


def test_save_flow(caplog):
    """Alur utama: tutup + total>0 -> pending, nomor muncul -> tersimpan 1 baris."""
    w = _watcher(nos={"m1": ["Auto", "7788"]})
    w.on_dialog_open(111, "m1")
    with caplog.at_level(logging.INFO, logger="cndesktop"):
        w.on_dialog_close(111)
        _run(w)
    rows = list_since(w.db)
    assert len(rows) == 1 and rows[0]["kategori"] == "Tunai" and rows[0]["total"] == 150000
    assert 111 not in w.sessions


def test_close_with_number_saves():
    """Tutup-dialog + no sudah angka -> pending dulu, tersimpan di poll berikut."""
    w = _watcher(nos={"m1": ["9001"]})
    w.on_dialog_open(111, "m1")
    _run(w, steps=5)
    w.on_dialog_close(111)
    assert 111 not in w.sessions and w.pending is not None and list_since(w.db) == []
    _run(w, steps=10)
    rows = list_since(w.db)
    assert len(rows) == 1 and rows[0]["no_transaksi"] == "9001"


def test_close_auto_goes_pending(caplog):
    """Tutup-dialog + masih Auto + total>0 -> slot pending, tanpa save/warning."""
    w = _watcher()
    w.on_dialog_open(111, "m1")
    _run(w, steps=5)
    with caplog.at_level(logging.WARNING, logger="cndesktop"):
        w.on_dialog_close(111)
    assert list_since(w.db) == [] and "needs_review" not in caplog.text
    assert 111 not in w.sessions and w.pending is not None


def test_close_without_save():
    """Tutup + total>0 tanpa nomor -> pending (save menyusul saat nomor muncul)."""
    w = _watcher()
    w.on_dialog_open(111, "m1")
    _run(w, steps=5)
    w.on_dialog_close(111)
    assert list_since(w.db) == []
    assert 111 not in w.sessions and w.pending is not None


def test_close_empty_discards():
    """Tutup + total kosong (= Batal sejati) -> tanpa pending, tanpa save."""
    w = _watcher(snap={"total_raw": "", "tunai_raw": "", "debit_raw": "", "bank_raw": ""})
    w.on_dialog_open(111, "m1")
    _run(w, steps=5)
    w.on_dialog_close(111)
    assert 111 not in w.sessions and w.pending is None and list_since(w.db) == []


def test_multi_hwnd():
    """Dua penjualan berurutan (tutup-A -> nomor-A -> tutup-B -> nomor-B) -> 2 baris."""
    w = _watcher(nos={"m1": ["Auto", "Auto", "9001", "9001"], "m2": ["Auto", "9002"]})
    w.on_dialog_open(111, "m1")
    _run(w, steps=5)
    w.on_dialog_close(111)
    _run(w)  # nomor-A muncul -> save baris 1
    assert len(list_since(w.db)) == 1
    w.on_dialog_open(222, "m2")
    _run(w, steps=5)
    w.on_dialog_close(222)
    _run(w)  # nomor-B muncul -> save baris 2
    assert len(list_since(w.db)) == 2


def test_reattach_after_kill():
    """Simulasi kill Ketoko -> buka lagi: pending tersisa, sesi terdeteksi ulang."""
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
    w.tick()  # tutup -> slot pending (sesi hilang)
    assert 555 not in w.sessions and w.pending is not None
    t[0] += 10.0
    w.tick()  # Auto terus -> tanpa save, tanpa crash
    assert 555 not in w.sessions and list_since(w.db) == []
    wins.append((555, "Pembayaran"))  # buka lagi
    w._reconcile()
    assert 555 in w.sessions  # terdeteksi ulang


def test_close_watch_late_number_saves():
    """Nomor muncul SETELAH tutup -> slot pending + transisi simpan (sekali pakai)."""
    w = _watcher(nos={"m1": ["Auto"] * 10 + ["9001"] * 60})
    w.on_dialog_open(111, "m1")
    _run(w, steps=5)
    w.on_dialog_close(111)
    assert 111 not in w.sessions and w.pending is not None
    _run(w, steps=60)
    rows = list_since(w.db)
    assert len(rows) == 1 and rows[0]["no_transaksi"] == "9001"
    assert w.pending is None


def test_close_watch_formatted_no_saves_both():
    """No dokumen format kasir -> tersimpan utuh + counter benar."""
    w = _watcher(nos={"m1": ["Auto"] * 10 + ["001519/KSR/SURJO/1026"] * 60})
    w.on_dialog_open(111, "m1")
    _run(w, steps=5)
    w.on_dialog_close(111)
    _run(w, steps=60)
    r = list_since(w.db)[0]
    assert r["no_transaksi"] == "001519/KSR/SURJO/1026" and r["no_urut"] == "001519"


def test_pending_late_number_30s():
    """Tutup-Auto lalu nomor muncul 30 dtk kemudian -> tersimpan 1 baris."""
    w = _watcher(nos={"m1": ["Auto"] * 10 + ["9001"] * 60})
    w.on_dialog_open(111, "m1")
    _run(w, steps=5)
    w.on_dialog_close(111)
    w._tick_time[0] += 30.0  # nomor kasir telat 30 dtk (kasus 001529)
    _run(w, steps=60)
    rows = list_since(w.db)
    assert len(rows) == 1 and rows[0]["no_transaksi"] == "9001"


def test_pending_same_number_no_double():
    """Transisi ulang nomor sama -> tidak dobel."""
    w = _watcher(nos={"m1": ["Auto"] * 10 + ["9001"] * 60})
    w.on_dialog_open(111, "m1")
    _run(w, steps=5)
    w.on_dialog_close(111)
    _run(w, steps=60)
    assert len(list_since(w.db)) == 1
    _run(w, steps=30)
    assert len(list_since(w.db)) == 1


def test_pending_cancel_no_save():
    """Batal (Auto terus) -> tidak ada save, pending tetap menunggu."""
    w = _watcher(nos={"m1": ["Auto"] * 100})
    w.on_dialog_open(111, "m1")
    _run(w, steps=5)
    w.on_dialog_close(111)
    _run(w, steps=60)
    assert list_since(w.db) == []


def test_tick_empty_read_keeps_snap():
    """T1: baca penuh lalu baca kosong -> snapshot lama utuh."""
    calls = [{"total_raw": "150.000,00", "tunai_raw": "200.000,00", "debit_raw": "0", "bank_raw": ""},
             {"total_raw": "", "tunai_raw": "", "debit_raw": "", "bank_raw": ""}]
    import tempfile
    t = [0.0]
    w = Watcher(db_path=os.path.join(tempfile.mkdtemp(), "m.db"),
                read_dialog_fn=lambda h: dict(calls[0] if t[0] < 0.4 else calls[1]),
                read_no_fn=lambda m: "Auto",
                enum_fn=lambda: [], clock=lambda: t[0])
    w._tick_time = t
    w.on_dialog_open(111, "m1")
    for _ in range(6):
        w.tick()
        t[0] += 0.1
    assert w.sessions[111]["snap"].get("total_raw") == "150.000,00"


def test_no_transition_logged(caplog):
    """Transisi Auto->angka->Auto tercatat di log (peta timing nomor, tanpa dialog)."""
    w = _watcher(nos={"m1": ["Auto", "9001", "Auto", "Auto"]})
    w.on_dialog_open(111, "m1")
    w.on_dialog_close(111)
    w._main = "m1"  # simulasi enum sudah menemukan window utama
    with caplog.at_level(logging.INFO, logger="cndesktop"):
        for _ in range(25):  # manual (tanpa break dini _run) agar transisi pasca-save ikut terbaca
            w.tick()
            w._tick_time[0] += 0.1
    assert "'Auto' -> '9001'" in caplog.text and "'9001' -> 'Auto'" in caplog.text


def test_mismatch_review(caplog):
    """Pola tak dikenal (ala Deposit/Kredit/E-Money): needs_review, tanpa save/crash."""
    w = _watcher(snap={"total_raw": "100.000,00", "tunai_raw": "0",
                       "debit_raw": "30.000,00", "bank_raw": "BCA"},
                 nos={"m1": ["9001"]})
    w.on_dialog_open(111, "m1")
    with caplog.at_level(logging.WARNING, logger="cndesktop"):
        w.on_dialog_close(111)
        _run(w)
    assert list_since(w.db) == [] and "needs_review" in caplog.text


def test_incomplete_data_review(caplog):
    """Total ada tapi komposisi tak lengkap (debit separuh tanpa bank) -> needs_review, tanpa save."""
    w = _watcher(snap={"total_raw": "150.000,00", "tunai_raw": "", "debit_raw": "50.000,00", "bank_raw": ""},
                 nos={"m1": ["9001"]})
    w.on_dialog_open(111, "m1")
    with caplog.at_level(logging.WARNING, logger="cndesktop"):
        w.on_dialog_close(111)
        _run(w)
    assert list_since(w.db) == [] and "needs_review" in caplog.text


def test_blink_250ms_saves():
    """Kedip nomor 250ms (ala 001641:259ms) tetap tertangkap polling 75ms."""
    import tempfile
    t = [0.0]
    w = Watcher(db_path=os.path.join(tempfile.mkdtemp(), "b.db"),
                read_dialog_fn=lambda h: dict(TUNAI),
                read_no_fn=lambda m: "9001" if 0.6 <= t[0] < 0.85 else "Auto",
                enum_fn=lambda: [], clock=lambda: t[0])
    w._tick_time = t
    w.on_dialog_open(111, "m1")
    for _ in range(5):  # 0.0-0.5: isi snap
        w.tick()
        t[0] += 0.1
    w.on_dialog_close(111)  # pending di t=0.5
    assert w.pending is not None
    for _ in range(10):  # 0.5-1.5: lewati jendela kedip 0.6-0.85
        w.tick()
        t[0] += 0.1
    rows = list_since(w.db)
    assert len(rows) == 1 and rows[0]["no_transaksi"] == "9001"


def test_number_before_close_pairs_active():
    """Nomor datang 14ms sebelum tutup (ala 001643) -> pakai snap sesi-aktif, bukan pending basi."""
    new = {"total_raw": "44.600,00", "tunai_raw": "50.000,00", "debit_raw": "0", "bank_raw": ""}
    old = {"total_raw": "25.200,00", "tunai_raw": "25.200,00", "debit_raw": "0", "bank_raw": ""}
    w = _watcher(snap=new, nos={"m1": ["Auto", "001643/KSR/SURJO/1026", "Auto"]})
    w.on_dialog_open(222, "m1")
    _run(w, steps=5)  # isi snap sesi-aktif = 44600
    assert w.sessions[222]["snap"].get("total_raw") == "44.600,00"
    w.pending = {"snap": dict(old), "main": "m1", "t": w._tick_time[0] - 312.9}  # paksa basi ala 001642
    _run(w)
    rows = list_since(w.db)
    assert len(rows) == 1 and rows[0]["total"] == 44600 and rows[0]["no_urut"] == "001643"
    assert w.pending is None and 222 not in w.sessions
    w.on_dialog_close(222)  # close susulan: sesi sudah dikonsumsi -> tanpa duplikat
    _run(w, steps=10)
    assert len(list_since(w.db)) == 1


def test_open_clears_stale_pending():
    """Sesi baru membersihkan pending basi tanpa nomor."""
    w = _watcher()
    w.on_dialog_open(111, "m1")
    _run(w, steps=5)
    w.on_dialog_close(111)
    assert w.pending is not None
    w.on_dialog_open(222, "m1")
    assert w.pending is None and 222 in w.sessions


def test_obj_filter():
    """WinEvent non-window (_obj != 0) diabaikan: tanpa sesi baru / tanpa false-close."""
    import src.watcher as W
    w = _watcher()
    orig_proc, orig_title = W.get_window_process_name, W._title
    W.get_window_process_name = lambda h: "KetokoD.exe"
    W._title = lambda h: "Pembayaran"
    try:
        w.on_dialog_open(111, "m1")
        _run(w, steps=5)
        w._event(None, W.EV_HIDE, 111, 1, 0, 0, 0)  # false close -> abaikan
        assert 111 in w.sessions and w.pending is None
        w._event(None, W.EV_HIDE, 111, 0, 0, 0, 0)  # close asli
        assert 111 not in w.sessions and w.pending is not None
    finally:
        W.get_window_process_name, W._title = orig_proc, orig_title


def test_unread_bukan_batal(caplog):
    """Snap tak pernah terbaca (reader selalu kosong) -> warning gagal-baca, bukan batal diam."""
    w = _watcher(snap={"total_raw": "", "tunai_raw": "", "debit_raw": "", "bank_raw": ""})
    w.on_dialog_open(111, "m1")
    _run(w, steps=5)  # tick baca kosong terus -> seen tetap False
    assert w.sessions[111].get("seen") is False
    with caplog.at_level(logging.WARNING, logger="cndesktop"):
        w.on_dialog_close(111)  # fallback read juga kosong
    assert "gagal-baca" in caplog.text
    assert w.pending is None and list_since(w.db) == []


def test_blink_150ms_saves():
    """Kedip nomor 150ms tetap tertangkap polling 30ms + reader cepat."""
    import tempfile
    t = [0.0]
    w = Watcher(db_path=os.path.join(tempfile.mkdtemp(), "b150.db"),
                read_dialog_fn=lambda h: dict(TUNAI),
                read_no_fn=lambda m: "9002" if 0.6 <= t[0] < 0.75 else "Auto",
                enum_fn=lambda: [], clock=lambda: t[0])
    w._tick_time = t
    w.on_dialog_open(111, "m1")
    for _ in range(5):  # 0.0-0.5: isi snap
        w.tick()
        t[0] += 0.1
    w.on_dialog_close(111)  # pending di t=0.5
    assert w.pending is not None
    for _ in range(10):  # 0.5-1.5: lewati jendela kedip 0.60-0.75
        w.tick()
        t[0] += 0.1
    rows = list_since(w.db)
    assert len(rows) == 1 and rows[0]["no_transaksi"] == "9002"
