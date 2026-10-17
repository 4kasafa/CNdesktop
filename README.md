# CNdesktop — Cashier PC Setup

Copy-paste guide for a **plain Windows 10/11 PC** (cashier). No git, no Python,
no package manager needed. Everything below runs in `cmd` with tools already
built into Windows (`curl.exe`, `tar.exe`, `netsh`).

CNdesktop is a background app: it reads the Ketoko payment window,
stores transactions in SQLite, and serves them to one phone over LAN WiFi
(`http://<PC-IP>:8765`). Two modes: **tray** (icon + dashboard, default)
and **headless** (no icon, no window) — same EXE, plus a **`cnd`** terminal CLI.

## What's new in v1.6.2

- **`cnd.exe` console companion**: `CNdesktop.exe` is windowed, so its CLI
  output never reaches a `cmd` screen — `cnd.exe` (same commands) always does.
  The portable zip and `setup_cn.bat` now ship it; the global shim points there.

## What's new in v1.6.1

- Global `cnd` shim: `setup_cn.bat` installs `C:\Windows\cnd.bat`, so `cnd ...`
  works from any `cmd` folder (plus `headless` arg now survives the admin UAC hop).
- Full English README + complete `docs/cnd-remote.md` reference.

## What's new in v1.6.0

- **Headless mode** (`CNdesktop.exe --headless`, auto-start via
  `setup_cn.bat headless`) + **`cnd` CLI** in the same EXE:
  `cnd status/data/log/port/watcher/wipe/quit/pin` (details: `docs/cnd-remote.md`).
- New phone endpoints: `GET /api/status`, `GET /api/log`,
  `POST /api/port|pin|shutdown` — PIN shares the 5-strikes/5-min lockout
  with wipe/watcher.

## What's new in v1.5.0

- **Nontunai** field in the dashboard — included in Total Sales
  (cash + non-cash + expenses) and printed on the receipt.
