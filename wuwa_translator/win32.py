"""Bantuan Win32 via ctypes: DPI, jendela click-through, exclude-from-capture, hotkey global."""
from __future__ import annotations

import ctypes
import queue
import threading
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x20
WS_EX_TOOLWINDOW = 0x80
WS_EX_LAYERED = 0x80000
WS_EX_NOACTIVATE = 0x08000000
WDA_EXCLUDEFROMCAPTURE = 0x11

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x4000
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012

_GetLong = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
_SetLong = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
_GetLong.restype = ctypes.c_ssize_t
_GetLong.argtypes = [wintypes.HWND, ctypes.c_int]
_SetLong.restype = ctypes.c_ssize_t
_SetLong.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]


def enable_dpi_awareness():
    """Supaya koordinat Tk = koordinat piksel asli (sama dengan screenshot)."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        user32.SetProcessDPIAware()


def virtual_screen() -> tuple[int, int, int, int]:
    return tuple(user32.GetSystemMetrics(i) for i in (76, 77, 78, 79))  # x, y, w, h


def toplevel_hwnd(tk_widget) -> int:
    return user32.GetParent(tk_widget.winfo_id()) or tk_widget.winfo_id()


def set_click_through(hwnd: int, enabled: bool):
    style = _GetLong(hwnd, GWL_EXSTYLE) | WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
    style = style | WS_EX_TRANSPARENT if enabled else style & ~WS_EX_TRANSPARENT
    _SetLong(hwnd, GWL_EXSTYLE, style)


def exclude_from_capture(hwnd: int) -> bool:
    """Overlay tidak ikut ter-screenshot, jadi tidak mengganggu OCR walau menutupi area dialog."""
    return bool(user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE))


_VK = {**{f"F{i}": 0x6F + i for i in range(1, 13)}, **{chr(c): c for c in range(0x30, 0x5B)}}


def parse_hotkey(spec: str) -> tuple[int, int]:
    mods, vk = MOD_NOREPEAT, None
    for part in (p.strip().upper() for p in spec.split("+")):
        if part in ("CTRL", "CONTROL"):
            mods |= MOD_CONTROL
        elif part == "ALT":
            mods |= MOD_ALT
        elif part == "SHIFT":
            mods |= MOD_SHIFT
        elif part in _VK:
            vk = _VK[part]
        else:
            raise ValueError(f"Tombol tidak dikenal di hotkey '{spec}': {part}")
    if vk is None:
        raise ValueError(f"Hotkey '{spec}' tidak punya tombol utama")
    return mods, vk


class HotkeyThread(threading.Thread):
    """RegisterHotKey tetap jalan walau game sedang fokus (termasuk game yang jalan sebagai admin)."""

    def __init__(self, bindings: dict[str, str], out: queue.Queue):
        super().__init__(daemon=True)
        self.bindings = bindings  # action -> "Ctrl+Alt+T"
        self.out = out
        self._tid = None

    def run(self):
        self._tid = kernel32.GetCurrentThreadId()
        ids = {}
        for i, (action, spec) in enumerate(self.bindings.items(), start=1):
            mods, vk = parse_hotkey(spec)
            if user32.RegisterHotKey(None, i, mods, vk):
                ids[i] = action
            else:
                self.out.put(("status", f"Hotkey {spec} ({action}) gagal didaftarkan, mungkin dipakai aplikasi lain"))
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY and msg.wParam in ids:
                self.out.put(("hotkey", ids[msg.wParam]))
        for i in ids:
            user32.UnregisterHotKey(None, i)

    def stop(self):
        if self._tid:
            user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
