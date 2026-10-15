"""CLI lokal `cnd`: cek data/log via file langsung, kontrol via HTTP localhost.

Dipakai: CNdesktop.exe cnd status|data|log|port|watcher|wipe|quit|pin.
Stdlib saja. data/log jalan walau service mati; kontrol butuh service jalan.
"""
import argparse
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


def _base(host, port):
    return f"http://{host}:{port}"


def _http(timeout=5):
    return timeout


def _get(base, path, timeout=5):
    try:
        with urllib.request.urlopen(base + path, timeout=timeout) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.load(e)
        except Exception:
            return e.code, {"error": str(e)}
    except Exception as e:
        return 0, {"error": f"tak tersambung ke {base}: {e}"}


def _post(base, path, obj, timeout=5):
    data = json.dumps(obj or {}).encode()
    req = urllib.request.Request(base + path, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.load(e)
        except Exception:
            return e.code, {"error": str(e)}
    except Exception as e:
        return 0, {"error": f"tak tersambung ke {base}: {e}"}


def _fail(code, body):
    err = body.get("error", body) if isinstance(body, dict) else body
    print(f"GAGAL {code}: {err}", file=sys.stderr)
    return 1


def _db_connect(path, retries=5):
    last = None
    for _ in range(retries):
        try:
            con = sqlite3.connect(path)
            con.execute("PRAGMA busy_timeout=2000")  # ponytail: tunggu lock max 2 dtk
            return con
        except sqlite3.OperationalError as e:
            last = e
            time.sleep(0.1)
    raise last


def cmd_status(a):
    code, body = _get(_base(a.host, a.port), "/api/status")
    if code == 404:  # ponytail: server lama tanpa /status -> fallback health
        code, body = _get(_base(a.host, a.port), "/api/health")
        if code == 200:
            body = {"ok": True, "note": "server lama, tanpa /api/status"}
    if code != 200:
        return _fail(code, body)
    if a.json:
        print(json.dumps(body, indent=1))
        return 0
    if body.get("note"):
        print(f"catatan : {body['note']}")
    get = body.get
    print(f"versi   : {get('version', '?')}")
    if get("ip"):
        print(f"alamat  : {get('ip')}:{get('port', a.port)}")
    else:
        print(f"port    : {get('port', a.port)}")
    print(f"watcher : {'jalan' if get('watcher_alive') else 'mati'}"
          f" (enabled={get('watcher_enabled')})")
    print(f"ketoko  : {get('ketoko')}")
    print(f"terakhir: {get('last_no')} (hari ini: {get('count_today')})")
    if get("db_busy"):
        print("catatan : DB sibuk")
    return 0


def cmd_data(a):
    from src.db import default_path
    path = a.db or default_path()
    limit = max(1, min(200, a.limit))
    try:
        con = _db_connect(path)
    except Exception as e:
        print(f"GAGAL buka DB {path}: {e}", file=sys.stderr)
        return 1
    try:
        con.row_factory = sqlite3.Row
        if a.today:
            rows = con.execute(
                "SELECT id,no_transaksi,total,kategori,created_at FROM transactions "
                "WHERE date(created_at) = date('now','localtime') "
                "AND id > ? ORDER BY id ASC LIMIT ?",
                (a.since, limit)).fetchall()
        else:
            rows = con.execute(
                "SELECT id,no_transaksi,total,kategori,created_at FROM transactions "
                "WHERE id > ? ORDER BY id ASC LIMIT ?",
                (a.since, limit)).fetchall()
        rows = [dict(r) for r in rows]
    except Exception as e:
        print(f"GAGAL baca DB: {e}", file=sys.stderr)
        return 1
    finally:
        try:
            con.close()
        except Exception:
            pass
    if a.json:
        print(json.dumps(rows, indent=1))
        return 0
    if not rows:
        print("(kosong)")
        return 0
    for r in rows:
        print(f"{r['id']:>5} {r['no_transaksi']:<22} {r['total']:>10} "
              f"{r['kategori']:<8} {r['created_at']}")
    return 0


def cmd_log(a):
    import os
    from src.config import LOG_FILE, LOG_SUBDIR, app_dir
    tail = max(1, min(1000, a.tail))
    p = os.path.join(app_dir(), LOG_SUBDIR, LOG_FILE)
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()[-tail:]
    except FileNotFoundError:
        print("(log belum ada)")
        return 0
    except Exception as e:
        print(f"GAGAL baca log: {e}", file=sys.stderr)
        return 1
    if a.json:
        print(json.dumps(lines, indent=1))
        return 0
    for ln in lines:
        print(ln)
    return 0


def cmd_port(a):
    base = _base(a.host, a.port)
    if not a.new_port:
        code, body = _get(base, "/api/status")
        if code == 200 and "port" in body:
            print(body["port"] if a.json else f"port: {body['port']}")
            return 0
        from src.config import PORT
        print(PORT if a.json else f"port: {PORT} (default, status tak tersedia)")
        return 0 if code == 200 else _fail(code, body)
    if not a.pin:
        print("GAGAL: butuh --pin", file=sys.stderr)
        return 2
    code, body = _post(base, "/api/port", {"pin": a.pin, "port": int(a.new_port)})
    if code != 200:
        return _fail(code, body)
    print(json.dumps(body) if a.json else f"ok, port -> {body['port']}")
    return 0


def cmd_watcher(a):
    base = _base(a.host, a.port)
    mode = (a.mode or "").lower()
    if not mode:
        code, body = _get(base, "/api/watcher")
        if code != 200:
            return _fail(code, body)
        print(json.dumps(body) if a.json
              else f"watcher: {'jalan' if body.get('enabled') else 'mati'}")
        return 0
    if mode not in ("on", "off"):
        print("GAGAL: mode harus on|off", file=sys.stderr)
        return 2
    if not a.pin:
        print("GAGAL: butuh --pin", file=sys.stderr)
        return 2
    code, body = _post(base, "/api/watcher",
                       {"pin": a.pin, "enabled": mode == "on"})
    if code != 200:
        return _fail(code, body)
    print(json.dumps(body) if a.json
          else f"ok, watcher -> {'jalan' if body['enabled'] else 'mati'}")
    return 0


def cmd_wipe(a):
    if not a.pin:
        print("GAGAL: butuh --pin", file=sys.stderr)
        return 2
    if a.confirm != "HAPUS":
        print("GAGAL: butuh --confirm HAPUS", file=sys.stderr)
        return 2
    code, body = _post(_base(a.host, a.port), "/api/wipe",
                       {"pin": a.pin, "confirm": "HAPUS"})
    if code != 200:
        return _fail(code, body)
    print(json.dumps(body) if a.json else f"ok, hapus {body.get('deleted', 0)} transaksi")
    return 0


def cmd_quit(a):
    if not a.pin:
        print("GAGAL: butuh --pin", file=sys.stderr)
        return 2
    code, body = _post(_base(a.host, a.port), "/api/shutdown", {"pin": a.pin})
    if code != 200:
        return _fail(code, body)
    print(json.dumps(body) if a.json else "ok, CNdesktop berhenti")
    return 0


def cmd_pin(a):
    if not a.pin or not a.new_pin:
        print("GAGAL: butuh --pin <lama> --new-pin <6 digit>", file=sys.stderr)
        return 2
    code, body = _post(_base(a.host, a.port), "/api/pin",
                       {"pin": a.pin, "new_pin": a.new_pin})
    if code != 200:
        return _fail(code, body)
    print(json.dumps(body) if a.json else "ok, PIN baru tersimpan")
    return 0


def build_parser():
    from src.config import PORT
    p = argparse.ArgumentParser(prog="cnd", description="Kontrol CNdesktop via terminal")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=PORT)
    p.add_argument("--db", default="")
    p.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    sub = p.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("status")
    st.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    d = sub.add_parser("data")
    d.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    d.add_argument("--since", type=int, default=0)
    d.add_argument("--limit", type=int, default=50)
    d.add_argument("--today", action="store_true")
    lg = sub.add_parser("log")
    lg.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    lg.add_argument("--tail", type=int, default=100)
    pt = sub.add_parser("port")
    pt.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    pt.add_argument("new_port", nargs="?", type=int, default=0)
    pt.add_argument("--pin", default="")
    w = sub.add_parser("watcher")
    w.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    w.add_argument("mode", nargs="?", default="")
    w.add_argument("--pin", default="")
    wp = sub.add_parser("wipe")
    wp.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    wp.add_argument("--pin", default="")
    wp.add_argument("--confirm", default="")
    q = sub.add_parser("quit", aliases=["shutdown"])
    q.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    q.add_argument("--pin", default="")
    pn = sub.add_parser("pin")
    pn.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    pn.add_argument("--pin", default="")
    pn.add_argument("--new-pin", default="")
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    if not hasattr(a, "json"):
        a.json = False  # ponytail: global+sub --json SUPPRESS, absen = False
    fn = {"status": cmd_status, "data": cmd_data, "log": cmd_log,
          "port": cmd_port, "watcher": cmd_watcher, "wipe": cmd_wipe,
          "quit": cmd_quit, "shutdown": cmd_quit, "pin": cmd_pin}[a.cmd]
    return fn(a)


if __name__ == "__main__":
    sys.exit(main())
