"""OCR lewat Windows.Media.Ocr (bawaan Windows 10/11, offline, gratis)."""
from __future__ import annotations

import asyncio

from PIL import Image, ImageOps
from winrt.windows.globalization import Language
from winrt.windows.graphics.imaging import BitmapAlphaMode, BitmapPixelFormat, SoftwareBitmap
from winrt.windows.media.ocr import OcrEngine
from winrt.windows.storage.streams import DataWriter


class OcrError(RuntimeError):
    pass


class WindowsOcr:
    def __init__(self, lang: str = "en-US", scale: float = 2.0, invert: bool = False):
        language = Language(lang)
        if not OcrEngine.is_language_supported(language):
            raise OcrError(
                f"Bahasa OCR '{lang}' belum terpasang di Windows. Buka Settings > Time & language > "
                "Language & region > tambahkan English (United States)."
            )
        self.engine = OcrEngine.try_create_from_language(language)
        self.scale = scale
        self.invert = invert
        self._loop = asyncio.new_event_loop()

    def preprocess(self, img: Image.Image) -> Image.Image:
        img = img.convert("L")
        if self.scale and self.scale != 1.0:
            img = img.resize((int(img.width * self.scale), int(img.height * self.scale)), Image.LANCZOS)
        if self.invert:
            img = ImageOps.invert(img)
        img = ImageOps.autocontrast(img)
        # Batas ukuran gambar OCR Windows
        limit = OcrEngine.max_image_dimension
        if img.width > limit or img.height > limit:
            img.thumbnail((limit, limit))
        return img

    def _to_bitmap(self, img: Image.Image) -> SoftwareBitmap:
        bgra = img.convert("RGB").convert("RGBA")
        r, g, b, a = bgra.split()
        raw = Image.merge("RGBA", (b, g, r, a)).tobytes()
        writer = DataWriter()
        writer.write_bytes(raw)
        return SoftwareBitmap.create_copy_with_alpha_from_buffer(
            writer.detach_buffer(), BitmapPixelFormat.BGRA8, bgra.width, bgra.height, BitmapAlphaMode.PREMULTIPLIED
        )

    def read_lines(self, img: Image.Image) -> list[str]:
        bitmap = self._to_bitmap(self.preprocess(img))
        result = self._loop.run_until_complete(self._recognize(bitmap))
        return [line.text for line in result.lines]

    def read_line_boxes(self, img: Image.Image) -> list[tuple[str, float, float, float, float]]:
        """Baris teks + posisinya (x1, y1, x2, y2) dalam koordinat gambar asli."""
        pre = self.preprocess(img)
        sx, sy = img.width / pre.width, img.height / pre.height
        result = self._loop.run_until_complete(self._recognize(self._to_bitmap(pre)))
        out = []
        for line in result.lines:
            rects = [w.bounding_rect for w in line.words]
            if not rects:
                continue
            x1 = min(r.x for r in rects) * sx
            y1 = min(r.y for r in rects) * sy
            x2 = max(r.x + r.width for r in rects) * sx
            y2 = max(r.y + r.height for r in rects) * sy
            out.append((line.text, x1, y1, x2, y2))
        return out

    async def _recognize(self, bitmap):
        return await self.engine.recognize_async(bitmap)
