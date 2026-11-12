"""Overlay terjemahan Wuthering Waves (EN -> ID) berbasis OCR layar + DeepL."""
from __future__ import annotations

import argparse
import json
import os
import queue
import sys
import tkinter as tk
from pathlib import Path

from . import win32
from .ocr import WindowsOcr
from .pipeline import Dialog, Pipeline
from .translator import DeepLTranslator, Glossary, MockTranslator

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"

DEFAULTS = {
    "deepl_auth_key": "",
    "source_lang": "EN",
    "target_lang": "ID",
    "region": None,
    "overlay_pos": None,
    "overlay_width": None,
    "font_family": "Segoe UI",
    "font_size": 16,
    "show_original": False,
    "opacity": 0.86,
    "detect_speaker": True,
    "interval_ms": 350,
    "stable_reads": 2,
    "clear_after_empty_reads": 4,
    "ocr_lang": "en-US",
    "ocr_scale": 2.0,
    "ocr_invert": False,
    "hotkeys": {
        "toggle": "Ctrl+Alt+T",
        "select_region": "Ctrl+Alt+R",
        "move": "Ctrl+Alt+M",
        "pause": "Ctrl+Alt+P",
        "original": "Ctrl+Alt+O",
        "quit": "Ctrl+Alt+Q",
    },
}


def load_config() -> dict:
    cfg = json.loads(json.dumps(DEFAULTS))
    if CONFIG_PATH.exists():
        user = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        hotkeys = {**cfg["hotkeys"], **user.get("hotkeys", {})}
        cfg.update(user)
        cfg["hotkeys"] = hotkeys
    else:
        save_config(cfg)
    return cfg


def save_config(cfg: dict):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def make_translator(cfg: dict, mock: bool):
    glossary = Glossary(ROOT / "glossary.txt")
    if mock:
        return MockTranslator(glossary)
    key = os.environ.get("DEEPL_AUTH_KEY") or cfg.get("deepl_auth_key")
    if not key:
        sys.exit("API key DeepL belum diisi. Isi \"deepl_auth_key\" di config.json "
                 "(atau jalankan dengan --mock untuk mencoba tanpa DeepL).")
    return DeepLTranslator(key, glossary, ROOT / "translation_cache.json",
                           cfg["source_lang"], cfg["target_lang"])


