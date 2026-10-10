"""Baca UIA Ketoko read-only. Copy `pos_reader.py` docs/pos.md + locator Fase 0.

Tidak pernah raise dari thread background; gagal baca = "".
Tanpa klik/fokus — watcher hanya membaca.
"""
import ctypes
import os

import uiautomation as auto

from src.config import KETOKO_PROCESS_NAME, KETOKO_WINDOW_TITLE  # re-ekspor utk watcher/dashboard

# POS Automation (constants.py:52-56 docs/pos.md)

# ClassName obfuscated dari field total Ketoko, fallback ke scan Edit ControlType
KETOKO_EDIT_CLASS = "l11illlII111I"

# ponytail: cache handle UIA per-hwnd; scan subtree mahal sekali, baca ulang murah.
# Dibuang saat dialog tutup / handle basi (Exists gagal) / main berganti.
_EL_TOTAL, _EL_TUNAI, _EL_NO = {}, {}, {}


def drop_dialog_cache(hwnd: int) -> None:
    """Buang cache dialog agar tak bocor/basi. Aman untuk hwnd tak dikenal."""
    for d in (_EL_TOTAL, _EL_TUNAI):
        d.pop(hwnd, None)


def drop_no_cache(main: int) -> None:
    """Buang cache nomor main window (Ketoko restart)."""
    _EL_NO.pop(main, None)


def get_window_process_name(hwnd: int) -> str:
    """Nama file process pemilik hwnd (e.g. 'KetokoD.exe'), '' jika gagal."""
    try:
        pid = ctypes.wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return ""
        # ponytail: QueryFullProcessImageName cukup, tanpa psutil/tambahan dependency
        hproc = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid.value)
        if not hproc:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(260)
            size = ctypes.wintypes.DWORD(260)
            if ctypes.windll.kernel32.QueryFullProcessImageNameW(hproc, 0, buf, ctypes.byref(size)):
                return os.path.basename(buf.value)
        finally:
            ctypes.windll.kernel32.CloseHandle(hproc)
    except Exception:
        pass
    return ""


def is_ketoko_window(hwnd: int, title: str = "") -> tuple:
    """(is_ketoko, proc_name): True jika title match ATAU process KetokoD.exe.

    Menangani dialog terpisah (e.g. title='Pembayaran') milik process yang sama.
    """
    proc = get_window_process_name(hwnd)
    if title and KETOKO_WINDOW_TITLE.lower() in title.lower():
        return True, proc
    if proc.lower() == KETOKO_PROCESS_NAME.lower():
        return True, proc
    return False, proc


def _read_edit_sources(edit) -> dict:
    """Ambil semua sumber teks yang mungkin dari sebuah Edit control."""
    sources = {}
    try:
        sources["value"] = edit.GetValuePattern().Value or ""
    except Exception as e:
        sources["value_err"] = repr(e)
    try:
        sources["name"] = edit.Name or ""
    except Exception as e:
        sources["name_err"] = repr(e)
    try:
        sources["legacy"] = (edit.GetLegacyIAccessiblePattern().Value or "")[:200]
    except Exception as e:
        sources["legacy_err"] = repr(e)
    return sources


def _iter_edits(control, depth: int = 0, max_depth: int = 10):
    """Yield semua EditControl secara rekursif (GetDescendants tidak ada di lib ini)."""
    if depth > max_depth:
        return
    try:
        children = control.GetChildren()
    except Exception:
        return
    for child in children:
        try:
            if child.ControlType == auto.ControlType.EditControl:
                yield child
            else:
                yield from _iter_edits(child, depth + 1, max_depth)
        except Exception:
            continue


def _iter_combos(control, depth: int = 0, max_depth: int = 10):
    """Yield semua ComboBoxControl (bank) — pola sama seperti _iter_edits."""
    if depth > max_depth:
        return
    try:
        children = control.GetChildren()
    except Exception:
        return
    for child in children:
        try:
            if child.ControlType == auto.ControlType.ComboBoxControl:
                yield child
            else:
                yield from _iter_combos(child, depth + 1, max_depth)
        except Exception:
            continue


def _raw(edit) -> str:
    """Teks mentah pertama yang ada: value → name → legacy, else ''."""
    s = _read_edit_sources(edit)
    return s.get("value") or s.get("name") or s.get("legacy") or ""


