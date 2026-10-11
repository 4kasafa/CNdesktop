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
    assert body == {"ok": True, "printer": "MockPrinter", "total": 205000}
    assert b"Surjo" in kirim[0]


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
