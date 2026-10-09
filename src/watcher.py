"""Watcher dialog Pembayaran: WinEventHook idle + save via pending. Read-only.

Idle 99%: SetWinEventHook (CREATE/SHOW/HIDE/DESTROY), ~0% CPU.
Aktif: baca UIA 250ms saat dialog terbuka; tutup + total>0 -> pending, simpan
saat nomor transaksi muncul (poll global 500ms, tanpa batas waktu).
Tidak pernah klik/fokus/steal-foreground. Exception → log + silent.
"""
import ctypes
import logging
import threading
import time
from ctypes import wintypes

from src.classify import classify
from src.config import BURST_EVERY, ENUM_EVERY, READ_EVERY
from src.db import init_db, insert_tx
from src.parse import parse_no_transaksi, parse_nominal
from src.pos_reader import (
    KETOKO_PROCESS_NAME,
    KETOKO_WINDOW_TITLE,
    get_window_process_name,
    read_dialog,
    read_no_transaksi,
)

log = logging.getLogger("cndesktop")

EV_CREATE, EV_DESTROY, EV_SHOW, EV_HIDE = 0x8000, 0x8001, 0x8002, 0x8003
WINEVENT_OUTOFCONTEXT, WINEVENT_SKIPOWNPROCESS = 0, 2


def _title(hwnd: int) -> str:
    try:
        buf = ctypes.create_unicode_buffer(256)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
        return buf.value
    except Exception:
        return ""


def _enum_ketoko():
    """[(hwnd, title)] top-level visible milik KetokoD.exe. Stdlib saja."""
    out = []
    cb = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    @cb
    def _cb(hwnd, _):
        try:
            if ctypes.windll.user32.IsWindowVisible(hwnd) \
                    and get_window_process_name(hwnd).lower() == KETOKO_PROCESS_NAME.lower():
                out.append((hwnd, _title(hwnd)))
        except Exception:
            pass
        return True

    try:
        ctypes.windll.user32.EnumWindows(_cb, 0)
    except Exception:
        pass
    return out


def _merge_snap(snap: dict, fresh: dict) -> dict:
    """Merge hanya field non-empty (dialog sekarat baca kosong -> jangan timpa)."""
    for k, v in (fresh or {}).items():
        if v:
            snap[k] = v
    return snap


