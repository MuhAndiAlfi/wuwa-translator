# WuWa Translator

Overlay terjemahan **Inggris → Indonesia** untuk Wuthering Waves. Cara kerjanya hanya dengan membaca layar:
screenshot area dialog → OCR bawaan Windows → DeepL → teks ditampilkan di jendela transparan di atas game.

Game tidak disentuh sama sekali (tidak ada inject, hook memori, atau modifikasi file), jadi aman dari anti-cheat.

## Persiapan (sekali saja)

1. **API key DeepL Free**: daftar di https://www.deepl.com/pro-api (pilih *DeepL API Free*, 500.000 karakter/bulan gratis;
   biasanya perlu kartu untuk verifikasi, tapi tidak ditagih). Salin *Authentication Key* (berakhiran `:fx`).
2. Buka `config.json` dan isi `"deepl_auth_key": "xxxxxxxx:fx"`.
3. Di game: **Settings → Graphics → Display Mode = Borderless/Windowed** (overlay tidak bisa tampil di atas fullscreen eksklusif),
   dan **bahasa teks = English**.
4. Pastikan Windows punya bahasa *English (United States)* (Settings → Time & language → Language & region). Biasanya sudah ada.

## Pemakaian

Jalankan `run.bat` (pertama kali akan memasang dependensi otomatis), lalu buka game.

| Hotkey | Fungsi |
|---|---|
| `Ctrl+Alt+R` | Pilih area dialog: seret kotak mencakup **nama pembicara + teks dialog** |
| `Ctrl+Alt+M` | Mode geser overlay (seret, tekan lagi untuk menyimpan posisi) |
| `Ctrl+Alt+T` | Sembunyikan / tampilkan overlay |
| `Ctrl+Alt+O` | Tampilkan / sembunyikan teks asli bahasa Inggris |
| `Ctrl+Alt+P` | Jeda / lanjutkan terjemahan |
| `Ctrl+Alt+Q` | Keluar |

Secara default overlay muncul tepat **di atas** kotak dialog. Hotkey bisa diubah di `config.json`.

Uji tanpa game atau tanpa kuota:
```
.venv\Scripts\python -m wuwa_translator --mock                       # tanpa DeepL
.venv\Scripts\python -m wuwa_translator --test-image screenshot.png  # uji satu screenshot
```

## Tips

- **Glosarium**: `glossary.txt` berisi istilah yang tidak diterjemahkan (Rover, Echo, Tacet Discord, nama karakter...).
  Tambahkan sendiri; format `Istilah => Pengganti` untuk memaksa terjemahan tertentu.
- **Hemat kuota**: kalimat yang sama tidak diterjemahkan dua kali (disimpan di `translation_cache.json`).
  Kalimat sebelumnya dikirim sebagai konteks ke DeepL, dan itu tidak dihitung ke kuota.
- **OCR kurang akurat?** Di `config.json`: naikkan `ocr_scale` (misal 3.0), atau coba `ocr_invert: true`.
  Buat area sesempit mungkin, cuma teks dialog, tanpa ikon atau tombol.
- **Terlalu lambat atau terlalu cepat?** `interval_ms` = jeda baca layar, `stable_reads` = berapa kali teks harus sama
  sebelum diterjemahkan (menunggu efek mengetik selesai).
- Kalau game dijalankan sebagai Administrator dan overlay/hotkey tidak bekerja, jalankan `run.bat` sebagai Administrator juga.