class Overlay:
    BG, FG, SPEAKER, ORIG = "#14161e", "#ffffff", "#f2c76e", "#9aa3b5"

    def __init__(self, root: tk.Tk, cfg: dict):
        self.root, self.cfg = root, cfg
        self.moving = False
        self.user_hidden = False
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", cfg["opacity"])
        root.configure(bg=self.BG)
        f, s = cfg["font_family"], cfg["font_size"]
        self.speaker = tk.Label(root, bg=self.BG, fg=self.SPEAKER, font=(f, s - 2, "bold"), anchor="w", justify="left")
        self.text = tk.Label(root, bg=self.BG, fg=self.FG, font=(f, s), anchor="w", justify="left")
        self.orig = tk.Label(root, bg=self.BG, fg=self.ORIG, font=(f, max(9, s - 5)), anchor="w", justify="left")
        root.update_idletasks()
        self.hwnd = win32.toplevel_hwnd(root)
        win32.set_click_through(self.hwnd, True)
        if not win32.exclude_from_capture(self.hwnd):
            print("Peringatan: overlay tidak bisa dikecualikan dari screenshot. Jangan taruh overlay di atas area dialog.")
        for w in (root, self.speaker, self.text, self.orig):
            w.bind("<ButtonPress-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag)
        self._last: Dialog | None = None

    def width(self) -> int:
        r = self.cfg.get("region")
        return self.cfg.get("overlay_width") or (r["width"] if r else 900)

    def show_message(self, msg: str):
        self._render("", msg, "")

    def show_dialog(self, d: Dialog):
        self._last = d
        self._render(d.speaker, d.translated, d.original if self.cfg["show_original"] else "")

    def rerender(self):
        if self._last:
            self.show_dialog(self._last)

    def clear(self):
        self._last = None
        if not self.moving:
            self.root.withdraw()

    def _render(self, speaker: str, text: str, orig: str):
        wrap = self.width() - 28
        for lbl in (self.speaker, self.text, self.orig):
            lbl.pack_forget()
            lbl.configure(wraplength=wrap)
        if speaker:
            self.speaker.configure(text=speaker)
            self.speaker.pack(fill="x", padx=14, pady=(8, 0))
        self.text.configure(text=text)
        self.text.pack(fill="x", padx=14, pady=(8 if not speaker else 2, 8 if not orig else 2))
        if orig:
            self.orig.configure(text=orig)
            self.orig.pack(fill="x", padx=14, pady=(0, 8))
        self.root.update_idletasks()
        h = self.root.winfo_reqheight()
        x, y = self._position(h)
        self.root.geometry(f"{self.width()}x{h}+{x}+{y}")
        if self.user_hidden and not self.moving:
            return
        self.root.deiconify()
        self.root.attributes("-topmost", True)

    def _position(self, h: int) -> tuple[int, int]:
        if self.cfg.get("overlay_pos"):
            return tuple(self.cfg["overlay_pos"])
        r = self.cfg.get("region")
        if not r:
            vx, vy, vw, vh = win32.virtual_screen()
            return vx + (vw - self.width()) // 2, vy + vh // 8
        # Default: tepat di atas kotak dialog
        return r["left"], max(0, r["top"] - h - 10)

    def toggle_move(self) -> bool:
        self.moving = not self.moving
        win32.set_click_through(self.hwnd, not self.moving)
        self.root.configure(highlightthickness=3 if self.moving else 0, highlightbackground="#4da3ff")
        if self.moving:
            if not self._last:
                self.show_message("Seret kotak ini ke posisi yang kamu mau, lalu tekan hotkey Move lagi.")
        else:
            self.cfg["overlay_pos"] = [self.root.winfo_x(), self.root.winfo_y()]
            save_config(self.cfg)
        return self.moving

    def _drag_start(self, e):
        self._dx, self._dy = e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y()

    def _drag(self, e):
        if self.moving:
            self.root.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")


class RegionSelector:
    """Layar gelap transparan; seret kotak di sekitar teks dialog game."""

    def __init__(self, root: tk.Tk, on_done):
        self.on_done = on_done
        vx, vy, vw, vh = win32.virtual_screen()
        self.ox, self.oy = vx, vy
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.35)
        self.win.geometry(f"{vw}x{vh}+{vx}+{vy}")
        self.canvas = tk.Canvas(self.win, bg="black", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_text(vw // 2, 60, fill="white", font=("Segoe UI", 20, "bold"),
                                text="Seret kotak di sekitar teks dialog (nama + kalimat).  Esc = batal")
        self.rect = None
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._motion)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.win.bind("<Escape>", lambda e: self._finish(None))
        self.win.focus_force()

    def _press(self, e):
        self.sx, self.sy = e.x, e.y
        self.rect = self.canvas.create_rectangle(e.x, e.y, e.x, e.y, outline="#ff4d4d", width=3, fill="white")

    def _motion(self, e):
        if self.rect:
            self.canvas.coords(self.rect, self.sx, self.sy, e.x, e.y)

    def _release(self, e):
        x1, x2 = sorted((self.sx, e.x))
        y1, y2 = sorted((self.sy, e.y))
        if x2 - x1 < 40 or y2 - y1 < 15:
            self._finish(None)
            return
        self._finish({"left": x1 + self.ox, "top": y1 + self.oy, "width": x2 - x1, "height": y2 - y1})

    def _finish(self, region):
        self.win.destroy()
        self.on_done(region)


