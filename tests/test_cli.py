"""CLI cnd + endpoint remote baru (status/log/port/pin/shutdown) + Service."""
import json
import os
import tempfile
import urllib.error
import urllib.request

from src.api import reset_pin_lockout, start_bg
from src.cli import build_parser, main
from src.db import init_db, insert_tx
from src.tray import _cli_port, _pre_dispatch


def test_json_flag_semua_posisi():
    assert getattr(build_parser().parse_args(["status"]), "json", False) is False
    assert build_parser().parse_args(["--json", "status"]).json is True
    assert build_parser().parse_args(["status", "--json"]).json is True
    assert build_parser().parse_args(["data", "--today", "--json"]).json is True


def test_pre_dispatch():
    from src.tray import _cli_args
    assert _pre_dispatch(["tray.py", "cnd", "status"]) == "cli"
    assert _pre_dispatch(["tray.py", "--port", "9999", "cnd", "status"]) == "cli"
    assert _pre_dispatch(["tray.py", "--headless"]) == "headless"
    assert _pre_dispatch(["tray.py"]) == "tray"
    assert _cli_args(["tray.py", "--port", "9999", "cnd", "status"]) == ["status"]


def test_cli_port_invalid_exit_2():
    import pytest
    for bad in (["tray.py", "--port", "abc"], ["tray.py", "--port", "99999"],
                ["tray.py", "--port"], ["tray.py", "--port", "0"]):
        with pytest.raises(SystemExit) as e:
            _cli_port(bad, 8765)
        assert e.value.code == 2
    assert _cli_port(["tray.py"], 8765) == 8765
    assert _cli_port(["tray.py", "--port", "1234"], 8765) == 1234


def test_db_connect_busy_timeout(tmp_path):
    from src.cli import _db_connect
    con = _db_connect(str(tmp_path / "b.db"))
    try:
        assert con.execute("PRAGMA busy_timeout").fetchone()[0] == 2000
    finally:
        con.close()


