"""Mode otomatis: baca seluruh layar (OCR Windows, CPU), terjemahkan kalimat, tempel di posisi teks aslinya.

- Mode Cerita (jalan terus): hanya teks yang berbentuk kalimat (dialog, pilihan jawaban, tutorial, quest).
- Snapshot (hotkey): semua teks di layar sekali jalan (menu, deskripsi item/Echo), tekan lagi untuk kembali.
"""
from __future__ import annotations

import difflib
import queue
import re
import statistics
import threading
import time
import tkinter as tk
from dataclasses import dataclass, field

import mss
from PIL import Image

from . import win32


# ---------------------------------------------------------------- blok teks
@dataclass
class Block:
    lines: list[tuple[str, float, float, float, float]] = field(default_factory=list)

    @property
    def text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(l[0] for l in self.lines)).strip()

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return (min(l[1] for l in self.lines), min(l[2] for l in self.lines),
                max(l[3] for l in self.lines), max(l[4] for l in self.lines))

    @property
    def line_h(self) -> float:
        return statistics.median(l[4] - l[2] for l in self.lines)

    @property
    def centered(self) -> bool:
        if len(self.lines) < 2:
            return False
        centers = [(l[1] + l[3]) / 2 for l in self.lines]
        lefts = [l[1] for l in self.lines]
        return (max(centers) - min(centers)) < (max(lefts) - min(lefts)) * 0.6


def group_blocks(lines) -> list[Block]:
    """Gabungkan baris yang berdekatan (ukuran huruf sama, sejajar) menjadi satu paragraf."""
    blocks: list[Block] = []
    for ln in sorted(lines, key=lambda l: (l[2], l[1])):
        text, x1, y1, x2, y2 = ln
        h = y2 - y1
        placed = False
        for b in blocks:
            last = b.lines[-1]
            lh = last[4] - last[2]
            gap = y1 - last[4]
            same_size = abs(h - lh) < 0.35 * max(h, lh)
            overlap = min(x2, last[3]) - max(x1, last[1])
            aligned = overlap > 0 and (abs((x1 + x2) / 2 - (last[1] + last[3]) / 2) < 0.5 * max(x2 - x1, last[3] - last[1])
                                       or abs(x1 - last[1]) < 1.5 * lh)
            if -0.3 * lh < gap < 0.9 * lh and same_size and aligned:
                b.lines.append(ln)
                placed = True
                break
        if not placed:
            blocks.append(Block([ln]))
    # Nama pembicara (baris pertama pendek tanpa tanda baca) dipisah: tidak diterjemahkan & tidak ditutup
    out: list[Block] = []
    for b in blocks:
        first = b.lines[0][0].strip()
        if len(b.lines) >= 2 and len(first.split()) <= 3 and len(first) <= 24 and not first.endswith(_TERMINAL):
            out.append(Block([b.lines[0]]))
            out.append(Block(b.lines[1:]))
        else:
            out.append(b)
    return out


_TERMINAL = tuple(".!?…,:;\"'”’)—-~")


def is_sentence(text: str, line_h: float) -> bool:
    letters = sum(c.isalpha() for c in text)
    digits = sum(c.isdigit() for c in text)
    words = len(re.findall(r"[A-Za-z][A-Za-z'’-]*", text))
    return line_h >= 12 and letters >= 8 and words >= 3 and digits <= 0.3 * max(1, letters)


def is_label(text: str, line_h: float) -> bool:
    letters = sum(c.isalpha() for c in text)
    digits = sum(c.isdigit() for c in text)
    return line_h >= 10 and letters >= 3 and digits <= letters


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9]", "", t.lower())


# ---------------------------------------------------------------- pipeline
@dataclass
class Shown:
    bbox: tuple[float, float, float, float]
    line_h: float
    centered: bool
    original: str
    translated: str
    misses: int = 0