class App:
    def __init__(self, cfg: dict, translator):
        self.cfg = cfg
        self.events: queue.Queue = queue.Queue()
        self.root = tk.Tk()
        self.root.title("WuWa Translator")
        self.overlay = Overlay(self.root, cfg)
        ocr = WindowsOcr(cfg["ocr_lang"], cfg["ocr_scale"], cfg["ocr_invert"])
        self.pipeline = Pipeline(cfg, ocr, translator, self.events)
        self.hotkeys = win32.HotkeyThread(cfg["hotkeys"], self.events)
        self.selecting = False
        hk = cfg["hotkeys"]
        print(translator.usage_text() if hasattr(translator, "usage_text") else "")
        print("Hotkey: " + ", ".join(f"{v} = {k}" for k, v in hk.items()))
        if cfg.get("region"):
            self.overlay.show_message(f"Siap. Overlay akan muncul saat ada dialog.  ({hk['quit']} = keluar)")
            self.root.after(2500, lambda: self.overlay.clear() if not self.overlay._last else None)
        else:
            self.overlay.show_message(f"Tekan {hk['select_region']} lalu seret kotak di sekitar teks dialog game.")

    def run(self):
        self.pipeline.start()
        self.hotkeys.start()
        self.root.after(50, self._poll)
        try:
            self.root.mainloop()
        finally:
            self.pipeline.stopped.set()
            self.hotkeys.stop()

    def _poll(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "dialog":
                    if payload == "clear":
                        self.overlay.clear()
                    else:
                        print(f"\n[{payload.speaker or '-'}] {payload.original}\n  -> {payload.translated}")
                        self.overlay.show_dialog(payload)
                elif kind == "status":
                    print(payload)
                elif kind == "hotkey":
                    self._hotkey(payload)
        except queue.Empty:
            pass
        self.root.after(50, self._poll)

    def _hotkey(self, action: str):
        if action == "quit":
            self.root.destroy()
        elif action == "toggle":
            ov = self.overlay
            ov.user_hidden = not ov.user_hidden
            if ov.user_hidden:
                ov.root.withdraw()
            elif ov._last:
                ov.rerender()
            else:
                ov.show_message("Overlay aktif")
        elif action == "select_region" and not self.selecting:
            self.selecting = True
            self.pipeline.paused.set()
            RegionSelector(self.root, self._region_done)
        elif action == "move":
            self.overlay.toggle_move()
        elif action == "pause":
            if self.pipeline.paused.is_set():
                self.pipeline.paused.clear()
                self.overlay.show_message("Terjemahan dilanjutkan")
            else:
                self.pipeline.paused.set()
                self.overlay.show_message("Terjemahan dijeda")
        elif action == "original":
            self.cfg["show_original"] = not self.cfg["show_original"]
            save_config(self.cfg)
            self.overlay.rerender()

    def _region_done(self, region):
        self.selecting = False
        if region:
            self.cfg["region"] = region
            save_config(self.cfg)
            self.pipeline.reset()
            self.overlay.show_message(f"Area disimpan: {region['width']}x{region['height']} di ({region['left']}, {region['top']})")
        self.pipeline.paused.clear()


def test_image(path: str, cfg: dict, translator):
    """Uji pipeline pada screenshot tanpa membuka jendela apa pun."""
    from PIL import Image

    img = Image.open(path)
    ocr = WindowsOcr(cfg["ocr_lang"], cfg["ocr_scale"], cfg["ocr_invert"])
    p = Pipeline({**cfg, "stable_reads": 1}, ocr, translator, queue.Queue())
    print("OCR:", ocr.read_lines(img))
    d = p.process_image(img)
    if isinstance(d, Dialog):
        print(f"Pembicara : {d.speaker or '-'}\nAsli      : {d.original}\nTerjemahan: {d.translated}")
    else:
        print("Tidak ada teks yang terbaca.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mock", action="store_true", help="coba tanpa DeepL (tidak memakai kuota)")
    ap.add_argument("--test-image", metavar="PNG", help="uji OCR+terjemah pada sebuah screenshot")
    args = ap.parse_args()

    win32.enable_dpi_awareness()
    cfg = load_config()
    translator = make_translator(cfg, args.mock)
    if args.test_image:
        test_image(args.test_image, cfg, translator)
    else:
        App(cfg, translator).run()


if __name__ == "__main__":
    main()
