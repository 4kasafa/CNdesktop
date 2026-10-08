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
    code, body, _ = _get("/api/health")
    assert (code, body) == (200, {"ok": True})


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
    code, _, _ = _get("/nope")
    assert code == 404
