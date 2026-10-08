"""API LAN untuk HP polling (PRD §6). Stdlib http.server, tanpa auth."""
import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from src.config import PORT
from src.db import list_since


def _send(h, code, obj):
    body = json.dumps(obj).encode()
    h.send_response(code)
    h.send_header("Content-Type", "application/json")
    h.send_header("Cache-Control", "no-store")
    h.send_header("Content-Length", str(len(body)))
    h.end_headers()
    h.wfile.write(body)


class Handler(BaseHTTPRequestHandler):
    db_path = ""

    def log_message(self, *a):
        pass  # ponytail: silent, logging terpusat Fase 6

    def do_GET(self):
        try:
            path = urllib.parse.urlparse(self.path).path
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if path == "/api/health":
                return _send(self, 200, {"ok": True})
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


def serve(db_path, port=PORT):
    """Blokir. Untuk test: port=0 lalu baca server.server_port."""
    Handler.db_path = db_path
    with ThreadingHTTPServer(("0.0.0.0", port), Handler) as srv:
        srv.serve_forever()


def start_bg(db_path, port=PORT):
    """Jalan di thread daemon. Return server (stop: server.shutdown())."""
    Handler.db_path = db_path
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True).start()
    return srv


if __name__ == "__main__":
    import sys
    from src.db import init_db
    serve(init_db(), int(sys.argv[1]) if len(sys.argv) > 1 else PORT)
