"""Dump dialog Pembayaran KetokoD.exe ke JSON (Fase 0 gate)."""
import ctypes
import json
import os
from ctypes import wintypes

import uiautomation as auto

PROC = "KetokoD.exe"


def proc_name(hwnd: int) -> str:
    try:
        pid = wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return ""
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid.value)
        if not h:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(260)
            sz = wintypes.DWORD(260)
            if ctypes.windll.kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(sz)):
                return os.path.basename(buf.value)
        finally:
            ctypes.windll.kernel32.CloseHandle(h)
    except Exception:
        pass
    return ""


def top_windows():
    out = []
    cb = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    @cb
    def _cb(hwnd, _):
        try:
            if not ctypes.windll.user32.IsWindowVisible(hwnd):
                return True
            n = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetWindowTextW(hwnd, n, 256)
            out.append((hwnd, n.value))
        except Exception:
            pass
        return True

    ctypes.windll.user32.EnumWindows(_cb, 0)
    return out


def _value(c) -> str:
    try:
        return (c.GetValuePattern().Value or "")[:120]
    except Exception:
        return ""


def dump_ctrl(c, depth=0, max_depth=10):
    if depth > max_depth:
        return None
    try:
        rect = c.BoundingRectangle
        rect = [rect.left, rect.top, rect.right, rect.bottom]
    except Exception:
        rect = []
    try:
        pats = [p for p in ("Value", "Invoke", "LegacyIAccessible", "ExpandCollapse") if hasattr(c, f"Get{p}Pattern")]
    except Exception:
        pats = []
    node = {
        "ControlType": str(getattr(c, "ControlType", "")),
        "ClassName": getattr(c, "ClassName", ""),
        "AutomationId": getattr(c, "AutomationId", ""),
        "Name": (getattr(c, "Name", "") or "")[:120],
        "Rect": rect,
        "Patterns": pats,
    }
    v = _value(c)
    if v:
        node["Value"] = v
    try:
        kids = c.GetChildren()
    except Exception:
        return node
    subs = []
    for k in kids:
        try:
            if k.ControlType == auto.ControlType.EditControl:
                d = dump_ctrl(k, max_depth=0)
            else:
                d = dump_ctrl(k, depth + 1, max_depth)
            if d:
                subs.append(d)
        except Exception:
            continue
    if subs:
        node["children"] = subs
    return node


def _walk_find(node, aid):
    if node.get("AutomationId") == aid:
        return node
    for k in node.get("children", []):
        r = _walk_find(k, aid)
        if r:
            return r
    return None


def main():
    wins = []
    dialog = None
    with auto.UIAutomationInitializerInThread():
        for hwnd, title in top_windows():
            if proc_name(hwnd).lower() != PROC.lower():
                continue
            try:
                c = auto.ControlFromHandle(hwnd)
                name = c.Name if c else title
            except Exception:
                name = title
            wins.append({"hwnd": hwnd, "title": title, "uia_name": name})
            if name == "Pembayaran" and dialog is None:
                try:
                    dialog = dump_ctrl(auto.ControlFromHandle(hwnd))
                    dialog["hwnd"] = hwnd
                except Exception as e:
                    dialog = {"error": repr(e), "hwnd": hwnd}
        targets = {"MainWindow": None, "tNoTransaksi": None, "tBayarTunai": None, "ButSimpanCetak": None}
        for w in wins:
            if "Ketoko" in (w.get("uia_name") or ""):
                targets["MainWindow"] = {"hwnd": w["hwnd"], "AutomationId": "MainWindow", "Name": w["uia_name"]}
                try:
                    m = auto.ControlFromHandle(w["hwnd"])
                    # ponytail: typed EditControl agar GetValuePattern tersedia
                    e = m.EditControl(searchDepth=10, AutomationId="tNoTransaksi")
                    if e and e.Exists(1, 0.5):
                        targets["tNoTransaksi"] = dump_ctrl(e, max_depth=0)
                    else:
                        mc = dump_ctrl(m, max_depth=10)
                        targets["tNoTransaksi"] = _walk_find(mc, "tNoTransaksi")
                except Exception:
                    pass
                break
        if dialog:
            # ponytail: ambil target dari tree yang sudah di-dump, tanpa search UIA kedua
            for key in ("tBayarTunai", "ButSimpanCetak"):
                targets[key] = _walk_find(dialog, key)
    print(json.dumps({"windows": wins, "dialog": dialog, **targets}, indent=1, default=str))


if __name__ == "__main__":
    main()
