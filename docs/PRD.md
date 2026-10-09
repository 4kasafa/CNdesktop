# PRD — CNdesktop (Connector Kasir Ketoko)

## 0. Referensi

* Sumber kebenaran: `D:\Desktop\projects\cash_note` — JANGAN edit sumber.
* Copy POS: `docs/pos.md` (konstanta, `pos_reader.py`, pola hotkey F10).
* Locator UIA: `docs/pos_inspect.md:16-28` (dipakai verbatim).
* App target: `KetokoD.exe` — `Ketoko.co.id Desktop v2.3.1.0`, WPF + DevExpress v16.2.
* Gap wajib inspect ulang sebelum watcher final: field `Total Bayar` (hijau), `Kembali` (oranye), `AutomationId` tombol `Simpan` polos, modal "simpan berhasil" + timing clear.

## 1. Tujuan & Kriteria

1. Berjalan di background, tanpa taskbar/console, hanya tray-icon.
2. Fungsi utama: membaca data pembayaran Ketoko dan menentukan metode (Tunai / Nontunai / Split).
3. Simpan sementara di SQLite sebelum diambil HP (WiFi/LAN sama, 1 HP).
4. Dashboard hanya dibuka via tray-icon, isi minimal.
5. Read-only UIA: tidak klik/fokus `ButBayar` otomatis, tidak mencuri foreground kasir.

Keputusan user (final): kategori hanya Tunai/Nontunai/Split; trigger sah = `Simpan` polos + `Simpan+Cetak`; HP polling; dashboard minimal; tidak auto-print thermal.

## 2. Arsitektur

```
KetokoD.exe (WPF)
  └─ Dialog "Pembayaran" (IsDialog=1, top-level, hwnd != main)
       └─ WinEventHook (ctypes, stdlib) → watcher.py → SQLite (data.db)
                                                        └─ http.server LAN → HP (polling)
                                                        └─ tray-icon → dashboard lokal
```

* Idle 99%: `SetWinEventHook` — `EVENT_OBJECT_CREATE/SHOW` filter `Name="Pembayaran"` + PID `KetokoD.exe` = mulai; `HIDE/DESTROY` = tutup (total>0 → pending, total kosong → discard). Tanpa trigger INVOKED — nomor Ketoko adalah validator tunggal (muncul ⟺ transaksi sukses tersimpan). Idle ~0% CPU, ~30-50MB RAM.
* Dilarang polling idle 500ms. Pengaman saja: `EnumWindows` tiap 5 detik jika hook miss (WPF obfuscated).
* Aktif singkat (dialog terbuka saja): baca UIA tiap 250ms — Total kuning, `tBayarTunai`, field Debit, ComboBank.
* Save via pending: tutup + total>0 → slot pending; poll global `tNoTransaksi` tiap 500ms sampai transisi ke angka (tanpa batas waktu), lalu save sekali pakai dan kembali idle.
* Stack: Python stdlib (`ctypes`, `sqlite3`, `http.server`) + `uiautomation` (reuse `pos_reader.py` dari `docs/pos.md`) + satu dep tray (`pystray`). Autostart via Startup folder.

## 3. Locator UIA (dari `pos_inspect.md`)

| Elemen | Locator | Pola baca |
|---|---|---|
| Window utama | `AutomationId="MainWindow"` / judul `Ketoko.co.id Desktop` | anchor |
| No Transaksi | parent `aid="tNoTransaksi"` (bukan inner `PART_Editor`) | `ValuePattern`: `Auto` → angka |
| Total dialog (kuning) | `ClassName="l11illlII111I"` tanpa aid, Edit pertama/terbesar di dialog | `ValuePattern` |
| Bayar Tunai | `AutomationId="tBayarTunai"` | `ValuePattern` |
| Kartu Debit (nominal) | tanpa aid, Edit di `Top:565` sejajar combo Bank | `ValuePattern`, fallback posisi |
| Combo Bank Debit | `ClassName="ComboBoxEdit"` di `(1014,565,1139,607)` | `ValuePattern` (opsional) |
| Simpan + Cetak | `AutomationId="ButSimpanCetak"` | `Invoke` — deteksi saja |
| Simpan polos | aid menyusul (gap inspect) | `Invoke` — deteksi saja |
| Grid item `GrdCtrl` | 0 anak, tidak terekspos | DITUTUP: item tidak diambil via UIA |

