"""Terjemahan via DeepL, dengan glosarium istilah game dan cache supaya hemat kuota."""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path


class Glossary:
    """Format glossary.txt (satu per baris, '#' = komentar):
         Rover              -> dibiarkan apa adanya
         Echo => Echo       -> sama
         Shell Credit => Shell Credit
         Resonance Liberation => Resonance Liberation
         sweetheart => sayang   -> dipaksa diterjemahkan jadi 'sayang'
    """

    def __init__(self, path: Path | None):
        self.entries: dict[str, str] = {}
        if path and path.exists():
            for raw in path.read_text(encoding="utf-8").splitlines():
                line = raw.split("#", 1)[0].strip()
                if not line:
                    continue
                if "=>" in line:
                    src, dst = (p.strip() for p in line.split("=>", 1))
                else:
                    src = dst = line
                if src:
                    self.entries[src] = dst
        terms = sorted(self.entries, key=len, reverse=True)
        self._pattern = (
            re.compile(r"(?<![\w])(" + "|".join(re.escape(t) for t in terms) + r")(?![\w])") if terms else None
        )

    def protect(self, text: str) -> str:
        """Bungkus istilah dengan <k>..</k> supaya DeepL tidak menerjemahkannya."""
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if not self._pattern:
            return text
        return self._pattern.sub(lambda m: f"<k>{self.entries[m.group(1)]}</k>", text)

    @staticmethod
    def restore(text: str) -> str:
        text = re.sub(r"</?k>", "", text)
        return text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


class DeepLTranslator:
    def __init__(self, auth_key: str, glossary: Glossary, cache_path: Path,
                 source_lang: str = "EN", target_lang: str = "ID"):
        import deepl

        self._deepl = deepl
        self.client = deepl.DeepLClient(auth_key)
        self.glossary = glossary
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.cache_path = cache_path
        self._lock = threading.Lock()
        try:
            self.cache: dict[str, str] = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.cache = {}

    def usage_text(self) -> str:
        u = self.client.get_usage()
        if u.character.valid:
            return f"Kuota DeepL: {u.character.count:,} / {u.character.limit:,} karakter bulan ini"
        return "Kuota DeepL: tidak diketahui"

    def translate(self, text: str, context: str | None = None) -> str:
        key = f"{self.source_lang}>{self.target_lang}|{text}"
        with self._lock:
            if key in self.cache:
                return self.cache[key]
        result = self.client.translate_text(
            self.glossary.protect(text),
            source_lang=self.source_lang,
            target_lang=self.target_lang,
            tag_handling="xml",
            ignore_tags=["k"],
            split_sentences="nonewlines",
            preserve_formatting=True,
            context=context or None,  # konteks tidak dihitung ke kuota
        )
        out = Glossary.restore(result.text)
        with self._lock:
            self.cache[key] = out
            tmp = self.cache_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.cache, ensure_ascii=False, indent=0), encoding="utf-8")
            tmp.replace(self.cache_path)
        return out


class MockTranslator:
    """Untuk uji coba tanpa API key."""

    def __init__(self, glossary: Glossary):
        self.glossary = glossary

    def usage_text(self) -> str:
        return "Mode mock: tidak memakai DeepL"

    def translate(self, text: str, context: str | None = None) -> str:
        return "[ID] " + Glossary.restore(self.glossary.protect(text))