class AutoPipeline(threading.Thread):
    def __init__(self, cfg: dict, ocr, translator, out: queue.Queue):
        super().__init__(daemon=True)
        self.cfg, self.ocr, self.translator, self.out = cfg, ocr, translator, out
        self.paused = threading.Event()
        self.stopped = threading.Event()
        self.snapshot_requested = threading.Event()
        self.in_snapshot = False
        self.prev_norms: set[str] = set()
        self.shown: dict[str, Shown] = {}

    # ---- satu langkah (bisa dipanggil langsung untuk tes) ----
    def process(self, img: Image.Image, origin=(0, 0), snapshot: bool = False) -> list[Shown] | None:
        """Return daftar teks yang harus tampil, atau None bila tidak ada perubahan."""
        ox, oy = origin
        blocks = group_blocks(self.ocr.read_line_boxes(img))
        keep = is_label if snapshot else is_sentence
        blocks = [b for b in blocks if keep(b.text, b.line_h)]
        norms = {_norm(b.text): b for b in blocks}

        # Mode cerita: terjemahkan hanya teks yang sudah sama di 2 pembacaan (efek mengetik selesai)
        stable = blocks if snapshot else [b for n, b in norms.items() if n in self.prev_norms]
        self.prev_norms = set(norms)

        todo = [b for b in stable if _norm(b.text) not in self.shown and not self._similar_shown(b)]
        if todo:
            context = " ".join(b.text for b in stable)[:3000]
            try:
                translated = self.translator.translate_many([b.text for b in todo], context=context)
            except Exception as e:  # noqa: BLE001
                self.out.put(("status", f"Gagal menerjemahkan: {e}"))
                translated = None
            if translated:
                for b, tr in zip(todo, translated):
                    x1, y1, x2, y2 = b.bbox
                    self.shown[_norm(b.text)] = Shown((x1 + ox, y1 + oy, x2 + ox, y2 + oy), b.line_h,
                                                      b.centered, b.text, tr)
        changed = bool(todo)
        # perbarui posisi & buang yang sudah hilang (beri toleransi 1x OCR meleset)
        for n, s in list(self.shown.items()):
            match = norms.get(n) or self._similar_block(s, blocks)
            if match:
                s.misses = 0
                x1, y1, x2, y2 = match.bbox
                nb = (x1 + ox, y1 + oy, x2 + ox, y2 + oy)
                if max(abs(a - b) for a, b in zip(nb, s.bbox)) > 4:
                    s.bbox, changed = nb, True
            else:
                s.misses += 1
                if s.misses >= (1 if snapshot else 2):
                    del self.shown[n]
                    changed = True
        return list(self.shown.values()) if changed else None

    def _similar_shown(self, b: Block) -> bool:
        n = _norm(b.text)
        return any(difflib.SequenceMatcher(None, n, k).ratio() > 0.92 for k in self.shown)

    @staticmethod
    def _similar_block(s: Shown, blocks: list[Block]) -> Block | None:
        n = _norm(s.original)
        for b in blocks:
            if difflib.SequenceMatcher(None, n, _norm(b.text)).ratio() > 0.92:
                return b
        return None

    def reset(self):
        self.shown.clear()
        self.prev_norms.clear()
        self.out.put(("auto", []))

    # ---- loop ----
    def run(self):
        interval = self.cfg.get("auto_interval_ms", 400) / 1000
        with mss.mss() as sct:
            while not self.stopped.is_set():
                start = time.perf_counter()
                try:
                    if self.snapshot_requested.is_set():
                        self.snapshot_requested.clear()
                        self._toggle_snapshot(sct)
                    elif not self.paused.is_set() and not self.in_snapshot:
                        mon = sct.monitors[min(self.cfg.get("monitor", 1), len(sct.monitors) - 1)]
                        shot = sct.grab(mon)
                        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                        res = self.process(img, (mon["left"], mon["top"]))
                        if res is not None:
                            self.out.put(("auto", res))
                except Exception as e:  # noqa: BLE001
                    self.out.put(("status", f"Error: {e}"))
                    time.sleep(1)
                time.sleep(max(0.0, interval - (time.perf_counter() - start)))

    def _toggle_snapshot(self, sct):
        if self.in_snapshot:
            self.in_snapshot = False
            self.reset()
            self.out.put(("status", "Snapshot ditutup"))
            return
        mon = sct.monitors[min(self.cfg.get("monitor", 1), len(sct.monitors) - 1)]
        shot = sct.grab(mon)
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        self.shown.clear()
        self.in_snapshot = True
        res = self.process(img, (mon["left"], mon["top"]), snapshot=True) or []
        self.out.put(("auto", res))
        self.out.put(("status", f"Snapshot: {len(res)} teks diterjemahkan (tekan lagi untuk menutup)"))


# ---------------------------------------------------------------- overlay
class InPlaceOverlay:
    """Jendela transparan seukuran monitor; terjemahan digambar tepat di atas teks aslinya.
    Tembus klik dan tidak ikut ter-screenshot (jadi OCR tetap membaca teks asli di bawahnya)."""

    KEY = "#010203"  # warna yang dibuat transparan

    def __init__(self, root: tk.Tk, cfg: dict):
        self.cfg = cfg
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-transparentcolor", self.KEY)
        self.win.attributes("-alpha", cfg.get("auto_opacity", 0.94))
        self.canvas = tk.Canvas(self.win, bg=self.KEY, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.place_on_monitor()
        self.win.update_idletasks()
        self.hwnd = win32.toplevel_hwnd(self.win)
        win32.set_click_through(self.hwnd, True)
        win32.exclude_from_capture(self.hwnd)
        self.hidden = False

    def place_on_monitor(self):
        with mss.mss() as sct:
            mon = sct.monitors[min(self.cfg.get("monitor", 1), len(sct.monitors) - 1)]
        self.origin = (mon["left"], mon["top"])
        self.win.geometry(f"{mon['width']}x{mon['height']}+{mon['left']}+{mon['top']}")

    def draw(self, items: list[Shown]):
        c = self.canvas
        c.delete("all")
        ox, oy = self.origin
        fam = self.cfg.get("font_family", "Segoe UI")
        for s in items:
            x1, y1, x2, y2 = s.bbox
            x1, x2, y1, y2 = x1 - ox, x2 - ox, y1 - oy, y2 - oy
            size = max(12, int(s.line_h * 0.92))
            width = max((x2 - x1) * 1.15, size * 8)
            if s.centered or (x2 - x1) < size * 10:
                tid = c.create_text((x1 + x2) / 2, y1 - 2, text=s.translated, anchor="n", width=width,
                                    justify="center", fill="#ffffff", font=(fam, -size))
            else:
                tid = c.create_text(x1, y1 - 2, text=s.translated, anchor="nw", width=width,
                                    justify="left", fill="#ffffff", font=(fam, -size))
            bx1, by1, bx2, by2 = c.bbox(tid)
            # kotak gelap menutupi teks asli + terjemahan
            rx1, ry1 = min(bx1, x1) - 6, min(by1, y1) - 3
            rx2, ry2 = max(bx2, x2) + 6, max(by2, y2) + 3
            rid = c.create_rectangle(rx1, ry1, rx2, ry2, fill="#12141b", outline="")
            c.tag_lower(rid, tid)
        if not self.hidden:
            self.win.deiconify()
            self.win.attributes("-topmost", True)

    def set_hidden(self, hidden: bool):
        self.hidden = hidden
        if hidden:
            self.win.withdraw()
        else:
            self.win.deiconify()

    def clear(self):
        self.canvas.delete("all")
