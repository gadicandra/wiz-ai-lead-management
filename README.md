# AI-Assisted Mini Lead Management System

Take-home assignment WIZ.AI — **AI Builder (Mid-Level)**.

Backend untuk mengelola dataset leads dari export CRM yang berantakan, dengan dua fitur
berbasis AI: **deduplikasi lead** dan **ekstraksi sumber lead dari teks bebas**.

Spesifikasi asli assignment: [`ASSIGNMENT.md`](ASSIGNMENT.md)

---

## Status deliverable

| # | Deliverable | Status |
|---|---|---|
| 1 | Lead store + API — 5 endpoint wajib | ✅ SQLite + FastAPI, 9 route |
| 2 | Dedup AI-assisted — `POST /leads/dedupe-candidates` | ✅ 232 grup, reduksi pasangan 99,98% |
| 3 | Ekstraksi sumber — `POST /source/extract` | ✅ 92,1% via rules, 7,9% ditandai untuk LLM |
| 4 | Dashboard (bonus) — `GET /dashboard` | ✅ JSON + halaman HTML tanpa build step |
| — | Test | ✅ **70 passed** (28 pipeline + 42 API) |
| — | Dokumentasi temuan & keputusan | ✅ 36 temuan, 18 keputusan, next steps |

---

## Jalankan

Butuh Python 3.12. Versi di-pin di [`requirements.txt`](requirements.txt) — bukan `>=` —
karena skor `rapidfuzz` bisa bergeser antar versi minor dan itu akan mengubah hasil dedup.

```bash
conda env create -f environment.yml   # atau: pip install -r requirements.txt
conda activate WIZ.AI

python src/clean_leads.py             # 1. pipeline: CSV mentah → out/
python src/load_db.py                 # 2. muat hasilnya ke out/leads.db
uvicorn api:app --app-dir src --reload --port 8000   # 3. jalankan API
```

Lalu buka:

| URL | Isi |
|---|---|
| <http://localhost:8000/> | dashboard HTML |
| <http://localhost:8000/docs> | Swagger UI — semua endpoint bisa dicoba langsung |
| <http://localhost:8000/health> | cek DB hidup & terisi |

Test:

```bash
python -m pytest -q          # 70 test
cat out/report.json          # seluruh metrik pipeline
```

