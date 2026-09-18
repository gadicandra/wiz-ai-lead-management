# `analysis/` — Script eksplorasi (sekali pakai)

Jejak kerja menuju `src/clean_leads.py`. **Bukan bagian dari pipeline** — tidak
di-import siapa pun, dan tidak perlu dijalankan untuk mereproduksi hasil.

Disimpan bukan untuk dipakai lagi, tapi sebagai bukti bahwa angka-angka di
dokumentasi berasal dari pemeriksaan nyata, bukan dari asumsi. Beberapa di antaranya
adalah **kalibrasi yang gagal**, dan justru itu yang membentuk desain akhirnya.

| Script | Yang diperiksa |
|---|---|
| `01_profile.py` | fill rate & kardinalitas 22 kolom |
| `02_values.py` | distribusi nilai per kolom kategorikal |
| `03_formats.py` | sensus format tanggal, email, telepon |
| `04_dupes.py` | probe awal: email & telepon persis sama |
| `05_notes_company.py` | struktur `Notes`, artefak nama perusahaan |
| `06_misc.py` | crosstab `Lead Status` × `Lifecycle Stage` → **terbukti tidak berkorelasi** |
| `07_dedupe_probe.py` | eksperimen kunci blocking |
| `08_calibrate.py` | **kalibrasi #1 — gagal**: hanya 58 grup, 33/136 baris bertanda tertangkap |
| `09_negatives.py` | cari false positive → menemukan `Rania`/`Hana Andersen` skor 0,791 |
| `10_final_score.py` | fungsi skor final + dua Aturan Keras |
| `11_recall_conflict.py` | uji recall brute-force vs hasil clustering |
| `12_verify_conflicts.py` | konflik per field di dalam grup |
| `13_debug.py` · `14_conflict2.py` | inspeksi kasus spesifik |
| `15_json.py` | struktur JSON + overlap dengan seed |
| `16_extra.py` | sapuan ambang 0,70–0,95 → **clustering identik** |

`out*.txt` adalah output yang ditangkap dari script bernomor sama (beberapa script
punya stdout panjang yang lebih mudah dibaca dari file).

`*.pkl` adalah cache DataFrame — di-`gitignore` karena regenerable dan bukan sumber
kebenaran.

## Temuan mana yang berasal dari sini

| Temuan | Script |
|---|---|
| `M/D/YYYY` terbukti US-order (komponen pertama maks 12, kedua sampai 31) | `03` |
| `Record ID` **tidak** duplikat — 2.049 unik | `01` |
| Seluruh 107 baris `Full Name` ada di dalam grup duplikat | `04`, `11` |
| `Lead Status` × `Lifecycle Stage` tidak berkorelasi → tidak ada aturan repair yang layak | `06` |
| Bobot email persis 0,30 terlalu dominan → restrukturisasi jadi identity/person/org | `08` |
| Nama + perusahaan bisa menumpuk ke 0,791 tanpa bukti identitas → **Aturan Keras #1** | `09` |
| 49 dari 90 entri JSON sudah ada di seed | `15` |
| Ambang 0,90 tidak sensitif | `16` |

Semua angka ini sudah dirangkum di [`../docs/ANALISIS-DATA.md`](../docs/ANALISIS-DATA.md) —
script di sini hanya rujukan kalau ada yang ingin memeriksa ulang.

## File `out*.txt`

Enam file `outNN.txt` adalah **stdout yang dibekukan** dari script bernomor sama
(`out09.txt` ← `09_negatives.py`, dst). Sengaja ikut di-commit, bukan di-gitignore:
sebagian di antaranya adalah bukti mentah di balik angka yang dikutip di dokumentasi,
dan beberapa script bergantung pada state eksplorasi saat itu sehingga tidak dijamin
menghasilkan output identik kalau dijalankan ulang sekarang.

Kalau butuh angka yang dijamin bisa direproduksi, sumbernya adalah
[`../out/report.json`](../out/report.json) — itu di-generate ulang setiap kali
`src/clean_leads.py` dijalankan.
