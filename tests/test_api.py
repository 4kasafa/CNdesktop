"""API LAN: health, polling since tanpa duplikat, since invalid → 400."""
import json
import os
import tempfile
import urllib.error
import urllib.request

from src.api import start_bg
from src.db import init_db, insert_tx

BASE = None
DB = None


def setup_module():
    global BASE, DB
    DB = init_db(os.path.join(tempfile.mkdtemp(), "a.db"))
    for i, kat in enumerate(["Tunai", "Nontunai", "Split"], 1):
        insert_tx(DB, f"TRX{i}", i * 10000, kategori=kat)
    srv = start_bg(DB, 0)
    BASE = f"http://127.0.0.1:{srv.server_port}"
    srv._test_ref = srv  # ponytail: daemon thread mati ikut proses test


def _get(path):
    try:
        with urllib.request.urlopen(BASE + path) as r:
            return r.status, json.load(r), r.headers
    except urllib.error.HTTPError as e:
        return e.code, json.load(e), e.headers


def test_health():
    code, body, h = _get("/api/health")
    assert (code, body) == (200, {"ok": True})
    assert h["Access-Control-Allow-Origin"] == "*"


def test_polling_no_dup_asc():
    code, rows, h = _get("/api/transactions?since=0")
    assert code == 200 and [r["id"] for r in rows] == [1, 2, 3]
    assert h["Cache-Control"] == "no-store"
    assert set(rows[0]) >= {"id", "no_transaksi", "total", "tunai", "nontunai",
                            "bank", "kategori", "created_at"}
    code, rows2, _ = _get(f"/api/transactions?since={rows[-1]['id']}")
    assert (code, rows2) == (200, [])


def test_since_invalid_400():
    code, body, _ = _get("/api/transactions?since=abc")
    assert code == 400 and "error" in body


def test_unknown_404():
    code, _, h = _get("/nope")
    assert code == 404
    assert h["Access-Control-Allow-Origin"] == "*"


def test_options_204_cors():
    req = urllib.request.Request(BASE + "/api/health", method="OPTIONS",
                                 headers={"Origin": "capacitor://localhost"})
    with urllib.request.urlopen(req) as r:
        assert r.status == 204
        assert r.headers["Access-Control-Allow-Origin"] == "*"
        assert "GET" in r.headers["Access-Control-Allow-Methods"]
        assert r.headers["Content-Length"] == "0"


def test_cors_on_400():
    code, _, h = _get("/api/transactions?since=abc")
    assert code == 400
    assert h["Access-Control-Allow-Origin"] == "*"


