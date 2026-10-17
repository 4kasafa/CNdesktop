# CNdesktop remote + CLI reference (v1.7.0)

Contract owned by the PC side; the phone side must not reinterpret it.
Default PIN `363636` (change via dashboard or `POST /api/pin`).
Combined lockout for every PIN action: 5 consecutive wrong PINs → `429`
locked for 5 minutes; a correct PIN resets the counter.

Base URL: `http://<PC-IP>:8765`. `cnd` below means `cnd.exe`
(the console companion; `setup_cn.bat` installs it plus a global shim,
so `cnd ...` works from any folder). NOTE: `CNdesktop.exe` is windowed —
`CNdesktop.exe cnd ...` output only appears via pipe/file redirect,
never directly on a `cmd` screen. Always use `cnd.exe` interactively.

## Version matrix

| Since | Feature |
|---|---|
| v1.4.0 | `GET /api/transactions`, `POST /api/print`, `GET /api/health` |
| v1.5.0 | `GET/POST /api/watcher`, `POST /api/wipe` |
| v1.6.0 | `GET /api/status`, `GET /api/log`, `POST /api/port\|pin\|shutdown`, `cnd` CLI, `--headless` |
| v1.7.0 | `cnd qr` (QR URL LAN di terminal, `--json`); `/api/status` fallback kini punya `ip` + port bind aktual |

Older servers answer unknown paths with `404 {"error":"not found"}`.
`cnd status` against an old server falls back to `/api/health` and shows
`?`/`None` fields plus a "legacy server" note — that means: update the PC.

## API endpoints

### GET /api/health (no PIN)

`GET {base}/api/health` → 200 `{"ok": true}`. Liveness probe.

### GET /api/status (no PIN)

`GET {base}/api/status` → 200:

```json
{"version":"1.6.0","ip":"192.168.1.5","port":8765,
 "watcher_enabled":true,"watcher_alive":true,"db_busy":false,
 "ketoko":false,"last_no":"NOTRX-001","count_today":3,"uptime_s":12.5}
```

`watcher_alive` = thread running AND enabled. `ketoko` = Ketoko window
currently detected. `db_busy` = a session/pending write may be in flight
(`POST /api/wipe` returns `409` while true).

### GET /api/transactions (no PIN)

`GET {base}/api/transactions?since=0&limit=50` → 200 array of rows
(`id`, `no_transaksi`, `no_urut`, `total`, `tunai`, `nontunai`, `bank`,
`kategori`, `created_at`), `ORDER BY id ASC`. `since` must be integer ≥ 0
(else 400); `limit` is clamped to 1–50. Phone polling pattern:
remember the last `id`, poll `?since=<id>`.

### GET /api/log (PIN, tail capped at 1000)

`GET {base}/api/log?pin=363636&tail=200`
→ 200 `{"lines":[...],"tail":200}`
| `403` wrong PIN | `429` locked | `400` tail outside 1–1000.
PIN travels in the query string — never store it permanently on the phone.

### GET /api/watcher (no PIN) · POST /api/watcher (PIN)

- `GET {base}/api/watcher` → 200 `{"enabled":bool}`.
- `POST {base}/api/watcher` body `{pin:str, enabled:bool}`
  → 200 `{ok:true, enabled:bool}` | `400` enabled not bool | `403` | `429`.

### POST /api/wipe (PIN, irreversible)

Body `{pin:str, confirm:"HAPUS"}` (exact caps)
→ 200 `{ok:true, deleted:N, log_cleared:true}`
| `400` wrong confirm | `403` | `429` | `409` PC busy (printing/DB write)
| `500` failure. No backup — deleted rows and logs are gone.

### POST /api/print (no PIN)

Body `{kasir, branch, shift, user_id, qty:{denom:count},
expense_amount, expense_note, nontunai_amount?, size:"58"|"80"}`
→ 200 `{ok:true, printer, total, nontunai, sales_total}`
| `400` validation error | `500` printer failure.
Empty `qty` with `nontunai_amount` > 0 is allowed (non-cash only).

### POST /api/port (PIN, in-memory only)

Body `{pin, port}` → 200 `{ok:true, port:N}`
| `400` port outside 1–65535. Restarts the listener in-process;
not persisted — a restart returns to the default/startup port.

### POST /api/pin (old PIN)

Body `{pin, new_pin}` → 200 `{ok:true}`
| `400` `new_pin` is not 6 digits | `403` | `429`.

### POST /api/shutdown (PIN)

Body `{pin}` → 200 `{ok:true}`, then the PC service stops
(the `cnd quit` / tray-Keluar equivalent). In-flight requests may be cut.

## `cnd` CLI (same EXE, terminal)

`cnd data` / `cnd log` read files directly — they work even when the
service is down. Everything else needs the local HTTP server.

| Command | Needs | Meaning |
|---|---|---|
| `cnd status` | server | Health + watcher + Ketoko + last receipt + today's count |
| `cnd data [--since N] [--limit N] [--today]` | file | Transactions table (`--limit` capped at 200) |
| `cnd log [--tail N]` | file | Last N log lines (capped at 1000, default 100) |
| `cnd port [N] --pin P` | server+PIN (to set) | Show port, or restart listener on N |
| `cnd watcher [on\|off] --pin P` | server (+PIN to set) | Show state, or pause/resume recording |
| `cnd wipe --pin P --confirm HAPUS` | server+PIN | Delete ALL transactions + logs, no backup |
| `cnd quit [--pin P]` (alias `shutdown`) | server+PIN | Clean shutdown |
| `cnd pin --pin OLD --new-pin NEW` | server+PIN | Change PIN (6 digits) |
| `cnd qr [--json]` | server | QR URL LAN (`http://IP:PORT`) di terminal, untuk scan HP |

Global flags (before or after the command): `--host` (default `127.0.0.1`),
`--port` (default `8765`, explicit `1`–`65535` or exit 2), `--db <path>`
(for `data`), `--json` (machine-readable output).
Exit codes: `0` ok · `1` failed (wrong PIN, offline server, DB error)
· `2` usage error (missing `--pin`, bad mode, bad `--port`).

Examples:

```bat
cnd status --json
cnd data --today --json
cnd log --tail 50
cnd qr
cnd port 8765 --pin 363636
cnd watcher off --pin 363636
cnd quit --pin 363636
```

## Headless mode

`CNdesktop.exe --headless [--port P]` (or `setup_cn.bat headless` for
logon auto-start without a tray icon). Single-instance lock, file logging,
and the watcher work exactly like tray mode; there is only no icon.
Operate it with `cnd ...`; stop it with `cnd quit --pin ...`.
Back to tray: run `setup_cn.bat` without arguments and restart the EXE.

## Error mapping (phone + CLI)

| Code | Meaning | Show |
|---|---|---|
| 400 | Bad request | The PC's `error` text as-is |
| 403 | Wrong PIN | "Wrong PIN" |
| 409 | PC busy | "PC busy, retry" |
| 429 | Locked | "Locked for 5 minutes" |
| timeout/offline | Unreachable | "PC unreachable, same WiFi?" |

(Phone UI strings above are English; the current CNmobile app uses
Indonesian equivalents — localization stays on the phone side.)
