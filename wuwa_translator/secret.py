"""Simpan API key terenkripsi dengan Windows DPAPI (CryptProtectData).

Hasil enkripsi cuma bisa dibuka oleh akun Windows yang sama di PC yang sama. Jadi kalau config.json
tersalin/tercuri ke tempat lain, key-nya tidak bisa dibaca.
"""
from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes

_crypt32 = ctypes.windll.crypt32
_kernel32 = ctypes.windll.kernel32
_ENTROPY = b"wuwa-translator/deepl-key/v1"
CRYPTPROTECT_UI_FORBIDDEN = 0x1


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> tuple[_Blob, ctypes.Array]:
    buf = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def _take(blob: _Blob) -> bytes:
    try:
        return ctypes.string_at(blob.pbData, blob.cbData)
    finally:
        _kernel32.LocalFree(blob.pbData)


def protect(text: str) -> str:
    data, _b1 = _blob(text.encode("utf-8"))
    ent, _b2 = _blob(_ENTROPY)
    out = _Blob()
    if not _crypt32.CryptProtectData(ctypes.byref(data), "WuWa Translator", ctypes.byref(ent), None, None,
                                     CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out)):
        raise OSError("Gagal mengenkripsi API key")
    return base64.b64encode(_take(out)).decode()


def unprotect(token: str) -> str | None:
    """None kalau tidak bisa dibuka (mis. config disalin dari PC/akun lain)."""
    try:
        data, _b1 = _blob(base64.b64decode(token))
    except ValueError:
        return None
    ent, _b2 = _blob(_ENTROPY)
    out = _Blob()
    if not _crypt32.CryptUnprotectData(ctypes.byref(data), None, ctypes.byref(ent), None, None,
                                       CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out)):
        return None
    return _take(out).decode("utf-8")
