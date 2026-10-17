# CNdesktop — Cashier PC Setup

Copy-paste guide for a **plain Windows 10/11 PC** (cashier). No git, no Python,
no package manager needed. Everything below runs in `cmd` with tools already
built into Windows (`curl.exe`, `tar.exe`, `netsh`).

CNdesktop is a background app: it reads the Ketoko payment window,
stores transactions in SQLite, and serves them to one phone over LAN WiFi
(`http://<PC-IP>:8765`). It runs in two modes — **headless** (default: no icon,
no window, driven from the terminal) and **tray** (green `CN` icon +
dashboard) — and ships a terminal CLI, **`cnd`**.

## What's new in v1.6.2

- **`cnd.exe` console companion** — same commands as the CLI, built as a
  console app so its output always shows on a `cmd` screen.
- **Global `cnd` shim** — `setup_cn.bat` installs `C:\Windows\cnd.bat`, so
  `cnd ...` works from any folder.
- **Headless mode** with logon auto-start (`setup_cn.bat headless`).
- New phone endpoints: `GET /api/status`, `GET /api/log`,
  `POST /api/port|pin|shutdown` — the PIN shares the 5-strikes/5-min
  lockout with wipe/watcher.

## Requirements

- Windows 10/11 x64 with internet access (once, for download).
- Admin approval **once** (Windows UAC prompt during setup).
- PC and phone on the **same WiFi**, network profile set to **Private**
  (Settings → Network → Private). Port `8765` is opened automatically.

## 1. Install

Open `cmd` (no admin needed to start) and paste this whole block:

```bat
set VER=1.6.2
curl -L -o %TEMP%\CNdesktop.zip "https://github.com/4kasafa/CNdesktop/releases/download/v%VER%/CNdesktop-v%VER%-portable.zip"
if not exist C:\CNdesktop mkdir C:\CNdesktop
tar -xf %TEMP%\CNdesktop.zip -C C:\CNdesktop
C:\CNdesktop\setup_cn.bat headless
start "" "C:\CNdesktop\CNdesktop.exe" --headless
timeout /t 5 /nobreak >nul
cnd status
```

What each step does:

1. `set VER=...` — pins the version so only one line changes per release.
2. `curl -L` — downloads the portable package (`CNdesktop.exe` + `cnd.exe` +
   `setup_cn.bat`). `-L` follows GitHub's redirect to the actual file.
3. `mkdir` — creates the install folder (`if not exist` keeps it re-runnable).
4. `tar -xf` — extracts the zip (built into Windows, no WinRAR needed).
5. `setup_cn.bat headless` — asks for admin once (UAC), then creates the
   Startup shortcut (auto-start on every login, here with `--headless`), the
   firewall rule for TCP port `8765`, and the **global `cnd` shim**:
   a one-line file `C:\Windows\cnd.bat` that forwards to
   `C:\CNdesktop\cnd.exe`, so `cnd ...` works from any folder. It does
   **not** start the app — that's the next line. `headless` and `--headless`
   are both accepted.