def _post(path, obj=None, raw=None):
    data = raw if raw is not None else json.dumps(obj or {}).encode()
    req = urllib.request.Request(BASE + path, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


def _job():
    return {"kasir": "Surjo", "branch": "Cabang A", "shift": "Pagi",
            "user_id": "K01", "qty": {"100000": 2, "5000": 1},
            "expense_amount": 10000, "expense_note": "Potongan", "size": "58"}


def test_print_ok_mock_sender(monkeypatch):
    import src.receipt as rcpt
    kirim = []
    monkeypatch.setattr(rcpt, "send_to_printer",
                        lambda p: kirim.append(p) or "MockPrinter")
    code, body = _post("/api/print", _job())
    assert code == 200
    assert body == {"ok": True, "printer": "MockPrinter", "total": 205000,
                    "nontunai": 0, "sales_total": 215000}
    assert b"Surjo" in kirim[0]


def test_print_nontunai_ok(monkeypatch):
    import src.receipt as rcpt
    kirim = []
    monkeypatch.setattr(rcpt, "send_to_printer",
                        lambda p: kirim.append(p) or "MockPrinter")
    code, body = _post("/api/print", _job() | {"qty": {"100000": 1},
                                               "expense_amount": 5000,
                                               "nontunai_amount": 50000})
    assert code == 200
    assert body == {"ok": True, "printer": "MockPrinter", "total": 100000,
                    "nontunai": 50000, "sales_total": 155000}
    assert "Rp 50.000".encode() in kirim[0]


def test_print_nontunai_negatif_400():
    code, body = _post("/api/print", _job() | {"nontunai_amount": -100})
    assert code == 400 and "negatif" in body["error"]


def test_print_nontunai_saja_lolos(monkeypatch):
    import src.receipt as rcpt
    monkeypatch.setattr(rcpt, "send_to_printer", lambda p: "MockPrinter")
    code, body = _post("/api/print", _job() | {"qty": {},
                                               "nontunai_amount": 50000})
    assert code == 200 and body["nontunai"] == 50000 and body["total"] == 0


def test_print_tanpa_nontunai_backward_compat(monkeypatch):
    import src.receipt as rcpt
    monkeypatch.setattr(rcpt, "send_to_printer", lambda p: "MockPrinter")
    d = _job()
    d.pop("nontunai_amount", None)
    assert "nontunai_amount" not in d
    code, body = _post("/api/print", d)
    assert code == 200 and body["nontunai"] == 0


def test_print_validasi_400():
    code, body = _post("/api/print", _job() | {"kasir": ""})
    assert code == 400 and "error" in body
    code, body = _post("/api/print", _job() | {"qty": {}})
    assert code == 400 and "error" in body


def test_print_malformed_400():
    code, body = _post("/api/print", raw=b"{bukan json")
    assert code == 400 and "error" in body
    code, body = _post("/api/print", raw=b"[1,2]")
    assert code == 400 and "error" in body


def test_print_printer_gagal_500(monkeypatch):
    import src.receipt as rcpt

    def rusak(p):
        raise RuntimeError("printer macet")

    monkeypatch.setattr(rcpt, "send_to_printer", rusak)
    code, body = _post("/api/print", _job())
    assert code == 500 and "macet" in body["error"]


def test_print_unknown_path_404():
    code, body = _post("/api/other", {})
    assert code == 404


def _new_srv(watcher=None):
    import src.api as api_mod
    db = init_db(os.path.join(tempfile.mkdtemp(), "n.db"))
    srv = start_bg(db, 0, watcher=watcher)
    return f"http://127.0.0.1:{srv.server_port}", db, srv


def _post_to(base, path, obj):
    data = json.dumps(obj).encode()
    req = urllib.request.Request(base + path, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


def _get_from(base, path):
    try:
        with urllib.request.urlopen(base + path) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


def test_wipe_200_hapus_dan_balas_N(monkeypatch):
    import src.api as api_mod
    api_mod.reset_pin_lockout()
    base, db, srv = _new_srv()
    try:
        insert_tx(db, "D1", 1000)
        insert_tx(db, "D2", 2000)
        called = {}
        monkeypatch.setattr("src.log.clear_logs", lambda log_dir=None: called.setdefault("x", True) or 1)
        import src.api as m2
        monkeypatch.setattr(m2.Handler, "db_path", db, raising=False)
        code, body = _post_to(base, "/api/wipe", {"pin": "363636", "confirm": "HAPUS"})
        assert code == 200 and body["deleted"] == 2 and body["log_cleared"] is True
        assert called and insert_tx(db, "D3", 3000) == 1  # ID reset dari 1
    finally:
        srv.shutdown()
        api_mod.reset_pin_lockout()


def test_wipe_400_confirm_salah(monkeypatch):
    import src.api as api_mod
    api_mod.reset_pin_lockout()
    base, db, srv = _new_srv()
    try:
        insert_tx(db, "C1", 1000)
        for bad in ("hapus", "Hapus", "", None):
            code, body = _post_to(base, "/api/wipe", {"pin": "363636", "confirm": bad})
            assert code == 400
        from src.db import list_since
        assert len(list_since(db)) == 1  # 400 tanpa ubah DB
    finally:
        srv.shutdown()
        api_mod.reset_pin_lockout()


def test_wipe_403_pin_salah_tanpa_ubah(monkeypatch):
    import src.api as api_mod
    api_mod.reset_pin_lockout()
    base, db, srv = _new_srv()
    try:
        insert_tx(db, "P1", 1000)
        called = []
        monkeypatch.setattr("src.log.clear_logs", lambda log_dir=None: called.append(1) or 1)
        code, body = _post_to(base, "/api/wipe", {"pin": "000000", "confirm": "HAPUS"})
        assert code == 403
        from src.db import list_since
        assert len(list_since(db)) == 1 and not called
    finally:
        srv.shutdown()
        api_mod.reset_pin_lockout()


def test_wipe_409_saat_sibuk(monkeypatch):
    import src.api as api_mod
    api_mod.reset_pin_lockout()

    class Sibuk:
        def db_busy(self):
            return True
        def is_enabled(self):
            return True

    base, db, srv = _new_srv(watcher=Sibuk())
    try:
        code, body = _post_to(base, "/api/wipe", {"pin": "363636", "confirm": "HAPUS"})
        assert code == 409 and "sibuk" in body["error"].lower()
    finally:
        srv.shutdown()
        api_mod.reset_pin_lockout()


def test_lockout_429_setelah_5_salah():
    import src.api as api_mod
    api_mod.reset_pin_lockout()
    base, db, srv = _new_srv()
    try:
        for _ in range(5):
            code, _ = _post_to(base, "/api/wipe", {"pin": "salah", "confirm": "HAPUS"})
            assert code == 403
        code, body = _post_to(base, "/api/wipe", {"pin": "salah", "confirm": "HAPUS"})
        assert code == 429
    finally:
        srv.shutdown()
        api_mod.reset_pin_lockout()


def test_lockout_reset_saat_pin_benar(monkeypatch):
    import src.api as api_mod
    api_mod.reset_pin_lockout()
    base, db, srv = _new_srv()
    try:
        monkeypatch.setattr("src.log.clear_logs", lambda log_dir=None: 1)
        for _ in range(4):
            _post_to(base, "/api/wipe", {"pin": "salah", "confirm": "HAPUS"})
        code, _ = _post_to(base, "/api/wipe", {"pin": "363636", "confirm": "HAPUS"})
        assert code == 200  # sukses reset hitungan
        code, _ = _post_to(base, "/api/wipe", {"pin": "salah", "confirm": "HAPUS"})
        assert code == 403  # dihitung dari 1 lagi, bukan 429
    finally:
        srv.shutdown()
        api_mod.reset_pin_lockout()


def test_wipe_log_deleted_hapus_6_file(tmp_path):
    from src.log import clear_logs
    d = str(tmp_path)
    open(os.path.join(d, "cndesktop.log"), "w").write("isi")
    for i in range(1, 6):
        open(os.path.join(d, f"cndesktop.log.{i}"), "w").write("lama")
    assert clear_logs(log_dir=d) == 6  # aktif + .1-.5 hilang


def test_wipe_log_recreate_kosong_dan_tulis(tmp_path):
    import logging
    from src.log import clear_logs
    d = str(tmp_path)
    open(os.path.join(d, "cndesktop.log"), "w").write("isi")
    clear_logs(log_dir=d)
    p = os.path.join(d, "cndesktop.log")
    assert os.path.exists(p) and os.path.getsize(p) == 0  # kosong baru
    logging.getLogger("cndesktop").info("cek tulis")
    assert os.path.getsize(p) > 0  # logger tetap tulis ke file baru


def test_watcher_get_bebas_pin():
    import src.api as api_mod
    api_mod.reset_pin_lockout()

    class W:
        def is_enabled(self):
            return False
        def db_busy(self):
            return False

    base, db, srv = _new_srv(watcher=W())
    try:
        code, body = _get_from(base, "/api/watcher")
        assert code == 200 and body == {"enabled": False}
    finally:
        srv.shutdown()


def test_watcher_post_200_sinkron():
    import src.api as api_mod
    from src.db import get_watcher_enabled
    api_mod.reset_pin_lockout()
    base, db, srv = _new_srv()
    try:
        code, body = _post_to(base, "/api/watcher", {"pin": "363636", "enabled": False})
        assert code == 200 and body == {"ok": True, "enabled": False}
        assert get_watcher_enabled(db) is False  # dashboard baca nilai sama
        code, body = _post_to(base, "/api/watcher", {"pin": "363636", "enabled": True})
        assert code == 200 and body["enabled"] is True
    finally:
        srv.shutdown()
        api_mod.reset_pin_lockout()


def test_watcher_post_403_dan_lockout_gabung():
    import src.api as api_mod
    api_mod.reset_pin_lockout()
    base, db, srv = _new_srv()
    try:
        code, _ = _post_to(base, "/api/watcher", {"pin": "salah", "enabled": False})
        assert code == 403
        for _ in range(4):
            _post_to(base, "/api/watcher", {"pin": "salah", "enabled": False})
        code, _ = _post_to(base, "/api/wipe", {"pin": "salah", "confirm": "HAPUS"})
        assert code == 429  # gabung wipe: salah watcher ikut kunci wipe
    finally:
        srv.shutdown()
        api_mod.reset_pin_lockout()


def test_dashboard_pin_salah_batal():
    from src.dashboard import check_watcher_pin
    import tempfile as _t
    from src.db import init_db as _init
    p = _init(os.path.join(_t.mkdtemp(), "dash.db"))
    assert check_watcher_pin(p, "363636") is True  # tiap klik wajib PIN benar
    assert check_watcher_pin(p, "000000") is False  # salah = batal


def test_dashboard_label_sinkron_api():
    from src.dashboard import watcher_status_text
    assert watcher_status_text(False, True) == "watcher: mati"
    assert watcher_status_text(True, True) == "watcher: jalan"
    assert watcher_status_text(True, False) == "watcher: mati"


def test_dashboard_change_pin_lokal():
    from src.dashboard import validate_new_pin
    from src.db import get_wipe_pin, set_wipe_pin
    import tempfile as _t
    from src.db import init_db as _init
    p = _init(os.path.join(_t.mkdtemp(), "pin.db"))
    assert validate_new_pin("12") is not None
    set_wipe_pin(p, "654321")  # simpan lokal, tanpa endpoint remote
    assert get_wipe_pin(p) == "654321"  # PIN lama 363636 kini ditolak
    assert get_wipe_pin(p) != "363636"


def test_wipe_dummy_isolasi(monkeypatch, tmp_path):
    import src.api as api_mod
    api_mod.reset_pin_lockout()
    base, db, srv = _new_srv()
    try:
        insert_tx(db, "X1", 500)
        monkeypatch.setattr("src.log.clear_logs", lambda log_dir=None: 1)
        code, body = _post_to(base, "/api/wipe", {"pin": "363636", "confirm": "HAPUS"})
        from src.db import list_since
        assert code == 200 and list_since(db) == [] and body["deleted"] == 1
        assert insert_tx(db, "X2", 500) == 1
    finally:
        srv.shutdown()
        api_mod.reset_pin_lockout()


def test_watcher_dummy_toggle_persist():
    import src.api as api_mod
    from src.db import get_watcher_enabled
    api_mod.reset_pin_lockout()
    base, db, srv = _new_srv()
    try:
        _post_to(base, "/api/watcher", {"pin": "363636", "enabled": False})
        assert get_watcher_enabled(db) is False
        code, body = _get_from(base, "/api/watcher")
        assert code == 200 and body["enabled"] is False  # konsisten setelah toggle
    finally:
        srv.shutdown()
        api_mod.reset_pin_lockout()