Parsing nominal: `Rp 150.000,00 → 150000` (strip `,\d{1,2}$`, ambil digit, tolak string berisi `/` atau `:` (tanggal/jam), tolak `0`). Match exact, toleransi 0.

## 4. Alur sistem

1. Dialog `Pembayaran` muncul → snapshot Total final (bukan total berjalan kasir; total kasir `ClassName=l11illlII111I` di main hanya untuk konteks).
2. Baca `ComboBank.Value`: kosong dan field Debit `0`/kosong → kandidat Tunai. Ada isi → baca nominal Debit.
3. `debit == total` → Nontunai. `debit < total` → baca `tBayarTunai`; jika `debit + tunai == total` → Split.
4. Tunai murni: simpan Total saja, abaikan input tunai (kembalian tidak disimpan).
5. Dialog tutup + total>0 → slot pending (snapshot + window utama). Total kosong (= Batal) → discard diam-diam.
6. Poll global No Transaksi tiap 500ms; transisi ke angka + ada pending → klasifikasi + `INSERT` sekali pakai. Nomor tak muncul = tak ada save (Batal). Data tak lengkap → log `needs_review`, tanpa save separuh.
7. HP polling periodik dan mengambil transaksi baru (repo HP terpisah).

Pseudocode klasifikasi:

```
total = parse(total_raw)
debit = parse(debit_raw) if bank else 0
if not bank and debit == 0: kategori = "Tunai"
elif debit == total: kategori = "Nontunai"
elif debit + parse(tunai_raw) == total: kategori = "Split"
else: needs_review (jangan save)
```

## 5. SQLite

File: `%APPDATA%/CNdesktop/data.db`. Tanpa hapus otomatis (retensi tunda).

```sql
CREATE TABLE IF NOT EXISTS transactions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  no_transaksi TEXT UNIQUE NOT NULL,
  total INTEGER NOT NULL,
  tunai INTEGER NOT NULL DEFAULT 0,
  nontunai INTEGER NOT NULL DEFAULT 0,
  bank TEXT DEFAULT '',
  kategori TEXT NOT NULL CHECK(kategori IN ('Tunai','Nontunai','Split')),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

Idempoten via `UNIQUE(no_transaksi)` — transisi nomor yang sama tidak dobel (`_last_seen` + slot sekali pakai). Multi-dialog: satu transaksi per `hwnd`.

## 6. API LAN (HP polling, tanpa auth)

Alasan: 1 HP, LAN sama, malas dulu. Risiko dicatat: siapa pun di LAN bisa baca nominal — tambah token jika toko komplain.

* Bind `0.0.0.0:8765`, IP:port tampil di tooltip tray.
* `GET /api/health → {"ok":true}`
* `GET /api/transactions?since=<id>&limit=50 → [{id,no_transaksi,total,tunai,nontunai,bank,kategori,created_at}] ORDER BY id ASC`

## 7. Dashboard (tray-only, minimal)

Dibuka via double-click / right-click tray. Isi: status watcher (jalan/mati), Ketoko terdeteksi/tidak, No Transaksi terakhir, tabel 20 transaksi terakhir, setting port, tombol `Test Baca UIA`. Ditutup = hide, bukan exit. Exit hanya via menu `Keluar`. Tanpa laporan/reprint/hapus-edit.

## 8. Print thermal USB

Out of scope. Tidak ada auto-print. Data hanya disiapkan di SQLite + API untuk HP/dashboard reprint nanti.

## 9. Edge & Non-fungsional

* Windows 10/11 x64, Ketoko `v2.3.1.0`. Gagal baca UIA = silent + log, jangan crash/block kasir (pola `pos_reader.py`: tidak pernah raise dari thread background).
* Batal (tutup + total kosong) = discard diam-diam; tutup + total>0 = pending sampai nomor muncul. Multi-dialog = antre per `hwnd` dengan kunci sederhana.
* Beban: idle ~0% CPU; baca UIA hanya saat dialog terbuka (250ms) + poll nomor global tiap 500ms.
* Deposit/Kredit/E-Money di luar scope (kasir hanya pakai Tunai + Debit).

## 10. Acceptance

PRD lengkap jika §2–§7 terimplementasi: hook idle + save-via-pending (poll 500ms tanpa batas waktu), klasifikasi §4, skema §5, 2 endpoint §6, dashboard §7. Verifikasi: 1× transaksi Tunai + 1× Nontunai + 1× Split terbaca benar + `since` HP tidak duplikat + idle CPU ~0%.
