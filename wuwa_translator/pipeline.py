"""Capture layar -> OCR -> deteksi teks stabil -> terjemah. Jalan di thread terpisah."""
from __future__ import annotations

import hashlib
import queue
import re
import threading
import time
from dataclasses import dataclass

import mss
from PIL import Image

_TERMINAL = tuple(".!?…,:;\"'”’)—-~")


@dataclass
class Dialog:
    speaker: str
    original: str
    translated: str


def split_speaker(lines: list[str], enabled: bool) -> tuple[str, str]:
    """Baris pertama yang pendek & tanpa tanda baca di akhir dianggap nama pembicara."""
    lines = [l.strip() for l in lines if l.strip()]
    if enabled and len(lines) >= 2:
        first = lines[0]
        if len(first) <= 28 and len(first.split()) <= 4 and not first.endswith(_TERMINAL):
            return first, " ".join(lines[1:])
    return "", " ".join(lines)


def normalize(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    # Hilangkan noise OCR umum (ikon panah "lanjut", dsb) di ujung kalimat
    return re.sub(r"\s*[▼▶>»•·]+$", "", text)


def worth_translating(text: str) -> bool:
    return sum(c.isalpha() for c in text) >= 3


class Pipeline(threading.Thread):
    def __init__(self, cfg: dict, ocr, translator, out: queue.Queue):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.ocr = ocr
        self.translator = translator
        self.out = out
        self.paused = threading.Event()
        self.stopped = threading.Event()
        self.reset()

    def reset(self):
        self._last_hash = None
        self._candidate = None
        self._candidate_count = 0
        self._shown = None
        self._empty_count = 0
        self._prev_original = ""

    def process_image(self, img: Image.Image) -> Dialog | None | str:
        """Satu langkah. Return Dialog baru, 'clear' bila dialog hilang, atau None bila tidak ada perubahan."""
        digest = hashlib.blake2b(img.convert("L").resize((96, 24)).tobytes(), digest_size=8).digest()
        if digest == self._last_hash:
            return None
        lines = self.ocr.read_lines(img)
        speaker, text = split_speaker(lines, self.cfg.get("detect_speaker", True))
        text = normalize(text)

        if not worth_translating(text):
            self._last_hash = digest
            self._candidate = None
            self._empty_count += 1
            if self._shown and self._empty_count >= self.cfg.get("clear_after_empty_reads", 4):
                self._shown = None
                return "clear"
            return None
        self._empty_count = 0

        # Tunggu teks berhenti berubah (efek mengetik di kotak dialog)
        if text != self._candidate:
            self._candidate, self._candidate_count = text, 1
        else:
            self._candidate_count += 1
        if self._candidate_count < self.cfg.get("stable_reads", 2):
            return None
        self._last_hash = digest
        if text == self._shown:
            return None

        self._shown = text
        try:
            translated = self.translator.translate(text, context=self._prev_original)
        except Exception as e:  # noqa: BLE001 - tampilkan error apa pun di overlay
            translated = f"(Gagal menerjemahkan: {e})"
            self._shown = None
        self._prev_original = text
        return Dialog(speaker, text, translated)

    def run(self):
        interval = self.cfg.get("interval_ms", 350) / 1000
        with mss.mss() as sct:
            while not self.stopped.is_set():
                start = time.perf_counter()
                region = self.cfg.get("region")
                if region and not self.paused.is_set():
                    try:
                        shot = sct.grab(region)
                        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                        result = self.process_image(img)
                        if result is not None:
                            self.out.put(("dialog", result))
                    except Exception as e:  # noqa: BLE001
                        self.out.put(("status", f"Error: {e}"))
                        time.sleep(1)
                time.sleep(max(0.0, interval - (time.perf_counter() - start)))
