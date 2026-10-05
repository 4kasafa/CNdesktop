# CNdesktop

Connector background PC kasir: tray-only (no taskbar/console), baca otomatis window
pembayaran Ketoko via UIA, simpan SQLite, layani 1 HP via HTTP LAN, print thermal USB.

- Sumber kebenaran: baca dulu `docs/PRD.md` (skema DB, kontrak API, milestone).
- Referensi READ-ONLY `../cash_note` (repo lama, DIKUNCI — copy saja, JANGAN edit):
  - `pos_reader.py` → copy utuh, tambah field dialog pembayaran (butuh Inspect.exe)
  - `gas_service.py:76-94` → rumus total_kurang/total_lebih untuk `/api/totals`
  - `tabs/calculate_tab.py:581-667` → builder struk ESC/POS (`build_escpos_receipt`)
  - `constants.py:25` → `GAS_URL_KASIR`
- Standar: stdlib dulu (`http.server`, `sqlite3`, `urllib`); dep baru hanya bila stdlib mentok.
  Dep terizin: `uiautomation`, `pywin32`, `pystray`, `pillow`, `qrcode`, `pyinstaller`.
