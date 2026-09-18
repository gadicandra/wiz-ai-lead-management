# `src/` — Pipeline + REST API

| File | Isi |
|---|---|
| `clean_leads.py` | Pipeline offline: normalisasi → ekstraksi sumber → dedup → survivorship |
| `db.py` | Skema SQLite (4 tabel, 11 index), helper baca/tulis, konversi row ↔ dict |
| `matching.py` | Dedup **online**: cari kandidat lewat index, skor, enrich |
| `load_db.py` | Muat hasil pipeline ke `out/leads.db` — idempoten, bangun ulang dari nol |
| `schemas.py` | Model Pydantic di batas API (validasi masuk & bentuk keluar) |
| `api.py` | FastAPI — 9 route |
| `static/dashboard.html` | Dashboard, tanpa build step |

## Jalankan

```bash
conda activate WIZ.AI
python src/clean_leads.py                            # 1. pipeline → out/
python src/load_db.py                                # 2. out/ → out/leads.db
uvicorn api:app --app-dir src --reload --port 8000   # 3. API + /docs + dashboard
```

## Pembagian tanggung jawab

```
clean_leads.py     ← satu-satunya sumber kebenaran untuk normalisasi & skor
      │
      ├─ load()            batch: seluruh CSV
      └─ build_record()    satu record — dipakai ulang oleh API
                │
      matching.py ─────────┴─ find_candidates() lewat index, bukan full scan
                │
      api.py ────┴─ HTTP, validasi, keputusan create/merge
```

`score_pair`, `explain`, `MERGE_T`, dan `REVIEW_T` **di-import** dari `clean_leads`,
tidak disalin. Kalau ambangnya berubah, ia berubah di kedua jalur sekaligus —
pipeline offline dan endpoint ingest tidak bisa diam-diam berbeda pendapat.

Alasan yang sama berlaku untuk `build_record()`: kalau ingest menormalisasi email atau
telepon sedikit saja berbeda dari pipeline, kunci blocking-nya meleset dan dedup online
gagal menemukan duplikat yang sebenarnya ada — kegagalan yang **senyap**, karena
hasilnya tetap berupa lead baru yang tampak wajar.

## Alur — 4 tahap, satu arah

```
data/leads_seed.csv
   │
   ├─ 1. NORMALISASI      nama · email · telepon · perusahaan · tanggal · enum
   ├─ 2. EKSTRAKSI SUMBER Notes → {channel, detail, confidence, needs_llm_review}
   ├─ 3. DEDUP            blocking → scoring → union-find
   └─ 4. SURVIVORSHIP     usulan master + golden record + daftar konflik
   │
   ▼  out/
```

Tiap tahap hanya bergantung pada output tahap sebelumnya. Efeknya: bisa dites per
tahap, bisa dijalankan ulang dari titik mana pun, dan tahap 1–3 bisa dipakai ulang
untuk **satu** record di jalur `POST /leads/ingest` tanpa memuat seluruh dataset.

## Peta fungsi

**Normalisasi** — tiap entitas punya dua representasi: bentuk asli untuk ditampilkan,
bentuk kanonik untuk dicocokkan. Yang satu tidak pernah menimpa yang lain.

| Fungsi | Tugas |
|---|---|
| `norm_status` · `norm_lifecycle` · `norm_country` | enum → bentuk kanonik; **nilai asing dipertahankan**, tidak dipaksa jadi `Other` |
| `norm_date` | 3 format → ISO-8601 UTC |
| `norm_email` / `email_key` | `email_key` buang titik/dash/underscore + plus-tag dari localpart |
| `phone_e164` / `phone_key` | `phone_key` = **9 digit terakhir**, tahan selisih prefix kode negara |
| `company_display` / `company_core` | `display` konservatif (rapikan artefak), `core` agresif (kupas suffix **berulang** sampai stabil) |
| `split_name` | gabung `First`+`Last` dan `Full Name` → `display_name` + flag `is_initial` |