6. `start ""` — launches the app (the empty `""` is a required dummy window
   title so the quoted path isn't eaten as the title).
7. `cnd status` — the health check: version, watcher state, last receipt,
   today's count. `curl http://127.0.0.1:8765/api/health` returns
   `{"ok": true}` if you prefer `curl`.

Verify the `cnd` shim once (optional):

```bat
where cnd
```

Expected: `C:\Windows\cnd.bat`.

**Prefer the dashboard?** Use tray mode instead — same install, only two
lines change:

```bat
C:\CNdesktop\setup_cn.bat
start "" "C:\CNdesktop\CNdesktop.exe"
```

Mode notes:

- The mode is stored **in the Startup shortcut**. Updating never changes it;
  to switch modes, run the other `setup_cn.bat` variant once and restart.
- Tray mode shows a green `CN` icon (tooltip `CNdesktop v%VER% <PC-IP>:8765`);
  double-click opens the dashboard. Headless mode has no icon — `cnd status`
  is the only check.
- When Windows SmartScreen appears (unsigned app), click **More info → Run
  anyway**. This happens once; if it blocked the start, re-run the `start`
  line after allowing it.

## 2. Daily use (`cnd`)

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

Notes:

- Use `cnd` / `cnd.exe`, **not** `CNdesktop.exe cnd ...` — the app EXE is
  windowed, so its CLI output never reaches a `cmd` screen.
- `cnd data` / `cnd log` read files directly and work even when the service
  is down; everything else needs the local HTTP server.
- Flags: `--host` (default `127.0.0.1`), `--port` (default `8765`),
  `--db <path>`, `--json` (machine-readable, before or after the command).
- Exit codes: `0` ok, `1` failed (wrong PIN, offline server), `2` usage error.
- Default PIN is `363636`; change it with `cnd pin` after install.

Full endpoint contract: `docs/cnd-remote.md`.

## 3. Update

Same mechanism: overwrite the EXEs. **Quit the app first** — `cnd quit --pin
<PIN>`, or right-click the tray icon → **Keluar** — because a running EXE is
file-locked. Never update in the middle of a transaction (no `Pembayaran`
dialog open).

```bat
set VER=1.6.2
cnd quit --pin 363636
tasklist | findstr /i CNdesktop.exe
```

If the line above still lists `CNdesktop.exe`, quit properly and repeat until
it prints nothing. Then:

```bat
copy C:\CNdesktop\CNdesktop.exe C:\CNdesktop\CNdesktop.exe.bak
copy C:\CNdesktop\cnd.exe C:\CNdesktop\cnd.exe.bak
curl -L -o %TEMP%\CNdesktop.zip "https://github.com/4kasafa/CNdesktop/releases/download/v%VER%/CNdesktop-v%VER%-portable.zip"
tar -xf %TEMP%\CNdesktop.zip -C C:\CNdesktop
start "" "C:\CNdesktop\CNdesktop.exe" --headless
cnd status
```

Notes:

- **Both EXEs are backed up**, because the `cnd` shim points at `cnd.exe` —
  if it doesn't arrive, `cnd` breaks.
- Tray mode: use `start "" "C:\CNdesktop\CNdesktop.exe"` instead. The
  Startup shortcut already carries your mode; the `start` line only affects
  the current session.
- `setup_cn.bat` does **not** need re-running (shortcut + firewall + shim
  already point at the same paths). Re-run it only if you moved the folder
  (with `headless` if that was your mode), or if you upgrade from a build
  older than v1.6.2 — that one shipped no `cnd.exe` for the shim to call.
- The backups (`.bak`) and database (`%APPDATA%\CNdesktop\data.db`) are
  untouched, so transactions and logs survive the update.

Rollback (if the new version misbehaves) — quit first, then:

```bat
del C:\CNdesktop\CNdesktop.exe
ren C:\CNdesktop\CNdesktop.exe.bak CNdesktop.exe
start "" "C:\CNdesktop\CNdesktop.exe" --headless
```

## 4. Uninstall (full wipe)

Run `cmd` **as administrator**. Prefer quitting cleanly first
(`cnd quit --pin <PIN>`, or tray → **Keluar**);
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

1. `taskkill` — force-stops the app if a clean quit was skipped.
2. `del ... StartUp\CNdesktop.lnk` — removes auto-start on login.
3. `del C:\Windows\cnd.bat` — removes the global `cnd` shim.
4. `netsh ... delete rule` — removes the firewall exception for port `8765`.
5. `rmdir C:\CNdesktop` — removes the program files (`CNdesktop.exe`,
   `cnd.exe`, `setup_cn.bat`, plus any `.bak`).
6. `rmdir %APPDATA%\CNdesktop` — removes transactions (`data.db`), logs,
   and the lock file. **This deletes sales history** — back up `data.db`
   first if you need it.

## 5. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| SmartScreen blue warning | App is unsigned → `More info → Run anyway`, once |
| `curl` reports 404 | Wrong `VER` — check the version exists under GitHub → Releases |
| Tray icon missing after start | Old instance still running (`tasklist \| findstr CNdesktop`) — quit it, start again |
| Phone can't reach `http://<PC-IP>:8765` | WiFi must be **Private**, not Public; re-run `setup_cn.bat` to restore the firewall rule |
| `cnd` not recognized | Shim missing → run `setup_cn.bat` again (admin), then `where cnd` |
| `cnd` runs but prints nothing | Call `C:\CNdesktop\cnd.exe` directly, or the terminal is broken (`echo hello` must print) |
| `403 PIN salah` / `429 terkunci` | Default PIN `363636`; 5 wrong PINs = wait 5 minutes |
| `409 PC sibuk` | Printing or a DB write is in progress — retry in a few seconds |
| `cnd status` shows `?`/`None` everywhere | Old server without `/api/status` holds the port — quit it, start the current release |
| Something looks wrong | `cnd log --tail 50`, or read `%APPDATA%\CNdesktop\logs\cndesktop.log` |

## For maintainers

Each new release only changes `set VER=` in the blocks above plus the asset
name — no other logic. Publish with (from the dev PC):

```bat
gh release create vX.Y.Z dist\CNdesktop-vX.Y.Z-portable.zip --title "vX.Y.Z" --notes "-"
```