def test_cli_data_langsung_db(tmp_path, capsys):
    db = init_db(str(tmp_path / "d.db"))
    insert_tx(db, "C1", 1000)
    insert_tx(db, "C2", 2000)
    assert main(["--db", db, "data", "--since", "1"]) == 0
    out = capsys.readouterr().out
    assert "C2" in out and "C1" not in out  # since=1 lewati id 1
    assert main(["--db", db, "data", "--today", "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert [r["no_transaksi"] for r in rows] == ["C1", "C2"]


def test_cli_log_baca_file(monkeypatch, tmp_path, capsys):
    d = tmp_path / "logs"
    d.mkdir()
    (d / "cndesktop.log").write_text("a\nb\nc\n", encoding="utf-8")
    monkeypatch.setattr("src.config.app_dir", lambda: str(tmp_path))
    assert main(["log", "--tail", "2"]) == 0
    assert capsys.readouterr().out.splitlines() == ["b", "c"]


def _srv():
    reset_pin_lockout()
    db = init_db(os.path.join(tempfile.mkdtemp(), "n.db"))
    srv = start_bg(db, 0)
    return f"http://127.0.0.1:{srv.server_port}", db, srv


def _get(base, path):
    try:
        with urllib.request.urlopen(base + path) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


def _post(base, path, obj):
    data = json.dumps(obj).encode()
    req = urllib.request.Request(base + path, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


def test_status_bentuk():
    base, db, srv = _srv()
    try:
        insert_tx(db, "S1", 500)
        code, body = _get(base, "/api/status")
        assert code == 200
        assert body["last_no"] == "S1" and body["count_today"] == 1
        assert set(body) >= {"version", "port", "watcher_enabled", "watcher_alive",
                             "db_busy", "ketoko", "uptime_s"}
    finally:
        srv.shutdown()
        reset_pin_lockout()


def test_log_pin_dan_tail():
    base, db, srv = _srv()
    try:
        code, _ = _get(base, "/api/log?pin=salah&tail=5")
        assert code == 403  # PIN salah ikut lockout gabungan
        code, body = _get(base, "/api/log?pin=363636&tail=2")
        assert code == 200 and body["tail"] == 2 and isinstance(body["lines"], list)
        code, _ = _get(base, "/api/log?pin=363636&tail=9999")
        assert code == 400  # cap 1000
    finally:
        srv.shutdown()
        reset_pin_lockout()


def test_port_validasi_pin():
    base, db, srv = _srv()
    try:
        assert _post(base, "/api/port", {"pin": "salah", "port": 8765})[0] == 403
        code, _ = _post(base, "/api/port", {"pin": "363636", "port": 99999})
        assert code == 400
        code, body = _post(base, "/api/port", {"pin": "363636", "port": 8765})
        assert code == 200 and body["port"] == 8765  # tanpa service = validasi saja
    finally:
        srv.shutdown()
        reset_pin_lockout()


def test_pin_baru_bersama():
    from src.db import get_wipe_pin
    base, db, srv = _srv()
    try:
        assert _post(base, "/api/pin", {"pin": "363636", "new_pin": "12"})[0] == 400
        assert _post(base, "/api/pin", {"pin": "363636", "new_pin": "654321"})[0] == 200
        assert get_wipe_pin(db) == "654321"
    finally:
        srv.shutdown()
        reset_pin_lockout()


def test_shutdown_ok_tanpa_exit():
    base, db, srv = _srv()
    try:
        assert _post(base, "/api/shutdown", {"pin": "salah"})[0] == 403
        code, body = _post(base, "/api/shutdown", {"pin": "363636"})
        assert (code, body) == (200, {"ok": True})  # PYTEST guard: tanpa _exit
    finally:
        srv.shutdown()
        reset_pin_lockout()


def test_service_status_dan_port_invalid(tmp_path):
    import pytest
    from src.service import Service
    s = Service(db_path=str(tmp_path / "s.db"), port=8765)
    st = s.status()
    assert st["port"] == 8765 and st["last_no"] == "-"
    with pytest.raises(ValueError):
        s.restart_port(99999)


def test_cli_status_dan_watcher(capsys):
    base, db, srv = _srv()
    try:
        port = str(srv.server_port)
        assert main(["--port", port, "status"]) == 0
        assert "versi" in capsys.readouterr().out
        assert main(["--port", port, "watcher", "off", "--pin", "363636"]) == 0
        assert "mati" in capsys.readouterr().out
    finally:
        srv.shutdown()
        reset_pin_lockout()


def test_qr_lines():
    from src.cli import _qr_lines
    ls = _qr_lines([[1, 0], [0, 1]])
    assert len(ls) == 5 and all(len(ln) == 10 for ln in ls)
    assert ls == [" " * 10] * 2 + ["    \u2580\u2584    "] + [" " * 10] * 2


def test_cli_qr_integrasi(capsys):
    base, db, srv = _srv()
    try:
        port = str(srv.server_port)
        assert main(["--port", port, "qr"]) == 0
        out = capsys.readouterr().out
        assert "http://" in out and f":{port}" in out
        assert any(c in out for c in "\u2588\u2580\u2584")
        assert "\x1b" not in out  # non-tty -> tanpa escape
    finally:
        srv.shutdown()
        reset_pin_lockout()


def test_cli_qr_json(capsys):
    base, db, srv = _srv()
    try:
        port = str(srv.server_port)
        assert main(["--port", port, "qr", "--json"]) == 0
        out = capsys.readouterr().out
        d = json.loads(out)
        assert set(d) == {"url"}
        assert d["url"].startswith("http://") and d["url"].endswith(f":{port}")
        assert not any(c in out for c in "\u2588\u2580\u2584")
    finally:
        srv.shutdown()
        reset_pin_lockout()


def test_cli_qr_server_mati(capsys):
    assert main(["--port", "59999", "qr"]) == 1
    assert "GAGAL" in capsys.readouterr().err
