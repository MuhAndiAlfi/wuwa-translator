# WuWa Translator

Overlay terjemahan **Inggris → Indonesia** untuk Wuthering Waves. Program ini hanya membaca layar:
screenshot → OCR bawaan Windows (CPU) → DeepL → terjemahan ditempel **tepat di atas teks aslinya**.

Game tidak disentuh sama sekali (tidak ada inject, hook memori, atau modifikasi file), jadi aman dari anti-cheat.
OCR berjalan di CPU (±80 ms per layar penuh), jadi **GPU tetap sepenuhnya untuk game** (DLSS / Frame Generation aman).

## Pasang di PC baru (sekali saja)

1. Pasang **Git** dan **Python 3.10–3.13** (centang "Add Python to PATH").
2. Clone lalu jalankan:
   ```
   git clone https://github.com/MuhAndiAlfi/wuwa-translator.git
   cd wuwa-translator
   run.bat
   ```
   `run.bat` memasang semua yang dibutuhkan pada jalan pertama.
3. Saat pertama jalan, program **menanyakan API key DeepL** di jendela kecil, mengeceknya, lalu menyimpannya di
   `config.json` di PC itu **dalam bentuk terenkripsi** (Windows DPAPI: cuma bisa dibuka akun Windows-mu di PC itu;
   file ini juga tidak ikut ke GitHub). Daftar gratis di https://www.deepl.com/pro-api
   (*DeepL API Free*, 500.000 karakter/bulan; key berakhiran `:fx`).
4. Di game: **Settings → Graphics → Display Mode = Borderless/Windowed** (overlay tidak bisa tampil di atas fullscreen
   eksklusif) dan **bahasa teks = English**.
5. Windows harus punya bahasa *English (United States)* (Settings → Time & language → Language & region). Biasanya sudah ada.

Update ke versi terbaru: `git pull` di folder itu.

## Mode

**Otomatis (default):** seluruh layar dibaca terus. Teks yang berbentuk kalimat (dialog, pilihan jawaban, tutorial,
quest) diterjemahkan dan ditempel di posisinya. Nama pembicara, HUD, angka, dan label pendek dibiarkan.
Program menunggu efek mengetik selesai, dan kalimat yang sama tidak diterjemahkan dua kali.

**Snapshot (`Ctrl+Alt+S`):** semua teks di layar diterjemahkan sekali, termasuk label pendek. Cocok untuk menu,
deskripsi item/Echo, dan layar quest. Tekan lagi untuk kembali.

**Area (`Ctrl+Alt+A` untuk ganti mode):** mode lama. Hanya area yang kamu pilih (`Ctrl+Alt+R`) yang dibaca,
dan terjemahannya tampil di kotak terpisah.

| Hotkey | Fungsi |
|---|---|
| `Ctrl+Alt+S` | Snapshot: terjemahkan semua teks di layar / tutup snapshot |
| `Ctrl+Alt+A` | Ganti mode Otomatis ↔ Area |
| `Ctrl+Alt+T` | Sembunyikan / tampilkan terjemahan |
| `Ctrl+Alt+P` | Jeda / lanjutkan |
| `Ctrl+Alt+R` | (Mode Area) pilih area dialog |
| `Ctrl+Alt+M` | (Mode Area) geser kotak terjemahan |
| `Ctrl+Alt+O` | (Mode Area) tampilkan teks asli juga |
| `Ctrl+Alt+Q` | Keluar |

Uji tanpa game atau tanpa kuota:
```
.venv\Scripts\python -m wuwa_translator --mock                       # tanpa DeepL
.venv\Scripts\python -m wuwa_translator --test-image screenshot.png  # uji satu screenshot (tanpa jendela)
```

## Isi `config.json`

| Kunci | Default | Arti |
|---|---|---|
| `deepl_auth_key_protected` | `""` | API key DeepL terenkripsi (DPAPI). Diisi otomatis saat pertama jalan; jangan diedit manual. Hapus isinya untuk mengganti key |
| `deepl_auth_key` | `""` | Lama (teks biasa). Kalau diisi, otomatis dipindah ke versi terenkripsi lalu dikosongkan |
| `mode` | `auto` | `auto` = seluruh layar, `region` = hanya area pilihan |
| `monitor` | `1` | Monitor tempat game (1 = utama, 2 = kedua, ...) |
| `auto_interval_ms` | `400` | Jeda antar-pembacaan layar di mode otomatis |
| `auto_opacity` | `0.94` | Transparansi kotak terjemahan di mode otomatis |
| `auto_ocr_scale` | `1.0` | Pembesaran sebelum OCR di mode otomatis; naikkan ke 1.5 kalau teks game kecil (resolusi rendah) |
| `source_lang` / `target_lang` | `EN` / `ID` | Bahasa asal dan tujuan DeepL |
| `region` | `null` | (Mode Area) area dialog; diisi lewat `Ctrl+Alt+R` |
| `overlay_pos` / `overlay_width` | `null` | (Mode Area) posisi & lebar kotak terjemahan |
| `font_family` / `font_size` | `Segoe UI` / `16` | Font terjemahan (ukuran di mode otomatis mengikuti teks game) |
| `show_original` | `false` | (Mode Area) tampilkan juga teks Inggris aslinya |
| `opacity` | `0.86` | (Mode Area) transparansi kotak |
| `detect_speaker` | `true` | (Mode Area) baris pertama pendek = nama pembicara |
| `interval_ms` / `stable_reads` / `clear_after_empty_reads` | `350` / `2` / `4` | (Mode Area) kecepatan baca & kestabilan |
| `ocr_lang` | `en-US` | Bahasa OCR Windows |
| `ocr_scale` / `ocr_invert` | `2.0` / `false` | (Mode Area) pembesaran & balik warna sebelum OCR |
| `hotkeys` | lihat tabel | Kombinasi `Ctrl`/`Alt`/`Shift` + huruf, angka, atau `F1`–`F12` |

## Tips

- **Glosarium**: `glossary.txt` berisi istilah yang tidak diterjemahkan (Rover, Echo, Tacet Discord, nama karakter...).
  Tambahkan sendiri; format `Istilah => Pengganti` untuk memaksa terjemahan tertentu.
- **Hemat kuota**: kalimat yang sama tidak diterjemahkan dua kali (disimpan di `translation_cache.json`).
  Semua kalimat di layar dikirim sebagai konteks ke DeepL, dan itu tidak dihitung ke kuota.
- **Ada teks game yang tidak ikut diterjemahkan?** Mode otomatis hanya menerjemahkan kalimat (minimal 3 kata).
  Untuk label atau menu, pakai Snapshot (`Ctrl+Alt+S`).
- Kalau game dijalankan sebagai Administrator dan overlay/hotkey tidak bekerja, jalankan `run.bat` sebagai Administrator juga.
