# PRD — Desktop Connector (repo BARU, mis. `CNdesktop`)

> Repo `cash_note` yang sekarang TIDAK diubah — tetap jadi referensi + sumber copy-paste.
> Repo baru ini: Python, tray-only, tanpa window utama.

## 1. Latar & tujuan

PC kasir butuh penghubung yang hidup di background: baca otomatis window pembayaran Ketoko (UIA), simpan ke SQLite, layani 1 HP via WiFi (live data + print), tanpa ganggu kasir (no taskbar, no console, autostart).

Non-tujuan: tidak ada UI kasir lengkap (itu tetap di repo lama), HP tidak edit transaksi, tidak ada Bluetooth print, tidak ada multi-device.

## 2. Keputusan kunci (locked)

- Auto-save langsung tiap nominal baru (tanpa konfirmasi HP).
- Printer thermal USB hanya di PC; HP cuma `POST /api/print`.
- 1 PC + 1 HP → pairing PIN→token sekali + QR (`http://IP:8765 + token`), tanpa mDNS.
- Server HTTP pakai **stdlib `http.server`** (tanpa Flask/FastAPI).
- UIA level: samakan elevated/non-elevated dengan KetokoD.exe (verifikasi di mesin toko).

## 3. Struktur file repo baru

```
CNdesktop/
  README.md                      # cara install, pairing HP, troubleshooting
  requirements.txt               # uiautomation, pywin32, pystray, pillow, pyinstaller (+ qrcode)
  installer.iss                  # Inno Setup: autostart, firewall port 8765, admin-manifest opsional
  cashnote.ico
  src/
    main.py                      # entrypoint: init db → watcher thread → api thread → tray mainloop
    config.py                    # DB_PATH, API_PORT=8765, PC_ID, GAS_URL (copy constants.py:25 repo lama)
    pos_reader.py                # COPY dari repo lama + tambah field dialog pembayaran (butuh Inspect.exe)
    watcher.py                   # polling EnumWindows 500ms → is_ketoko_window → read → debounce → insert
    db.py                        # connect (WAL), create schema, insert/query transactions + print_jobs
    migrate_json_to_sqlite.py    # one-shot: data_*.json repo lama → transactions (source='import')
    server.py                    # routes health/transactions/totals/print, cek token
    auth.py                      # buat PIN 6-digit sekali → tukar token, simpan token hash
    printer.py                   # worker antrean print_jobs → ESC/POS via win32print (COPY builder
                                 #   build_escpos_receipt/generate_receipt_text dari calculate_tab.py:581-667)
    tray.py                      # pystray: menu Buka QR-IP / Keluar; (QR: window mini atau PNG dibuka viewer)
  data/                          # RUNTIME, gitignored: cashnote.db, auth.json
  tests_smoke.py                 # assert-based: db insert+query, api health+print (tanpa framework)
```

Copy dari repo lama (referensi, jangan import lintas repo):
- `pos_reader.py` utuh (`read_ketoko_value`, `click_butbayar`, `is_ketoko_window`).
- `GAS_URL_KASIR` 1 baris (`constants.py:25`) — untuk jaga-jaga, HP yang utama pakai GAS.
- Rumus `total_kurang/total_lebih` (`gas_service.py:76-94`) untuk `/api/totals`.
- `format_rupiah` + builder struk ESC/POS (`tabs/kasir_tab.py:15-22`, `tabs/calculate_tab.py:581-667`).

## 4. Skema SQLite (`data/cashnote.db`, WAL)

```sql
transactions(id INTEGER PK, amount INTEGER NOT NULL, category TEXT NOT NULL DEFAULT 'Cash',
  label INTEGER, ts TEXT NOT NULL, source TEXT NOT NULL);  -- source: pos|manual|import
print_jobs(id INTEGER PK, payload_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued', ts TEXT NOT NULL); -- queued|done|failed + pesan di payload
auth(token_hash TEXT PRIMARY KEY, created TEXT NOT NULL);
```

Anti-duplikat watcher: cek `(amount, ts-menit, source='pos')` atau kolom `dedup_key` bila perlu.

## 5. Kontrak LAN API (port 8765, header `X-Token`)

| Method & path | Req | Res |
|---|---|---|
| `GET /api/health` | — | `{ok:true, pc_id, time}` |
| `GET /api/transactions?since_id=N` | — | `{data:[{id,amount,category,label,ts}], last_id}` |
| `GET /api/totals` | — | `{total_transaksi, total_kurang, total_lebih}` |
| `POST /api/print` | `{type:'receipt', transaction_ids:[...]}` atau `{type:'text', text}` | `{job_id}` |
| `GET /api/print/:id` | — | `{status}` (opsional, boleh skip — HP polling ulang) |
| `POST /api/pair` | `{pin}` | `{token}` (sekali saja) |

## 6. Alur runtime

1. Boot → tray muncul, watcher polling 500ms, API listen `0.0.0.0:8765`.
2. Dialog pembayaran Ketoko muncul + nominal berubah & >0 → insert `transactions(source='pos')`.
3. HP polling `since_id` tiap 2 detik → list live.
4. HP print → row `print_jobs queued` → worker cetak → `done/failed` (gagal tercatat, tampil di HP).
5. Pairing: kasir klik tray → tampil PIN 6 digit (sekali pakai, kedaluwarsa 5 mnt) + QR berisi IP+token → HP scan → simpan token.

## 7. Acceptance

- [ ] `setup.exe` → restart → hanya tray (no taskbar/console).
- [ ] Nominal pembayaran Ketoko masuk DB <1 dtk tanpa sentuh apa pun.
- [ ] `curl` dari HP: health + transactions + totals OK; print keluar struk fisik.
- [ ] Data lama (JSON repo lama) terbaca setelah migrasi.
- [ ] `tests_smoke.py` hijau.

## 8. Milestone

M1 ekstrak+copy modul (Fase 0) → M2 sqlite+migrasi → M3 watcher (butuh Inspect.exe dialog pembayaran) → M4 tray+installer → M5 LAN API+pairing → uji di mesin toko.
