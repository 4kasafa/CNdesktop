# Remote + CLI baru (v1.6.0): status/log/port/pin/shutdown

Kontrak milik PC (jangan diubah sisi HP). PIN default `363636`
(ganti via dashboard atau `POST /api/pin`). Lockout gabungan semua
aksi PIN: 5x salah beruntun → 429 terkunci 5 menit; PIN benar me-reset.

## GET /api/status (bebas PIN)

`GET {base}/api/status` → 200:

```json
{"version":"1.6.0","ip":"192.168.1.5","port":8765,
 "watcher_enabled":true,"watcher_alive":true,"db_busy":false,
 "ketoko":false,"last_no":"NOTRX-001","count_today":3,"uptime_s":12.5}
```

## GET /api/log (PIN, cap 1000)

`GET {base}/api/log?pin=363636&tail=200` → 200 `{"lines":[...],"tail":200}`
| 403 PIN salah | 429 terkunci | 400 tail di luar 1-1000.
PIN lewat query (jangan disimpan permanen di HP).

## POST /api/port (PIN)

Body `{pin, port}` → 200 `{ok:true, port:N}` | 400 port di luar 1-65535.
Restart listener in-memory (tidak persist; restart balik default).

## POST /api/pin (PIN lama)

Body `{pin, new_pin}` → 200 `{ok:true}` | 400 `new_pin` bukan 6 digit.

## POST /api/shutdown (PIN)

Body `{pin}` → 200 `{ok:true}` lalu PC berhenti (pengganti tray Keluar).

## Padanan `cnd` (1 exe, tanpa server untuk data/log)

```bat
CNdesktop.exe cnd status
CNdesktop.exe cnd data --today
CNdesktop.exe cnd log --tail 50
CNdesktop.exe cnd port 8765 --pin 363636
CNdesktop.exe cnd watcher off --pin 363636
CNdesktop.exe cnd quit --pin 363636
CNdesktop.exe cnd pin --pin 363636 --new-pin 654321
```

`data`/`log` baca file langsung (jalan walau service mati);
sisanya via HTTP localhost. `--json` untuk scripting.
