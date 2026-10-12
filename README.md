# CNdesktop — Cashier PC Setup

Copy-paste guide for a **plain Windows 10/11 PC** (cashier). No git, no Python,
no package manager needed. Everything below runs in `cmd` with tools already
built into Windows (`curl.exe`, `tar.exe`, `netsh`).

CNdesktop is a tray-only background app: it reads the Ketoko payment window,
stores transactions in SQLite, and serves them to one phone over LAN WiFi
(`http://<PC-IP>:8765`).

## Requirements

- Windows 10/11 x64 with internet access (once, for download).
- Admin approval **once** (Windows UAC prompt during setup).
- PC and phone on the **same WiFi**, network profile set to **Private**
  (Settings → Network → Private). Port `8765` is opened automatically.

## 1. Install

Open `cmd` (no admin needed to start) and paste this whole block:

```bat
set VER=1.4.0
curl -L -o %TEMP%\CNdesktop.zip "https://github.com/4kasafa/CNdesktop/releases/download/v%VER%/CNdesktop-v%VER%-portable.zip"
if not exist C:\CNdesktop mkdir C:\CNdesktop
tar -xf %TEMP%\CNdesktop.zip -C C:\CNdesktop
C:\CNdesktop\setup_cn.bat
start "" "C:\CNdesktop\CNdesktop.exe"
timeout /t 5 /nobreak >nul
```

What each line does:

1. `set VER=...` — pins the version so only one line changes per release.
2. `curl -L` — downloads the portable package (`CNdesktop.exe` + `setup_cn.bat`).
   `-L` follows GitHub's redirect to the actual file.
3. `mkdir` — creates the install folder (`if not exist` keeps it re-runnable).
4. `tar -xf` — extracts the zip (built into Windows, no WinRAR needed).
5. `setup_cn.bat` — asks for admin once, then creates the Startup shortcut
   (auto-start on every login) and the firewall rule for TCP port `8765`.
   It does **not** start the app — that's the next line.
6. `start ""` — launches the app (the empty `""` is a required dummy window
   title so the quoted path isn't eaten as the title).
7. `timeout /t 5` — waits for the app to finish starting (watcher + tray +
   HTTP server) before the health check below. If the check fails, wait a few
   more seconds and run it again.

When Windows SmartScreen appears (unsigned app, can pop up at step 5 or 6),
click **More info → Run anyway**. This happens once; if it blocked the start,
re-run the `start` line after allowing it.

Verify the install:

```bat
curl http://127.0.0.1:8765/api/health
```

Expected: `{"ok": true}`. A green `CN` tray icon must appear with tooltip
`CNdesktop v%VER% <PC-IP>:8765`. Double-click it to open the dashboard.

## 2. Update

Same mechanism: overwrite the EXE. **Quit the app first** — right-click the
tray icon → **Keluar** — because a running EXE is file-locked. Never update
in the middle of a transaction (no `Pembayaran` dialog open).

```bat
set VER=1.4.0
tasklist | findstr /i CNdesktop.exe
```

If the line above still lists `CNdesktop.exe`, quit via tray and repeat until
it prints nothing. Then:

```bat
copy C:\CNdesktop\CNdesktop.exe C:\CNdesktop\CNdesktop.exe.bak
curl -L -o %TEMP%\CNdesktop.zip "https://github.com/4kasafa/CNdesktop/releases/download/v%VER%/CNdesktop-v%VER%-portable.zip"
tar -xf %TEMP%\CNdesktop.zip -C C:\CNdesktop
start "" "C:\CNdesktop\CNdesktop.exe"
curl http://127.0.0.1:8765/api/health
```

Notes:

- `setup_cn.bat` does **not** need re-running (shortcut + firewall already
  point at the same path). Re-run it only if you moved the folder.
- The backup (`.bak`) and database (`%APPDATA%\CNdesktop\data.db`) are untouched,
  so transactions and logs survive the update.
- Verify: health returns `{"ok": true}` and the tray tooltip shows the new version.

Rollback (if the new version misbehaves) — quit via tray first, then:

```bat
del C:\CNdesktop\CNdesktop.exe
ren C:\CNdesktop\CNdesktop.exe.bak CNdesktop.exe
start "" "C:\CNdesktop\CNdesktop.exe"
```

## 3. Uninstall (full wipe)

Run `cmd` **as administrator**. Prefer quitting via tray → **Keluar**
(clean shutdown flushes the database); `taskkill` below is the fallback.

```bat
taskkill /F /IM CNdesktop.exe
del "C:\ProgramData\Microsoft\Windows\Start Menu\Programs\StartUp\CNdesktop.lnk"
netsh advfirewall firewall delete rule name="CNdesktop"
rmdir /S /Q C:\CNdesktop
rmdir /S /Q %APPDATA%\CNdesktop
```

What each line does:

1. `taskkill` — force-stops the app if tray-quit was skipped.
2. `del ... StartUp\CNdesktop.lnk` — removes auto-start on login.
3. `netsh ... delete rule` — removes the firewall exception for port `8765`.
4. `rmdir C:\CNdesktop` — removes the program files.
5. `rmdir %APPDATA%\CNdesktop` — removes transactions (`data.db`), logs,
   and the lock file. **This deletes sales history** — back up `data.db`
   first if you need it.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| SmartScreen blue warning | App is unsigned → `More info → Run anyway`, once |
| `curl` reports 404 | Wrong `VER` — check the version exists under GitHub → Releases |
| Tray icon missing after start | Old instance still running (`tasklist \| findstr CNdesktop`) — quit it, start again |
| Phone can't reach `http://<PC-IP>:8765` | WiFi must be **Private**, not Public; re-run `setup_cn.bat` to restore the firewall rule |
| Something looks wrong | Open dashboard (double-click tray) → `Buka Log`, or read `%APPDATA%\CNdesktop\logs\cndesktop.log` |

## For maintainers

Each new release only changes `set VER=` in the blocks above plus the asset
name — no other logic. Publish with (from the dev PC):

```bat
gh release create vX.Y.Z dist\CNdesktop-vX.Y.Z-portable.zip --title "vX.Y.Z" --notes "-"
```
