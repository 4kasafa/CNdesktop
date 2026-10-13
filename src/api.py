"""API LAN untuk HP polling (PRD §6). Stdlib http.server, PIN untuk aksi sensitif."""
import json
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from src.config import PORT
from src.db import get_watcher_enabled, get_wipe_pin, list_since

# ponytail: lockout gabungan wipe+watcher di memori (5x salah = kunci 5 mnt)
_pin_fail = {"count": 0, "locked_until": 0.0}
_pin_lock = threading.Lock()
MAX_FAIL, LOCK_SECS = 5, 5 * 60


def _locked():
    with _pin_lock:
        return time.monotonic() < _pin_fail["locked_until"]


def _note_fail():
    with _pin_lock:
        _pin_fail["count"] += 1
        if _pin_fail["count"] >= MAX_FAIL:
            _pin_fail["locked_until"] = time.monotonic() + LOCK_SECS
        return _pin_fail["count"]


def _reset_fail():
    with _pin_lock:
        _pin_fail["count"] = 0
        _pin_fail["locked_until"] = 0.0


def reset_pin_lockout():  # untuk test
    _reset_fail()


def _cors(h):
    h.send_header("Access-Control-Allow-Origin", "*")
    h.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    h.send_header("Access-Control-Allow-Headers", "Content-Type, X-Token")


def _send(h, code, obj):
    body = json.dumps(obj).encode()
    h.send_response(code)
    h.send_header("Content-Type", "application/json")
    h.send_header("Cache-Control", "no-store")
    _cors(h)
    h.send_header("Content-Length", str(len(body)))
    h.end_headers()
    h.wfile.write(body)


class Handler(BaseHTTPRequestHandler):
    db_path = ""
    watcher = None
    _print_active = False
    _print_lock = threading.Lock()

    def log_message(self, *a):
        pass  # ponytail: silent, logging terpusat Fase 6

    def do_OPTIONS(self):
        self.send_response(204)
        _cors(self)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _body_obj(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except (ValueError, TypeError):
            length = 0
        try:
            data = json.loads(self.rfile.read(max(0, length)) or b"null")
        except (ValueError, UnicodeDecodeError):
            return None, _send(self, 400, {"error": "body harus JSON valid"})
        if not isinstance(data, dict):
            return None, _send(self, 400, {"error": "body harus objek JSON"})
        return data, None

    def _check_pin(self, pin):
        if _locked():
            _send(self, 429, {"error": "terkunci 5 menit, coba lagi"})
            return False
        try:
            expect = get_wipe_pin(self.db_path)
        except Exception:
            expect = "363636"
        if (pin or "") != expect:
            _note_fail()
            _send(self, 403, {"error": "PIN salah"})
            return False
        _reset_fail()
        return True

    def _db_busy(self):
        try:
            w = self.watcher
            return bool(w is not None and w.db_busy())
        except Exception:
            return False

    def _print_busy(self):
        try:
            with Handler._print_lock:
                return Handler._print_active
        except Exception:
            return False

    def _handle_wipe(self, data):
        if not self._check_pin(data.get("pin")):
            return
        if data.get("confirm") != "HAPUS":
            return _send(self, 400, {"error": "confirm harus 'HAPUS'"})
        if self._print_busy() or self._db_busy():
            return _send(self, 409, {"error": "PC sibuk, coba lagi"})
        from src.db import wipe_transactions
        from src.log import clear_logs
        try:
            n = wipe_transactions(self.db_path)
        except Exception as e:
            return _send(self, 500, {"error": str(e)})
        try:
            clear_logs()
        except Exception as e:
            return _send(self, 500, {"error": f"hapus log gagal: {e}"})
        return _send(self, 200, {"ok": True, "deleted": n, "log_cleared": True})

    def _handle_watcher_post(self, data):
        if not self._check_pin(data.get("pin")):
            return
        if not isinstance(data.get("enabled"), bool):
            return _send(self, 400, {"error": "enabled harus bool"})
        w = self.watcher
        if w is None:
            try:
                from src.db import set_watcher_enabled
                set_watcher_enabled(self.db_path, data["enabled"])
            except Exception as e:
                return _send(self, 500, {"error": str(e)})
        else:
            try:
                w.set_enabled(data["enabled"])
            except Exception as e:
                return _send(self, 500, {"error": str(e)})
        return _send(self, 200, {"ok": True, "enabled": bool(data["enabled"])})

    def do_POST(self):
        try:
            path = urllib.parse.urlparse(self.path).path
            if path == "/api/wipe":
                data, err = self._body_obj()
                if err is not None:
                    return err
                return self._handle_wipe(data)
            if path == "/api/watcher":
                data, err = self._body_obj()
                if err is not None:
                    return err
                return self._handle_watcher_post(data)
            if path != "/api/print":
                return _send(self, 404, {"error": "not found"})
            data, err = self._body_obj()
            if err is not None:
                return err
            from src.receipt import process_print_job
            with Handler._print_lock:
                Handler._print_active = True
            try:
                out = process_print_job(data)
            except ValueError as e:
                return _send(self, 400, {"error": str(e)})
            except Exception as e:
                return _send(self, 500, {"error": str(e)})
            finally:
                with Handler._print_lock:
                    Handler._print_active = False
            return _send(self, 200, {"ok": True, "printer": out["printer"],
                                     "total": out["total"],
                                     "nontunai": out["nontunai"],
                                     "sales_total": out["sales_total"]})
        except BrokenPipeError:
            pass

    def do_GET(self):
        try:
            path = urllib.parse.urlparse(self.path).path
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if path == "/api/health":
                return _send(self, 200, {"ok": True})
            if path == "/api/watcher":
                try:
                    enabled = self.watcher.is_enabled() if self.watcher is not None \
                        else get_watcher_enabled(self.db_path)
                except Exception:
                    enabled = True
                return _send(self, 200, {"enabled": bool(enabled)})
            if path == "/api/transactions":
                try:
                    since = int(qs.get("since", ["0"])[0])
                    if since < 0:
                        raise ValueError
                except (ValueError, TypeError):
                    return _send(self, 400, {"error": "since harus integer >= 0"})
                try:
                    limit = max(1, min(50, int(qs.get("limit", ["50"])[0])))
                except (ValueError, TypeError):
                    limit = 50
                return _send(self, 200, list_since(self.db_path, since, limit))
            return _send(self, 404, {"error": "not found"})
        except BrokenPipeError:
            pass


def serve(db_path, port=PORT, watcher=None):
    """Blokir. Untuk test: port=0 lalu baca server.server_port."""
    Handler.db_path = db_path
    Handler.watcher = watcher
    with ThreadingHTTPServer(("0.0.0.0", port), Handler) as srv:
        srv.serve_forever()


def start_bg(db_path, port=PORT, watcher=None):
    """Jalan di thread daemon. Return server (stop: server.shutdown())."""
    Handler.db_path = db_path
    Handler.watcher = watcher
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True).start()
    return srv


if __name__ == "__main__":
    import sys
    from src.db import init_db
    serve(init_db(), int(sys.argv[1]) if len(sys.argv) > 1 else PORT)
