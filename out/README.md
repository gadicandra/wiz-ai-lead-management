# `out/` — Artefak hasil pipeline

Semuanya **di-generate**, bukan ditulis tangan. Regenerate dengan:

```bash
python src/clean_leads.py     # artefak teks
python src/load_db.py         # leads.db (butuh dua file di atas)
```

Artefak teks di-commit supaya hasilnya bisa dilihat tanpa menjalankan apa pun.

| File | Isi | Di-commit? |
|---|---|---|
| `leads_clean.csv` | 2.049 baris ternormalisasi + kolom turunan | ya |
| `dedupe_groups.json` | 232 grup duplikat dengan bukti & usulan master | ya |
| `dedupe_review.csv` | 17 pasangan yang butuh mata manusia | ya |
| `report.json` | seluruh metrik, agar setiap angka di dokumentasi bisa diverifikasi | ya |
| `leads.db` | SQLite yang dibaca API — 4 tabel, 11 index | **tidak** |

`leads.db` di-gitignore: 2 MB biner yang lahir **sepenuhnya** dari dua file di atasnya,
dan `load_db.py` membangunnya ulang dari nol dalam hitungan detik (ia menghapus DB lama
beserta `-wal`/`-shm`, jadi tidak ada state yang menumpuk). Meng-commit-nya hanya
menambah diff biner yang tidak bisa direview.

## ⚠️ `leads_clean.csv` masih mengandung duplikat

Ini **disengaja**. Pipeline bersifat non-destruktif: 2.049 baris masuk, 2.049 baris
keluar. Duplikat *ditandai*, bukan dihapus — karena 95 grup (41%) punya field yang
saling melengkapi, jadi menghapus baris yang salah akan membuang data yang benar.

Untuk daftar mana yang duplikat, pakai `dedupe_groups.json`.

Kolom turunan yang ditambahkan:

| Kolom | Isi |
|---|---|
| `display_name` · `name_source` | nama gabungan + asal bentuknya (jejak audit) |
| `company_display` · `company_core` | versi tampil (konservatif) & versi match (agresif) |
| `phone_e164` | telepon bentuk E.164 |
| `source_channel` · `source_detail` · `source_confidence` · `source_needs_llm` | hasil ekstraksi dari `Notes` |
| `flagged_in_notes` | apakah `Notes` mengandung `"possible duplicate"` |

## `dedupe_groups.json`

Satu entri per grup:

| Field | Isi |
|---|---|
| `group_id` · `size` · `group_confidence` | `group_confidence` diambil dari pasangan internal **terlemah** — grup hanya sekuat sambungan terlemahnya |
| `suggested_master_record_id` | usulan record utama |
| `members[]` | seluruh anggota dengan field kuncinya |
| `evidence[]` | per pasangan: confidence, kalimat `why`, dan sinyal mentahnya |
| `conflicts` | **field yang nilainya berbeda antar anggota** — supaya reviewer lihat apa yang dipertaruhkan sebelum menyetujui |
| `merged_preview` | golden record: yang terbaik per field, siap di-`POST` begitu disetujui |

## `dedupe_review.csv`

Dirancang untuk dibuka di spreadsheet: kedua record bersebelahan kolom demi kolom
(`name_a`/`name_b`, `company_a`/`company_b`, …) plus kalimat `why`. Semuanya di
rentang confidence 0,45–0,90 — kelas kasus yang tidak bisa diputuskan dari data yang
ada, karena informasinya memang tidak ada di sana.

Penjelasan lengkap: [`../docs/ANALISIS-DATA.md`](../docs/ANALISIS-DATA.md)
