"""Overlay terjemahan Wuthering Waves (EN -> ID) berbasis OCR layar + DeepL."""
from __future__ import annotations

import argparse
import json
import os
import queue
import sys
import tkinter as tk
from pathlib import Path

from . import secret, win32
from .auto_mode import AutoPipeline, InPlaceOverlay
from .ocr import WindowsOcr
from .pipeline import Dialog, Pipeline
from .translator import DeepLTranslator, Glossary, MockTranslator

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"

DEFAULTS = {
    "deepl_auth_key": "",            # lama (teks biasa); otomatis dipindah ke versi terenkripsi
    "deepl_auth_key_protected": "",  # API key terenkripsi Windows DPAPI (cuma bisa dibuka akun Windows ini)
    "mode": "auto",            # "auto" = baca seluruh layar, "region" = hanya area yang dipilih
    "monitor": 1,              # monitor tempat game (1 = monitor utama)
    "auto_interval_ms": 400,
    "auto_opacity": 0.94,
    "auto_ocr_scale": 1.0,
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
        "snapshot": "Ctrl+Alt+S",
        "mode": "Ctrl+Alt+A",
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
    if cfg.get("deepl_auth_key"):
        # Pindahkan key teks biasa ke versi terenkripsi, lalu hapus yang teks biasa
        cfg["deepl_auth_key_protected"] = secret.protect(cfg["deepl_auth_key"])
        cfg["deepl_auth_key"] = ""
        save_config(cfg)
        print("API key DeepL sekarang disimpan terenkripsi (Windows DPAPI).")
    return cfg


def save_config(cfg: dict):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def make_translator(cfg: dict, mock: bool):
    glossary = Glossary(ROOT / "glossary.txt")
    if mock:
        return MockTranslator(glossary)
    stored = secret.unprotect(cfg["deepl_auth_key_protected"]) if cfg.get("deepl_auth_key_protected") else None
    key = os.environ.get("DEEPL_AUTH_KEY") or stored or ask_key(cfg)
    if not key:
        sys.exit("Butuh API key DeepL. Jalankan lagi lalu isi key-nya (atau pakai --mock untuk mencoba).")
    return DeepLTranslator(key, glossary, ROOT / "translation_cache.json",
                           cfg["source_lang"], cfg["target_lang"])


def ask_key(cfg: dict) -> str | None:
    """Tanyakan API key DeepL lewat jendela kecil saat pertama dipakai, cek, lalu simpan di config.json (lokal)."""
    import deepl
    from tkinter import messagebox, simpledialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        while True:
            key = simpledialog.askstring(
                "WuWa Translator",
                "Masukkan API key DeepL kamu (DeepL API Free, berakhiran :fx).\n"
                "Belum punya? Daftar gratis di https://www.deepl.com/pro-api",
                show="*", parent=root)
            if not key or not key.strip():
                return None
            key = key.strip()
            try:
                deepl.DeepLClient(key).get_usage()
            except deepl.AuthorizationException:
                messagebox.showerror("WuWa Translator", "API key tidak valid. Coba lagi.", parent=root)
                continue
            except Exception:  # noqa: BLE001 - jaringan bermasalah: simpan saja, dicek saat dipakai
                pass
            cfg["deepl_auth_key_protected"] = secret.protect(key)
            cfg["deepl_auth_key"] = ""
            save_config(cfg)
            return key
    finally:
        root.destroy()


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
        auto_ocr = WindowsOcr(cfg["ocr_lang"], cfg["auto_ocr_scale"], cfg["ocr_invert"])
        self.auto = AutoPipeline(cfg, auto_ocr, translator, self.events)
        self.inplace = InPlaceOverlay(self.root, cfg)
        self.hotkeys = win32.HotkeyThread(cfg["hotkeys"], self.events)
        self.selecting = False
        try:
            print(translator.usage_text())
        except Exception as e:  # noqa: BLE001
            print("Tidak bisa cek kuota DeepL:", e)
        self._apply_mode()

    def _apply_mode(self):
        hk = self.cfg["hotkeys"]
        if self.cfg.get("mode", "auto") == "auto":
            self.pipeline.paused.set()
            self.auto.paused.clear()
            self.overlay.clear()
            msg = (f"Mode OTOMATIS: kalimat di layar diterjemahkan di tempatnya.  {hk['snapshot']} = terjemahkan "
                   f"semua teks (menu)  ·  {hk['mode']} = ganti mode  ·  {hk['quit']} = keluar")
        else:
            self.auto.paused.set()
            self.auto.reset()
            self.pipeline.paused.clear()
            msg = (f"Mode AREA aktif.  {hk['mode']} = ganti mode  ·  {hk['quit']} = keluar" if self.cfg.get("region")
                   else f"Mode AREA: {hk['select_region']} untuk pilih area dialog  ·  {hk['mode']} = ganti mode")
        print(msg)
        print("Hotkey: " + ", ".join(f"{v} = {k}" for k, v in hk.items()))
        self.overlay.show_message(msg)
        self.root.after(4000, lambda: self.overlay.clear() if not self.overlay._last else None)

    def run(self):
        self.pipeline.start()
        self.auto.start()
        self.hotkeys.start()
        self.root.after(50, self._poll)
        try:
            self.root.mainloop()
        finally:
            self.pipeline.stopped.set()
            self.auto.stopped.set()
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
                elif kind == "auto":
                    self.inplace.draw(payload)
                    for s in payload:
                        print(f"  {s.original}\n    -> {s.translated}")
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
            self.inplace.set_hidden(ov.user_hidden)
            if ov.user_hidden:
                ov.root.withdraw()
            elif ov._last:
                ov.rerender()
            else:
                ov.show_message("Overlay aktif")
        elif action == "snapshot":
            self.auto.snapshot_requested.set()
        elif action == "mode":
            self.cfg["mode"] = "region" if self.cfg.get("mode", "auto") == "auto" else "auto"
            save_config(self.cfg)
            self._apply_mode()
        elif action == "select_region" and not self.selecting:
            if self.cfg.get("mode") != "region":
                self.cfg["mode"] = "region"
                self._apply_mode()
            self.selecting = True
            self.pipeline.paused.set()
            RegionSelector(self.root, self._region_done)
        elif action == "move":
            self.overlay.toggle_move()
        elif action == "pause":
            target = self.auto if self.cfg.get("mode", "auto") == "auto" else self.pipeline
            if target.paused.is_set():
                target.paused.clear()
                self.overlay.show_message("Terjemahan dilanjutkan")
            else:
                target.paused.set()
                if target is self.auto:
                    self.auto.reset()
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

    img = Image.open(path).convert("RGB")
    if cfg.get("mode", "auto") == "auto":
        ap = AutoPipeline(cfg, WindowsOcr(cfg["ocr_lang"], cfg["auto_ocr_scale"], cfg["ocr_invert"]),
                          translator, queue.Queue())
        ap.process(img)                      # pembacaan 1 (menunggu teks stabil)
        res = ap.process(img) or []          # pembacaan 2
        print(f"Mode otomatis: {len(res)} kalimat")
        for s in res:
            print(f"  {tuple(int(v) for v in s.bbox)} {s.original}\n    -> {s.translated}")
        snap = AutoPipeline(cfg, ap.ocr, translator, queue.Queue()).process(img, snapshot=True) or []
        print(f"Snapshot: {len(snap)} teks")
        for s in snap:
            print(f"  {s.original}  ->  {s.translated}")
        return
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