def _rect_top(edit) -> int:
    try:
        return edit.BoundingRectangle.top
    except Exception:
        return -1


def _area(edit) -> int:
    try:
        r = edit.BoundingRectangle
        return max(0, r.right - r.left) * max(0, r.bottom - r.top)
    except Exception:
        return 0


def _cached(el_cache: dict, hwnd: int):
    """Elemen cache bila masih hidup (Exists tanpa tunggu), else None + buang."""
    el = el_cache.get(hwnd)
    if el is None:
        return None
    try:
        if el.Exists(0, 0):
            return el
    except Exception:
        pass
    el_cache.pop(hwnd, None)
    return None


def read_dialog_fast(hwnd: int) -> dict:
    """total+tunai saja via cache (~ms). Gagal = '' per field, tidak pernah raise.

    Dipakai tiap tick; bank/debit hanya di full read (~1s). Tanpa full-scan
    kecuali cache miss pertama (satu scan total + tunai aid langsung).
    """
    out = {"total_raw": "", "tunai_raw": "", "debit_raw": "", "bank_raw": ""}
    if not hwnd:
        return out
    try:
        with auto.UIAutomationInitializerInThread():
            el = _cached(_EL_TOTAL, hwnd)
            if el is not None:
                out["total_raw"] = _raw(el)
            el = _cached(_EL_TUNAI, hwnd)
            if el is not None:
                out["tunai_raw"] = _raw(el)
            if out["total_raw"] and out["tunai_raw"]:
                return out
            dlg = auto.ControlFromHandle(hwnd)
            if not dlg or not dlg.Exists(0.5, 0.5):
                return out
            if not out["total_raw"]:
                best, best_area = None, 0
                for e in _iter_edits(dlg):
                    try:
                        if e.ClassName == KETOKO_EDIT_CLASS and e.AutomationId in ("", None):
                            a = _area(e)
                            if a > best_area:
                                best, best_area = e, a
                    except Exception:
                        continue
                if best is not None:
                    _EL_TOTAL[hwnd] = best
                    out["total_raw"] = _raw(best)
            if not out["tunai_raw"]:
                try:
                    t = dlg.EditControl(searchDepth=10, AutomationId="tBayarTunai")
                    if t.Exists(0.5, 0.5):
                        _EL_TUNAI[hwnd] = t
                        out["tunai_raw"] = _raw(t)
                except Exception:
                    pass
    except Exception:
        pass
    return out