**Ekstraksi sumber** — rules-first, LLM hanya untuk sisa yang ambigu.

| Bagian | Tugas |
|---|---|
| `CHANNEL_RULES` | 7 channel, **dievaluasi berurutan** — semakin spesifik channel-nya, semakin tinggi prioritasnya |
| `PAID_HINT` | override: `"google ad"` → `Website`, bukan Organic Search |
| `extract_source` | → `{channel, detail, confidence, needs_llm_review}` |

`needs_llm_review = True` menandai teks yang tidak tertangkap rule — **sistem tidak
menebak.** Di dataset ini: 162 baris (7,9%).

**Dedup**

| Fungsi | Tugas |
|---|---|
| `build_blocks` | 4 kunci blocking; pasangan dari **union** semua blok |
| `candidate_pairs` | 2.098.176 pasangan → **513** (reduksi 99,98%) |
| `score_pair` | skor berbobot + **dua Aturan Keras** |
| `explain` | ubah skor jadi kalimat yang bisa dibaca reviewer |
| `DSU` | union-find untuk klaster transitif (A≈B, B≈C → satu grup) |

Dua Aturan Keras — keduanya lahir dari kegagalan kalibrasi nyata, bukan desain awal:

```python
if identity <  0.95:                    conf = min(conf, 0.45)  # tanpa email/telepon → review, bukan merge
if identity >= 0.95 and person < 0.55:  conf = min(conf, 0.55)  # telepon kantor bersama ≠ orang sama
```

**Survivorship**

| Fungsi | Tugas |
|---|---|
| `pick_master` | kelengkapan → kualitas nama → recency → Record ID terkecil |
| `merged_view` | golden record: yang terbaik **per field**, bukan menyalin master |

## Lapisan penyimpanan & API

**`db.py`** — 4 tabel: `leads`, `dedupe_groups`, `dedupe_members`, `lead_events`.

11 index, dua kelompok dengan alasan berbeda:

| Index | Untuk |
|---|---|
| `status` · `owner` · `country` · `channel` | filter `GET /leads` |
| `phone_key` · `email_key` · `email` · `(domain_root, last)` | **kunci blocking** — supaya ingest jadi 4 lookup, bukan 2.049 perbandingan |

`phone_key` dan `email_key` disimpan sebagai **kolom**, bukan dihitung saat query:
keduanya tidak bisa ditulis sebagai ekspresi SQL yang bisa di-index, jadi harus
dimaterialisasi saat tulis.

**`matching.py`**

| Fungsi | Tugas |
|---|---|
| `find_candidates` | union dari 4 lookup ber-index, buang diri sendiri |
| `decide` | confidence → `merge` / `review` / `distinct` |
| `enrich` | isi field yang **kosong** di lead lama dari payload baru — tidak pernah menimpa; `notes` di-append |

**`api.py`** — catatan urutan route: `/leads/export` dideklarasikan **sebelum**
`/leads/{record_id}`, kalau tidak `export` akan ditelan sebagai `record_id`. Ada
test-nya (`test_export_route_is_not_shadowed_by_the_id_route`) supaya urutan itu tidak
bisa tertukar tanpa ketahuan.

`PATCHABLE` membatasi `PATCH` ke 3 field (`lead_status`, `contact_owner`, `notes`).
Field lain ditolak, bukan diabaikan diam-diam — mengizinkan `PATCH` pada `email` atau
`phone` berarti mengizinkan kunci blocking berubah tanpa menghitung ulang dedup.

## Konstanta yang bisa disetel

```python
MERGE_T, REVIEW_T = 0.90, 0.45   # ambang merge & zona review manusia
BLOCK_MAX = 50                   # pengaman block explosion
```

Ambang 0,90 tidak sensitif di data ini — sapu 0,70–0,95 menghasilkan clustering
**identik**.

Alasan lengkap setiap keputusan: [`../docs/ANALISIS-DATA.md`](../docs/ANALISIS-DATA.md)
