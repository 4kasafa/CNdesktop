# E2E Checklist — Acceptance PRD §10 (mesin toko asli)

Gate rilis. Yang `[x]` sudah terverifikasi CONFIG/CODE-level.
Yang `[ ]` wajib transaksi live di mesin toko.

## Sudah hijau (tidak perlu diulang)

- [x] `python -m pytest -v` 27 passed (parse, classify, db, api, watcher)
- [x] §2 hook idle + burst 100ms x 5 dtk (unit: save/timeout/close/multi-hwnd/double-invoked)
- [x] §3 locator UIA terverifikasi live (debit = field sebaris combo bank, `dump_debit.json`)
- [x] §4 klasifikasi Tunai/Nontunai/Split + `needs_review` (unit + live Nontunai 28600/BCA)
- [x] §5 skema + `UNIQUE(no_transaksi)` anti-duplikat (unit)
- [x] §6 `GET /api/health` + `GET /api/transactions?since&limit` (unit + live)
- [x] §7 dashboard tray-only (smoke: refresh/port/test-baca/hide-bukan-exit)
- [x] Idle CPU ~0% (sampel 3 mnt EXE), RAM private 46MB
- [x] Tidak auto-print (tidak ada code path print di repo)
- [x] Tidak klik/fokus kasir (watcher + reader read-only; INVOKED hanya dideteksi)
- [x] Grid `GrdCtrl` tidak diambil (scope ditutup, tidak ada kode grid)

## Wajib live di mesin toko (kasir transaksi sungguhan)

Cara cek tiap transaksi: bandingkan struk Ketoko vs baris baru di dashboard
(tabel 20 terakhir) atau `GET /api/transactions?since=<id-terakhir>`.

- [ ] 1x **Tunai**: bayar tunai penuh -> kategori `Tunai`, `total` = struk,
      `tunai` = total, `nontunai` = 0, `no_transaksi` angka (bukan `Auto`)
- [ ] 1x **Nontunai**: bayar debit penuh + pilih bank -> kategori `Nontunai`,
      `total` = `nontunai` = struk, `tunai` = 0, `bank` terisi, no angka
- [ ] 1x **Split**: tunai + debit pas total -> kategori `Split`,
      `tunai + nontunai` = `total` = struk, `bank` terisi, no angka
- [ ] HP polling `since`: ambil `since=<id>` dua kali -> respons kedua kosong
      (tidak duplikat); `since` naik mengikuti `id` terakhir

## Lulus jika

Semua kotak di atas `[x]`, tanpa transaksi `needs_review` yang tidak
terjelaskan di `%APPDATA%/CNdesktop/logs/cndesktop.log`.
