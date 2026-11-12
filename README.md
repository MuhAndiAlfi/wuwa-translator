# WuWa Translator

Overlay terjemahan **Inggris → Indonesia** untuk Wuthering Waves. Cara kerjanya hanya dengan membaca layar:
screenshot area dialog → OCR bawaan Windows → DeepL → teks ditampilkan di jendela transparan di atas game.

Game tidak disentuh sama sekali (tidak ada inject, hook memori, atau modifikasi file), jadi aman dari anti-cheat.

## Persiapan (sekali saja)

1. **API key DeepL Free**: daftar di https://www.deepl.com/pro-api (pilih *DeepL API Free*, 500.000 karakter/bulan gratis;
   biasanya perlu kartu untuk verifikasi, tapi tidak ditagih). Salin *Authentication Key* (berakhiran `:fx`).
2. Salin `config.example.json` menjadi `config.json`, lalu isi `"deepl_auth_key": "xxxxxxxx:fx"`.
   (`config.json` tidak ikut ter-commit, jadi key-mu aman. Kalau file ini belum ada, program akan membuatnya otomatis saat pertama jalan.)
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

## Isi `config.json`

| Kunci | Default | Arti |
|---|---|---|
| `deepl_auth_key` | `""` | API key DeepL (atau pakai environment variable `DEEPL_AUTH_KEY`) |
| `source_lang` / `target_lang` | `EN` / `ID` | Bahasa asal dan tujuan DeepL |
| `region` | `null` | Area dialog yang dibaca; diisi otomatis lewat `Ctrl+Alt+R` |
| `overlay_pos` | `null` | Posisi overlay `[x, y]`; diisi lewat `Ctrl+Alt+M`. `null` = tepat di atas area dialog |
| `overlay_width` | `null` | Lebar overlay dalam piksel; `null` = sama dengan lebar area dialog |
| `font_family` / `font_size` | `Segoe UI` / `16` | Font teks terjemahan |
| `show_original` | `false` | Tampilkan juga teks Inggris aslinya (`Ctrl+Alt+O`) |
| `opacity` | `0.86` | Transparansi overlay (0–1) |
| `detect_speaker` | `true` | Baris pertama yang pendek dianggap nama pembicara dan tidak diterjemahkan |
| `interval_ms` | `350` | Jeda antar-pembacaan layar |
| `stable_reads` | `2` | Berapa kali teks harus sama sebelum diterjemahkan |
| `clear_after_empty_reads` | `4` | Overlay hilang setelah sekian kali pembacaan tidak menemukan teks |
| `ocr_lang` | `en-US` | Bahasa OCR Windows (harus terpasang di Windows) |
| `ocr_scale` | `2.0` | Pembesaran gambar sebelum OCR; naikkan kalau teks kecil |
| `ocr_invert` | `false` | Balik warna sebelum OCR; coba kalau hasil OCR jelek |
| `hotkeys` | lihat tabel di atas | Kombinasi `Ctrl`/`Alt`/`Shift` + huruf, angka, atau `F1`–`F12` |

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