class Watcher:
    """State machine per-hwnd + glue Win32. Reader/enum/clock injectable untuk test."""

    def __init__(self, db_path=None, read_dialog_fn=None, read_no_fn=None,
                 enum_fn=None, clock=None):
        self.db = init_db(db_path)
        self.read_dialog = read_dialog_fn or read_dialog
        self.read_no = read_no_fn or read_no_transaksi
        self.enum = enum_fn or _enum_ketoko
        self.clock = clock or time.monotonic
        self.sessions = {}  # hwnd -> {main, snap, last_read} (hidup selama dialog terbuka)
        self.pending = None  # {"snap": dict, "main": hwnd, "t": float} slot tunggal
        self._last_seen = ""  # dokumen terakhir terlihat (transisi global)
        self._last_no_text = ""  # teks nomor mentah terakhir (log transisi)
        self._last_poll = 0.0
        self._main = 0
        self._last_enum = 0.0
        self._run = False

    # ---- event murni (dipakai hook maupun test) ----
    def on_dialog_open(self, hwnd, main_hwnd):
        """Return True jika sesi baru dibuat."""
        if hwnd not in self.sessions:
            self.sessions[hwnd] = {"main": main_hwnd, "snap": {}, "last_read": 0.0}
            return True
        return False

    def on_dialog_close(self, hwnd):
        s = self.sessions.get(hwnd)
        if not s:
            return
        # Tutup: total>0 -> slot pending (tunggu nomor, tanpa batas waktu);
        # total 0/kosong (= Batal murni) -> buang diam-diam.
        try:
            _merge_snap(s["snap"], self.read_dialog(hwnd))
        except Exception:
            pass
        self.sessions.pop(hwnd, None)
        total = parse_nominal(s["snap"].get("total_raw") or "")
        if not total:
            log.info("tutup hwnd=%s batal (total kosong)", hwnd)
            return
        self.pending = {"snap": dict(s["snap"]), "main": s["main"], "t": self.clock()}
        log.info("tutup hwnd=%s -> pending (total=%s)", hwnd, total)

    # ---- kerja periodik ----
    def _save(self, hwnd, s, doc_id, counter):
        """Klasifikasi + INSERT dari snap pending + nomor transisi."""
        total = parse_nominal((s["snap"].get("total_raw") or ""))
        tunai = parse_nominal((s["snap"].get("tunai_raw") or ""))
        debit = parse_nominal((s["snap"].get("debit_raw") or ""))
        bank = (s["snap"].get("bank_raw") or "").strip()
        kat = classify(total, tunai, debit, bank)
        if kat == "needs_review" or not total:
            log.warning("needs_review: data tak lengkap hwnd=%s kat=%s", hwnd, kat)
        else:
            t, n = (total, 0) if kat == "Tunai" else (0, total) if kat == "Nontunai" else (tunai, debit)
            rowid = insert_tx(self.db, doc_id, total, t, n, bank, kat, no_urut=counter)
            if rowid is None:
                log.info("duplikat no=%s (abaikan)", doc_id)
            else:
                log.info("saved id=%s no=%s urut=%s kat=%s", rowid, doc_id, counter, kat)
        self.sessions.pop(hwnd, None)

    def _poll_pending(self, now):
        """Poll global nomor 500ms; transisi + pending -> save sekali pakai."""
        if now - self._last_poll < 0.5:
            return
        self._last_poll = now
        main = self.pending["main"] if self.pending else self._main
        if not main:
            return
        try:
            no = self.read_no(main)
        except Exception:
            return
        if no != self._last_no_text:  # ponytail: peta timing nomor (satu-satunya log transisi)
            log.info("no_transaksi %r -> %r", self._last_no_text, no)
            self._last_no_text = no
        doc_id, counter = parse_no_transaksi(no)
        if not doc_id or doc_id == self._last_seen:
            return
        self._last_seen = doc_id
        if not self.pending:
            return  # hanya catat (Batal -> tak ada transisi -> tak ada save)
        snap = self.pending["snap"]
        age = now - self.pending["t"]
        self.pending = None  # konsumsi sekali pakai (sukses/gagal sama)
        log.info("simpan via transisi-nomor no=%s umur_pending=%.1fs", doc_id, age)
        try:
            self._save("pending", {"snap": snap}, doc_id, counter)
        except Exception as e:
            log.debug("save pending gagal: %r", e)

    def tick(self):
        """Satu iterasi worker (100ms real). Tidak pernah raise."""
        try:
            now = self.clock()
            for hwnd, s in list(self.sessions.items()):
                if now - s["last_read"] >= READ_EVERY:
                    s["last_read"] = now
                    try:
                        _merge_snap(s["snap"], self.read_dialog(hwnd))
                    except Exception as e:
                        log.debug("read gagal hwnd=%s: %r", hwnd, e)
            self._poll_pending(now)
            if now - self._last_enum >= ENUM_EVERY:
                self._last_enum = now
                self._reconcile()
        except Exception as e:
            log.debug("tick gagal: %r", e)

    def _reconcile(self):
        try:
            wins = self.enum()
        except Exception:
            return
        main = next((h for h, t in wins if KETOKO_WINDOW_TITLE.lower() in t.lower()), 0)
        self._main = main  # ponytail: cache untuk poll global tanpa sesi
        seen = set()
        for hwnd, title in wins:
            if title == "Pembayaran":
                seen.add(hwnd)
                if self.on_dialog_open(hwnd, main):
                    log.info("dialog terbuka (fallback enum) hwnd=%s", hwnd)
        for hwnd in list(self.sessions):
            if hwnd not in seen and not self._alive(hwnd):
                self.on_dialog_close(hwnd)

    @staticmethod
    def _alive(hwnd):
        try:
            return bool(ctypes.windll.user32.IsWindow(hwnd))
        except Exception:
            return True

    # ---- glue Win32 ----
    def _event(self, _hook, event, hwnd, _obj, _child, _tid, _time):
        try:
            proc_ok = get_window_process_name(hwnd).lower() == KETOKO_PROCESS_NAME.lower()
            if not proc_ok:
                return
            title = _title(hwnd)
            if event in (EV_CREATE, EV_SHOW) and title == "Pembayaran":
                main = next((h for h, t in self.enum()
                             if KETOKO_WINDOW_TITLE.lower() in t.lower()), 0)
                if self.on_dialog_open(hwnd, main):
                    log.info("dialog terbuka (hook) hwnd=%s", hwnd)
            elif event in (EV_DESTROY, EV_HIDE) and hwnd in self.sessions:
                log.info("dialog tutup (hook) hwnd=%s", hwnd)
                self.on_dialog_close(hwnd)
        except Exception as e:
            log.debug("hook event gagal: %r", e)

    def run(self):
        """Blokir: install hook + pump pesan + worker 100ms. Stop via stop()."""
        proto = ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND,
                                   wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD)
        self._proc = proto(self._event)  # ponytail: simpan ref agar tidak di-GC
        self._tid = ctypes.windll.kernel32.GetCurrentThreadId()
        hook = ctypes.windll.user32.SetWinEventHook(
            EV_CREATE, EV_HIDE, 0, self._proc, 0, 0,
            WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS)
        if not hook:
            log.error("SetWinEventHook gagal (NULL): hanya fallback enum 5 dtk aktif")
        self._run = True
        threading.Thread(target=self._worker, daemon=True).start()
        try:
            msg = wintypes.MSG()
            while self._run and ctypes.windll.user32.GetMessageW(ctypes.byref(msg), 0, 0, 0):
                ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
                ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            if hook:
                ctypes.windll.user32.UnhookWinEvent(hook)

    def _worker(self):
        while self._run:
            self.tick()
            time.sleep(BURST_EVERY)

    def stop(self):
        self._run = False
        try:
            ctypes.windll.user32.PostThreadMessageW(self._tid, 0x0012, 0, 0)  # WM_QUIT
        except Exception:
            pass
