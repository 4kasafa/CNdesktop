"""Watcher dialog Pembayaran: WinEventHook idle + burst save. Read-only.

Idle 99%: SetWinEventHook (CREATE/SHOW/HIDE/DESTROY/INVOKED), ~0% CPU.
Aktif: baca UIA 250ms saat dialog terbuka; burst 100ms x 5 dtk pasca-INVOKED.
Tidak pernah klik/fokus/steal-foreground. Exception → log + silent.
"""
import ctypes
import logging
import threading
import time
from ctypes import wintypes

from src.classify import classify
from src.config import BURST_EVERY, BURST_MAX, ENUM_EVERY, READ_EVERY
from src.db import init_db, insert_tx
from src.parse import parse_nominal
from src.pos_reader import (
    KETOKO_PROCESS_NAME,
    KETOKO_WINDOW_TITLE,
    get_window_process_name,
    read_dialog,
    read_no_transaksi,
)

log = logging.getLogger("cndesktop")

EV_CREATE, EV_DESTROY, EV_SHOW, EV_HIDE, EV_INVOKED = 0x8000, 0x8001, 0x8002, 0x8003, 0x8013
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


class Watcher:
    """State machine per-hwnd + glue Win32. Reader/enum/clock injectable untuk test."""

    def __init__(self, db_path=None, read_dialog_fn=None, read_no_fn=None,
                 enum_fn=None, clock=None):
        self.db = init_db(db_path)
        self.read_dialog = read_dialog_fn or read_dialog
        self.read_no = read_no_fn or read_no_transaksi
        self.enum = enum_fn or _enum_ketoko
        self.clock = clock or time.monotonic
        self.sessions = {}  # hwnd -> {main, snap, phase, deadline, last_read}
        self._last_enum = 0.0
        self._run = False

    # ---- event murni (dipakai hook maupun test) ----
    def on_dialog_open(self, hwnd, main_hwnd):
        """Return True jika sesi baru dibuat (termasuk reset closed-watch basi)."""
        s = self.sessions.get(hwnd)
        if s is None or s.get("phase") == "closed-watch":
            self.sessions[hwnd] = {"main": main_hwnd, "snap": {}, "phase": "open",
                                    "deadline": 0.0, "last_read": 0.0, "last_no": ""}
            return True
        return False

    def on_dialog_close(self, hwnd):
        s = self.sessions.get(hwnd)
        if not s:
            return
        if s["phase"] == "burst":
            self.sessions.pop(hwnd, None)
            log.warning("needs_review: dialog hilang saat burst hwnd=%s", hwnd)
            return
        if s["phase"] == "closed-watch":
            return  # ponytail: tutup ganda = abaikan
        # fallback Simpan: dialog hilang tanpa INVOKED (hook mati?) tapi no
        # sudah angka -> anggap Simpan terjadi. Masih Auto -> watch pasca-tutup.
        try:
            fresh = self.read_dialog(hwnd)
            for k, v in fresh.items():
                if v:
                    s["snap"][k] = v
        except Exception:
            pass
        try:
            no = self.read_no(s["main"])
        except Exception:
            no = ""
        log.info("tutup hwnd=%s main=%s no=%r last_no=%r", hwnd, s["main"], no, s.get("last_no"))
        num = parse_nominal(no) if no and no != "Auto" else None
        if num is None and s.get("last_no"):
            num = s["last_no"]  # ponytail: no sudah ke-clear saat deteksi tutup
        if num is not None:
            log.info("simpan via tutup-dialog hwnd=%s no=%s", hwnd, num)
            self._save(hwnd, s, num)
            return
        s["phase"] = "closed-watch"  # T3: poll nomor 5 dtk pasca-tutup
        s["deadline"] = self.clock() + BURST_MAX

    def on_invoked(self, hwnd):
        s = self.sessions.get(hwnd)
        if not s or s["phase"] == "burst":
            return  # ponytail: unknown-hwnd / double-INVOKED = abaikan (UNIQUE jaga dobel)
        try:
            s["snap"] = self.read_dialog(hwnd)  # ponytail: seed lawan race Simpan <250ms
        except Exception as e:
            log.debug("seed snap gagal hwnd=%s: %r", hwnd, e)
        s["phase"] = "burst"
        s["deadline"] = self.clock() + BURST_MAX

    # ---- kerja periodik ----
    def _save(self, hwnd, s, num):
        """Klasifikasi + INSERT dari snap. Dipakai burst maupun tutup-dialog."""
        total = parse_nominal((s["snap"].get("total_raw") or ""))
        tunai = parse_nominal((s["snap"].get("tunai_raw") or ""))
        debit = parse_nominal((s["snap"].get("debit_raw") or ""))
        bank = (s["snap"].get("bank_raw") or "").strip()
        kat = classify(total, tunai, debit, bank)
        if kat == "needs_review" or not total:
            log.warning("needs_review: data tak lengkap hwnd=%s kat=%s", hwnd, kat)
        else:
            t, n = (total, 0) if kat == "Tunai" else (0, total) if kat == "Nontunai" else (tunai, debit)
            rowid = insert_tx(self.db, str(num), total, t, n, bank, kat)
            if rowid is None:
                log.info("duplikat no=%s (abaikan)", num)
            else:
                log.info("saved id=%s no=%s kat=%s", rowid, num, kat)
        self.sessions.pop(hwnd, None)

    def _finish_burst(self, hwnd, s):
        no = self.read_no(s["main"])
        num = parse_nominal(no) if no and no != "Auto" else None
        if num:
            self._save(hwnd, s, num)
            return True
        if self.clock() >= s["deadline"]:
            log.warning("needs_review: timeout 5 dtk hwnd=%s", hwnd)
            self.sessions.pop(hwnd, None)
            return True
        return False

    def tick(self):
        """Satu iterasi worker (100ms real). Tidak pernah raise."""
        try:
            now = self.clock()
            for hwnd, s in list(self.sessions.items()):
                if s["phase"] == "open":
                    if now - s["last_read"] >= READ_EVERY:
                        s["last_read"] = now
                        try:
                            s["snap"] = self.read_dialog(hwnd)
                        except Exception as e:
                            log.debug("read gagal hwnd=%s: %r", hwnd, e)
                        try:  # ponytail: ingat no numerik terakhir (tutupan fallback)
                            no = self.read_no(s["main"])
                            prev = s.get("prev_no")
                            if prev is None:
                                s["prev_no"] = no
                            elif no != prev:
                                log.info("no_transaksi main=%s %r -> %r", s["main"], prev, no)
                                s["prev_no"] = no
                            if no and no != "Auto" and parse_nominal(no):
                                s["last_no"] = parse_nominal(no)
                        except Exception:
                            pass
                elif s["phase"] == "closed-watch":
                    try:
                        no = self.read_no(s["main"])
                        num = parse_nominal(no) if no and no != "Auto" else None
                        if num:
                            log.info("simpan via tutup-dialog hwnd=%s no=%s", hwnd, num)
                            self._save(hwnd, s, num)
                        elif self.clock() >= s["deadline"]:
                            self.sessions.pop(hwnd, None)  # tak muncul -> discard
                    except Exception as e:
                        log.debug("closed-watch gagal hwnd=%s: %r", hwnd, e)
                        self.sessions.pop(hwnd, None)
                elif s["phase"] == "burst":
                    try:
                        self._finish_burst(hwnd, s)
                    except Exception as e:
                        log.debug("burst gagal hwnd=%s: %r", hwnd, e)
                        self.sessions.pop(hwnd, None)
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
            if event == EV_INVOKED:
                try:
                    if get_window_process_name(hwnd).lower() == KETOKO_PROCESS_NAME.lower():
                        log.info("invoked (hook) hwnd=%s obj=%s", hwnd, _obj)
                except Exception:
                    pass
                self.on_invoked(hwnd)
                return
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
            EV_CREATE, EV_INVOKED, 0, self._proc, 0, 0,
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