- **Watcher On/Off** button in the dashboard (admin) + `GET/POST /api/watcher` —
  every toggle requires the 6-digit PIN (default `363636`, change via **Simpan PIN**.
- `POST /api/wipe {pin, confirm:"HAPUS"}` — deletes all transactions + logs
  (5 wrong PINs = 5-minute lockout; `409` while the PC is printing/writing the DB).

## Requirements

- Windows 10/11 x64 with internet access (once, for download).
- Admin approval **once** (Windows UAC prompt during setup).
- PC and phone on the **same WiFi**, network profile set to **Private**
  (Settings → Network → Private). Port `8765` is opened automatically.

## 1. Install

Open `cmd` (no admin needed to start) and paste the shared first half of
either block below:

```bat
set VER=1.6.2
curl -L -o %TEMP%\CNdesktop.zip "https://github.com/4kasafa/CNdesktop/releases/download/v%VER%/CNdesktop-v%VER%-portable.zip"
if not exist C:\CNdesktop mkdir C:\CNdesktop
tar -xf %TEMP%\CNdesktop.zip -C C:\CNdesktop
```

Then pick **one** mode:

**Tray mode (default)** — green `CN` icon + dashboard:

```bat
C:\CNdesktop\setup_cn.bat
start "" "C:\CNdesktop\CNdesktop.exe"
```

**Headless mode** — no icon, no window; operate with `cnd`:

```bat
C:\CNdesktop\setup_cn.bat headless
start "" "C:\CNdesktop\CNdesktop.exe" --headless
```

Then wait ~5 seconds and verify:

```bat
timeout /t 5 /nobreak >nul
cnd status
```

What each step does:

1. `set VER=...` — pins the version so only one line changes per release.
2. `curl -L` — downloads the portable package (`CNdesktop.exe` + `cnd.exe` +
   `setup_cn.bat`). `-L` follows GitHub's redirect to the actual file.
3. `mkdir` — creates the install folder (`if not exist` keeps it re-runnable).
4. `tar -xf` — extracts the zip (built into Windows, no WinRAR needed).
5. `setup_cn.bat [headless]` — asks for admin once, then creates the Startup
   shortcut (auto-start on every login, with or without `--headless` as chosen),
   the firewall rule for TCP port `8765`, and the global `cnd` shim so
   `cnd ...` works from any folder. It does **not** start the app — that's
   the `start` line. Both `headless` and `--headless` are accepted.
6. `start ""` — launches the app (the empty `""` is a required dummy window
   title so the quoted path isn't eaten as the title).
7. `cnd status` — the health check: prints the version, watcher state,
   last receipt and today's count. `curl http://127.0.0.1:8765/api/health`
   returns `{"ok": true}` if you prefer `curl`.

Mode notes:

- The mode is stored **in the Startup shortcut**. Updating never changes it;
  to switch modes, run the other `setup_cn.bat` variant once.
- In tray mode the green `CN` icon appears (tooltip
  `CNdesktop v%VER% <PC-IP>:8765`); double-click opens the dashboard.
  In headless mode there is no icon — `cnd status` is the only check.
- Use `cnd.exe` (or the `cnd` shim), not `CNdesktop.exe cnd ...`: the app
  EXE is windowed, so its CLI output never shows on a `cmd` screen.

When Windows SmartScreen appears (unsigned app), click **More info → Run
anyway**. This happens once; if it blocked the start, re-run the `start`
line after allowing it.

## 2. Update

Same mechanism: overwrite the EXEs. **Quit the app first** — right-click the
tray icon → **Keluar**, or `cnd quit --pin <PIN>` — because a running EXE is
file-locked. Never update in the middle of a transaction
(no `Pembayaran` dialog open).

```bat
set VER=1.6.2
tasklist | findstr /i CNdesktop.exe
```

If the line above still lists `CNdesktop.exe`, quit (tray or `cnd quit`)
and repeat until it prints nothing. Then:

```bat
copy C:\CNdesktop\CNdesktop.exe C:\CNdesktop\CNdesktop.exe.bak
curl -L -o %TEMP%\CNdesktop.zip "https://github.com/4kasafa/CNdesktop/releases/download/v%VER%/CNdesktop-v%VER%-portable.zip"
tar -xf %TEMP%\CNdesktop.zip -C C:\CNdesktop
start "" "C:\CNdesktop\CNdesktop.exe"
cnd status
```

Notes:

- **Keep your mode.** The Startup shortcut decides the mode; the `start`
  line above is tray mode. In headless mode use
  `start "" "C:\CNdesktop\CNdesktop.exe" --headless` instead — the shortcut
  already has the flag, so this only matters for the current session.
- `setup_cn.bat` does **not** need re-running (shortcut + firewall + shim
  already point at the same paths). Re-run it only if you moved the folder
  (re-run with `headless` if that was your mode) or upgraded from a build
  older than v1.6.2 (that one ships `cnd.exe`, which the shim points to).
- The backup (`.bak`) and database (`%APPDATA%\CNdesktop\data.db`) are untouched,
  so transactions and logs survive the update.
- Verify: `cnd status` shows the new version (tray tooltip in tray mode).

Rollback (if the new version misbehaves) — quit first (tray or `cnd quit`), then:

```bat
del C:\CNdesktop\CNdesktop.exe
ren C:\CNdesktop\CNdesktop.exe.bak CNdesktop.exe
start "" "C:\CNdesktop\CNdesktop.exe"
```

## 3. Uninstall (full wipe)

Run `cmd` **as administrator**. Prefer quitting cleanly first
(tray → **Keluar**, or `cnd quit --pin <PIN>`);
`taskkill` below is the fallback.

```bat
taskkill /F /IM CNdesktop.exe
del "C:\ProgramData\Microsoft\Windows\Start Menu\Programs\StartUp\CNdesktop.lnk"
del C:\Windows\cnd.bat
netsh advfirewall firewall delete rule name="CNdesktop"
rmdir /S /Q C:\CNdesktop
rmdir /S /Q %APPDATA%\CNdesktop
```

What each line does:

1. `taskkill` — force-stops the app if tray-quit was skipped.
2. `del ... StartUp\CNdesktop.lnk` — removes auto-start on login.
3. `del C:\Windows\cnd.bat` — removes the global `cnd` shim.
4. `netsh ... delete rule` — removes the firewall exception for port `8765`.
5. `rmdir C:\CNdesktop` — removes the program files (`CNdesktop.exe`,
   `cnd.exe`, `setup_cn.bat`, plus any `.bak`).
6. `rmdir %APPDATA%\CNdesktop` — removes transactions (`data.db`), logs,
   and the lock file. **This deletes sales history** — back up `data.db`
   first if you need it.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| SmartScreen blue warning | App is unsigned → `More info → Run anyway`, once |
| `curl` reports 404 | Wrong `VER` — check the version exists under GitHub → Releases |
| Tray icon missing after start | Old instance still running (`tasklist \| findstr CNdesktop`) — quit it, start again |
| Phone can't reach `http://<PC-IP>:8765` | WiFi must be **Private**, not Public; re-run `setup_cn.bat` to restore the firewall rule |
| `403 PIN salah` / `429 terkunci` | Default PIN `363636` — see dashboard admin; 5 wrong PINs = wait 5 minutes |
| `409 PC sibuk` | Printing or a DB write is in progress — retry in a few seconds |
| Something looks wrong | `cnd log --tail 50`, or read `%APPDATA%\CNdesktop\logs\cndesktop.log` |
| `cnd status` shows `?`/`None` everywhere | Old server without `/api/status` is holding the port — quit it, start v1.6.0 |

## Headless + CLI `cnd` (no tray icon)

Run `CNdesktop.exe --headless` (auto-start: `setup_cn.bat headless`).
After setup, `cnd ...` works from any `cmd` folder (global shim).
`cnd data` / `cnd log` read files directly and work even when the service
is down; everything else talks to the local HTTP server.

```bat
cnd status                          # health + watcher + last receipt + today's count
cnd data --today                    # today's transactions (add --since N, --limit N)
cnd log --tail 50                   # last 50 log lines
cnd port                            # show port; `cnd port 8765 --pin 363636` to change
cnd watcher                         # show state; `cnd watcher off --pin 363636` to pause
cnd wipe --pin 363636 --confirm HAPUS   # delete ALL transactions + logs (no backup!)
cnd quit --pin 363636               # clean shutdown (replaces tray Keluar)
cnd pin --pin 363636 --new-pin 654321  # change PIN (6 digits)
```

Flags: `--host` (default `127.0.0.1`), `--port` (default `8765`),
`--db <path>`, `--json` (machine-readable output, before or after the command).
Exit codes: `0` ok, `1` failed (e.g. wrong PIN, offline server), `2` usage error.

New phone endpoints: `GET /api/status`, `GET /api/log?pin=&tail=`,
`POST /api/port {pin,port}`, `POST /api/pin {pin,new_pin}`,
`POST /api/shutdown {pin}` — PIN shares the 5-strikes/5-min lockout
with wipe/watcher. Full contract: `docs/cnd-remote.md`.

Rollback headless → tray: run `setup_cn.bat` without arguments
(the Startup shortcut loses `--headless`), then
`cnd quit --pin ...` and start the EXE again.

## For maintainers

Each new release only changes `set VER=` in the blocks above plus the asset
name — no other logic. Publish with (from the dev PC):

```bat
gh release create vX.Y.Z dist\CNdesktop-vX.Y.Z-portable.zip --title "vX.Y.Z" --notes "-"
```