Tidak butuh API key — **nol panggilan LLM berbayar** (lihat
[alasannya](#kenapa-rules-dulu-bukan-llm) di bawah).

---

## Endpoint

| Method | Path | Catatan |
|---|---|---|
| `GET` | `/leads` | filter `status`, `owner`, `country`, `channel`, free-text `q` (nama/perusahaan/email), `limit`/`offset` |
| `GET` | `/leads/{id}` | detail + **grup duplikatnya** kalau ada |
| `PATCH` | `/leads/{id}` | hanya `lead_status`, `contact_owner`, `notes` — selain itu ditolak |
| `GET` | `/leads/export` | CSV streaming dari view yang sedang difilter (filter sama persis dengan `GET /leads`) |
| `POST` | `/leads/ingest` | payload sebentuk `website_form_submissions.json` → dedup dulu, baru create/merge |
| `POST` | `/leads/dedupe-candidates` | dua mode: untuk record baru, atau untuk lead yang sudah ada |
| `POST` | `/source/extract` | teks bebas → `{channel, detail, confidence, needs_llm_review}` |
| `GET` | `/dashboard` | hitungan per status, kanal, owner, negara + KPI duplikat |
| `GET` | `/health` | jumlah baris & grup di DB |

### `POST /leads/ingest` — tabel keputusan

Ingest tidak pernah insert buta. Record masuk dinormalisasi lewat fungsi yang **sama
persis** dengan pipeline offline, dicari kandidatnya lewat 4 lookup ber-index, lalu:

| Confidence tertinggi | `action` | Efeknya |
|---:|---|---|
| ≥ 0,90 | `merged` | lead lama diperkaya field-nya, **tidak ada baris baru** |
| ≥ 0,45 | `created_pending_review` | lead baru dibuat **tapi ditandai** kembar dengan yang lama |
| < 0,45 | `created` | lead baru biasa |

Zona review sengaja **membuat**, bukan menahan: pengirim form adalah orang nyata yang
sedang menunggu ditelepon. Menahan lead yang ternyata orang baru lebih mahal daripada
membuat baris yang ternyata kembar — yang kedua bisa di-merge belakangan, yang pertama
hilang jadi peluang.

`?dry_run=true` menjalankan seluruh keputusan tanpa menulis.

---

## Hasil

| Metrik | Nilai |
|---|---|
| Baris masuk | 2.049 |
| Baris keluar | **2.049** — pipeline non-destruktif, 0 dihapus |
| Perkiraan orang unik | **± 1.786** (263 baris redundan, ≈13%) |
| Grup duplikat | **232** (201 pasang + 31 triplet, 0 grup > 3) |
| Butuh review manusia | **17 pasangan** |
| Pasangan dibandingkan | **513** dari 2.098.176 brute-force (**reduksi 99,9756%**) |
| Baris bertanda `"possible duplicate"` tertangkap | **136 / 136** |
| Ekstraksi sumber tanpa LLM | **92,1%** (mean confidence 0,831) |
| Normalisasi | `Lead Status` 35→7 · `Country` 62→35 · `Owner` 20→10 · 0 tanggal gagal parse |
| Query `/leads` terfilter | 0,12 ms/query (100 query = 12 ms) |

### Dedup diuji silang oleh jalur kode yang berbeda

Analisis offline menyimpulkan **49 dari 90** entri JSON sudah ada di seed. Endpoint
ingest menempuh jalur yang sama sekali lain — lookup SQL ber-index, bukan blocking
in-memory — dan sampai ke angka yang sama:

| Jalankan | Hasil | Baris di DB |
|---|---|---|
| 90 payload, kali ke-1 | 49 `merged`, 41 `created` | 2.049 → 2.090 |
| 90 payload yang sama, kali ke-2 | **90 `merged`, 0 baris baru** | 2.090 → **2.090** |

Tanpa dedup, dua kali ingest akan menghasilkan 2.229 baris.

---

## Struktur repo

```
.
├── README.md              ← Anda di sini
├── ASSIGNMENT.md          spesifikasi asli dari penyelenggara
├── ListMasalah.md         hipotesis awal saya sebelum analisis (semuanya sudah diverifikasi)
├── requirements.txt       versi di-pin
├── environment.yml        env conda setara
├── pytest.ini
│
├── data/                  input mentah, read-only
├── src/
│   ├── clean_leads.py     pipeline: normalisasi → ekstraksi sumber → dedup → survivorship
│   ├── db.py              skema SQLite, index, helper baca/tulis
│   ├── matching.py        dedup online: cari kandidat lewat index, skor, enrich
│   ├── load_db.py         muat hasil pipeline ke DB (idempoten)
│   ├── schemas.py         model Pydantic di batas API
│   ├── api.py             FastAPI — 9 route
│   └── static/            dashboard HTML (tanpa build step)
├── tests/                 70 test, fokus pada kasus ambigu
├── out/                   artefak hasil pipeline (di-generate)
├── docs/                  dokumentasi lengkap
└── analysis/              script eksplorasi sekali pakai (jejak kerja)
```

Setiap folder punya `README.md` sendiri yang menjelaskan isinya.

---

## Dokumentasi

**[`docs/ANALISIS-DATA.md`](docs/ANALISIS-DATA.md)** — dokumen utama:

1. **Temuan, Solusi, Justifikasi** — 36 temuan dalam tabel, masing-masing dengan bukti,
   solusi, dan alasan pemilihan solusinya
2. **Keputusan Pemrosesan** — 7 keputusan pipeline + 10 keputusan lapisan API
3. **Keputusan yang Masih Harus Diambil** — yang terbuka, bisnis & teknis
4. **Next Improvement** — berurutan menurut rasio nilai/usaha

---

## Keputusan desain yang paling menentukan

### Non-destruktif: duplikat ditandai, tidak dihapus

2.049 baris masuk, 2.049 baris keluar. Pipeline menghasilkan usulan master + golden
record + daftar konflik, bukan file yang sudah "bersih".

Alasannya bukan kehati-hatian abstrak: **95 grup (41%) punya field yang saling
melengkapi** — satu anggota punya `Last Modified Date`, anggota lain kosong. Menghapus
baris yang salah akan membuang data yang benar. Ditambah biayanya asimetris: merge yang
salah mahal dan sulit dibatalkan, menunda merge murah.

Ini juga yang menjelaskan kenapa **tidak ada `POST /leads/merge`**: assignment memang
tidak memintanya, tapi lebih dari itu — merge butuh keputusan bisnis yang belum diambil
(siapa yang berhak menyetujui, apakah bisa dibatalkan, apa yang terjadi pada aktivitas
milik record yang kalah). Membangun endpoint-nya sekarang berarti menebak jawabannya.

### Identity anchor: nama tidak pernah cukup untuk menyatakan duplikat

Hipotesis awal saya adalah *"nama mirip >80% → duplikat, dengan human-in-the-loop"*.
Data membantahnya **di dua arah sekaligus**:

- **terlalu longgar** — di ambang 80% ada 11 pasangan nama mirip + perusahaan sama
  yang jelas orang berbeda (turunkan ke 60% → 112 pasangan)
- **terlalu ketat** — duplikat asli `J. Yoon` ↔ `Ji-woo Yoon` hanya 63%

Jadi bukan angkanya yang perlu disetel, tapi sinyalnya yang perlu diganti. Yang
menentukan sekarang adalah **email dan nomor telepon**; nama hanya mengonfirmasi:

```python
if identity <  0.95:                    conf = min(conf, 0.45)   # tanpa email/telepon → review
if identity >= 0.95 and person < 0.55:  conf = min(conf, 0.55)   # telepon kantor bersama ≠ orang sama
```

Kedua aturan itu lahir dari kegagalan kalibrasi nyata, bukan desain awal. Gagasan
human-in-the-loop-nya tetap dipakai — dan justru jadi lebih berguna: antrian manusia
turun dari ratusan pasangan menjadi **17**.

Hasilnya pada jebakan yang sengaja ditanam dataset — tiga `Marcus Ho` di perusahaan
yang sama:

| Pasangan | Confidence | Hasil |
|---|---:|---|
| dua nomor telepon & domain identik | 0,987 | duplikat |
| satu lagi, telepon & negara beda | 0,45 | orang berbeda |

### Blocking: 513 pasangan, bukan 2.098.176

Assignment secara eksplisit menolak pendekatan ~2.000². Kandidat dipersempit lewat
**union dari 4 kunci blocking** (9 digit telepon terakhir · localpart email tanpa titik
& plus-tag · email persis · domain + nama belakang), dengan `BLOCK_MAX = 50` sebagai
pengaman block explosion. Baru pasangan yang selamat yang diskor.

Kunci yang sama disimpan sebagai **kolom ber-index** di SQLite. `phone_key` dan
`email_key` tidak bisa ditulis sebagai ekspresi SQL yang bisa di-index, jadi keduanya
dimaterialisasi saat tulis. Efeknya: satu ingest = 4 lookup ber-index, bukan 2.049
perbandingan.

### Kenapa rules dulu, bukan LLM

`Notes` punya 775 nilai unik dengan pola sangat berulang — bentuk yang cocok untuk
rules, bukan untuk LLM. Tapi alasan utamanya bukan biaya:

> LLM selalu punya jawaban. Untuk `"Saw our post about replacing hubspot and
> commented."` — yang sumbernya memang tidak bisa ditentukan dari teks — jawaban yang
> benar adalah **"tidak tahu"**. Rules bisa mengatakannya.

Jadi rules menangani 92,1% yang berpola, dan **162 baris (7,9%)** keluar dengan
`needs_llm_review = true` alih-alih ditebak. Angka itu sekaligus jadi metrik: kalau naik
melewati ~25%, itu sinyal otomatis bahwa distribusi `Notes` bergeser dan pendekatannya
perlu diganti — bukan sesuatu yang harus ditemukan lewat keluhan pengguna.

---

## Catatan penggunaan LLM

**Tidak ada panggilan LLM berbayar. Biaya kredit: nol.** Seluruh klasifikasi sumber dan
seluruh dedup berjalan dengan rules + fuzzy matching lokal (`rapidfuzz`), tanpa API key.

Ini keputusan desain, bukan penghematan. Untuk 92,1% baris, rules memberi hasil
deterministik yang bisa dites — sifat yang tidak diberikan LLM. Slot LLM-nya tetap ada
dan sudah dipetakan: `needs_llm_review = true` menandai persis 162 baris mana yang butuh
penilaian, sehingga kalau nanti dijalankan, cakupannya sudah terbatas dan biayanya bisa
diperkirakan di muka (±162 panggilan sekali jalan, bukan per request).

---

## Yang akan saya kerjakan berikutnya

Detail lengkap ada di [`docs/ANALISIS-DATA.md` Bagian 4](docs/ANALISIS-DATA.md).
Tiga teratas:

1. **Jalankan LLM pada 162 baris `needs_llm_review`** — cakupannya sudah terisolasi,
   tinggal pilih provider dan bandingkan hasilnya dengan rules sebagai baseline.
2. **UI review duplikat** — 17 pasangan zona review sekarang cuma CSV. API-nya sudah ada
   (`/leads/dedupe-candidates` + `/leads/{id}`), yang kurang tinggal antarmukanya dan
   endpoint merge yang menunggu keputusan bisnis di atas.
3. **Ganti pencocokan telepon 9-digit-terakhir dengan `libphonenumber`** — heuristik
   sekarang tahan terhadap selisih kode negara, tapi secara teori bisa menabrakkan dua
   nomor dari negara berbeda. Belum terjadi di dataset ini; akan terjadi kalau volumenya
   naik.

Auth sengaja tidak dibangun (eksplisit di luar scope), tapi perlu dicatat jujur:
`PATCH /leads/{id}` dan `POST /leads/ingest` adalah operasi tulis tanpa proteksi. Itu
prasyarat pertama sebelum apa pun di sini menyentuh produksi.