def read_dialog(hwnd: int) -> dict:
    """4 field mentah dialog Pembayaran. Gagal = '' per field, tidak pernah raise."""
    out = {"total_raw": "", "tunai_raw": "", "debit_raw": "", "bank_raw": ""}
    if not hwnd:
        return out
    try:
        with auto.UIAutomationInitializerInThread():
            dlg = auto.ControlFromHandle(hwnd)
            if not dlg or not dlg.Exists(1, 0.5):
                return out
            # Total kuning: Edit ClassName obfuscated TERBESAR (kotak 750x108)
            best, best_area = None, 0
            for e in _iter_edits(dlg):
                try:
                    if e.ClassName == KETOKO_EDIT_CLASS and e.AutomationId in ("", None):
                        a = _area(e)
                        if a > best_area:
                            best, best_area = e, a
                except Exception:
                    continue
            if best is not None:
                _EL_TOTAL[hwnd] = best  # ponytail: full scan juga mengisi cache fast path
                out["total_raw"] = _raw(best)
            # Bayar Tunai by aid (satu-satunya field bayar ber-aid stabil)
            try:
                t = dlg.EditControl(searchDepth=10, AutomationId="tBayarTunai")
                if t.Exists(1, 0.5):
                    _EL_TUNAI[hwnd] = t
                    out["tunai_raw"] = _raw(t)
            except Exception:
                pass
            # Bank: combo yang BERNILAI (sudah dipilih) + sebaris Edit
            # nominal di kirinya. Tanpa koordinat absolut (tahan resolusi/DPI
            # beda, mis. kasir 1366x768 vs dev 1080p).
            bank_top = None
            for cb in _iter_combos(dlg):
                try:
                    if not cb.Exists(0.5, 0.5):
                        continue
                    val = _raw(cb)
                    if not val:
                        continue
                    r = cb.BoundingRectangle
                    left = None
                    for e in _iter_edits(dlg):
                        try:
                            er = e.BoundingRectangle
                            if e.ClassName == KETOKO_EDIT_CLASS \
                                    and abs(er.top - r.top) <= 8 \
                                    and er.right <= r.left:
                                left = e
                                break
                        except Exception:
                            continue
                    if left is not None:
                        out["bank_raw"] = val
                        out["debit_raw"] = _raw(left)
                        bank_top = r.top
                        break
                except Exception:
                    continue
            if not out["bank_raw"]:
                # fallback: posisi absolut sesi inspect (1080p)
                for cb in _iter_combos(dlg):
                    try:
                        if not cb.Exists(0.5, 0.5):
                            continue
                        r = cb.BoundingRectangle
                        if abs(r.left - 1014) < 80 and abs(r.top - 565) < 40:
                            out["bank_raw"] = _raw(cb)
                            bank_top = r.top
                            break
                    except Exception:
                        continue
            # Debit: Edit sebaris combo bank. ponytail: dump live membuktikan
            # nominal di field tanpa-aid sebaris bank; tByrKredit = baris
            # tender lain (nilainya 0) -> jangan dipakai sebagai sumber debit.
            if bank_top is not None and not out["debit_raw"]:
                for e in _iter_edits(dlg):
                    try:
                        if e.ClassName == KETOKO_EDIT_CLASS and abs(_rect_top(e) - bank_top) <= 5:
                            out["debit_raw"] = _raw(e)
                            break
                    except Exception:
                        continue
            if not out["debit_raw"]:
                for e in _iter_edits(dlg):
                    try:
                        if e.ClassName == KETOKO_EDIT_CLASS and abs(_rect_top(e) - 565) <= 5:
                            out["debit_raw"] = _raw(e)
                            break
                    except Exception:
                        continue
    except Exception:
        pass
    return out


def read_no_transaksi(hwnd_main: int) -> str:
    """Value parent aid=tNoTransaksi (`Auto` pre-save). '' jika gagal, tidak pernah raise."""
    if not hwnd_main:
        return ""
    try:
        with auto.UIAutomationInitializerInThread():
            el = _cached(_EL_NO, hwnd_main)
            if el is not None:  # ponytail: 1 COM call, tanpa scan/tunggu/Name/Legacy
                try:
                    return el.GetValuePattern().Value or ""
                except Exception:
                    pass
                return _raw(el)  # jarang: Value gagal, coba Name/Legacy tanpa rescan
            m = auto.ControlFromHandle(hwnd_main)
            if not m or not m.Exists(1, 0.5):
                return ""
            # ponytail: typed EditControl agar GetValuePattern tersedia
            e = m.EditControl(searchDepth=10, AutomationId="tNoTransaksi")
            if e and e.Exists(1, 0.5):
                _EL_NO[hwnd_main] = e
                return _raw(e)
    except Exception:
        pass
    return ""


def read_ketoko_value(hwnd: int) -> str:
    """Baca nilai nominal dari window Ketoko via UIAutomation (total berjalan kasir).

    Return string digit bersih atau '' jika gagal/kosong. Tidak pernah raise.
    """
    if not hwnd:
        return ""
    try:
        with auto.UIAutomationInitializerInThread():
            window = auto.ControlFromHandle(hwnd)
            if not window or not window.Exists(1, 0.5):
                return ""
            edit = window.EditControl(searchDepth=10, ClassName=KETOKO_EDIT_CLASS)
            if edit.Exists(1, 0.5):
                for key in ("value", "name", "legacy"):
                    v = _read_edit_sources(edit).get(key, "")
                    if v and v.strip("0.,"):
                        return v
                # ponytail: field nominal ketemu tapi kosong/0 -> percaya, jangan fallback
                return ""
            for ctrl in _iter_edits(window):
                sources = _read_edit_sources(ctrl)
                for key in ("value", "name", "legacy"):
                    raw = sources.get(key, "")
                    if "/" in raw or ":" in raw:
                        continue  # ponytail: tolak tanggal/jam
                    if raw and raw.strip("0.,"):
                        return raw
    except Exception:
        pass
    return ""
