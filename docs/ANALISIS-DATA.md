# Analisis & Pembersihan Data — `leads_seed.csv` + `website_form_submissions.json`

Dokumen tunggal yang mencakup: **temuan → solusi → justifikasi**, lalu keputusan
pemrosesan, lalu keputusan yang masih harus diambil, lalu rencana perbaikan.

Semua angka di sini direproduksi oleh `python src/clean_leads.py` → `out/report.json`.

---

## Ringkasan

| | Angka |
|---|---|
| Baris masuk | **2.049** × 22 kolom |
| Kolom 100% kosong | **5** |
| Perkiraan orang unik | **± 1.786** (263 baris redundan, ≈13%) |
| Grup duplikat terdeteksi | **232** (201 pasang + 31 triplet) |
| Pasangan butuh review manusia | **17** |
| Entri JSON | 90 → **49 sudah ada**, **41 baru** |
| Baris yang dihapus pipeline | **0** (non-destruktif) |
| Test | **28 passed** |

Tiga masalah dengan dampak bisnis terbesar:

1. **Duplikasi 263 baris** → satu orang dihubungi 2–3 sales, forecast ter-*inflate*.
2. **`Lead Status` punya 35 varian untuk 7 nilai** → semua filter & agregasi rusak diam-diam.
3. **`Original Source` 49,5% kosong + sisanya generik** → atribusi channel tidak bisa dihitung dari kolom itu.

---

# BAGIAN 1 — Temuan, Solusi, dan Justifikasi

## 1.1 Kolom yang tidak membawa informasi

| # | Masalah | Bukti | Solusi | Justifikasi |
|---|---|---|---|---|
| 1 | 5 kolom kosong di **seluruh** 2.049 baris | `City`, `Original Source Drill-Down 1`, `Annual Revenue`, `Marketing contact status`, `GDPR consent` = 0 terisi | **Tidak dimodelkan** | Kolom nol-isi tidak membawa data tapi tetap memaksa keputusan desain (nullable? default? divalidasi?) di setiap layer. Ini anti-pattern yang membuat export HubSpot punya 200+ kolom yang tak seorang pun berani sentuh. Menghapusnya tidak menghilangkan data — hanya slot kosong. Kalau nanti dipakai, menambahnya = satu migrasi sepele. |
| 2 | `GDPR consent` kosong bisa disalahtafsirkan | 2.049 baris kosong | Kosong **tidak** dibaca sebagai "tidak setuju" | Blank artinya *export ini tidak membawa informasinya*, bukan penolakan consent. Menafsirkannya sebagai "tidak" adalah kesalahan hukum, bukan kesalahan data. |
| 3 | Kolom terisi sebagian | `Job Title` 59,6% · `Lead Score` 7,5% · `Last Modified Date` 73% | **Simpan apa adanya, jangan imputasi** | Skor parsial masih berguna untuk prioritisasi; skor karangan tidak. Blank adalah fakta yang terlihat sebagai *gap*; nilai karangan terlihat sebagai *fakta*. |

## 1.2 Nama — `Full Name` ternyata bukan varian skema

| # | Masalah | Bukti | Solusi | Justifikasi |
|---|---|---|---|---|
| 4 | Dua bentuk penulisan nama | 1.942 baris `First`+`Last` · 107 baris `Full Name` · **0 baris punya keduanya** | Gabung ke `display_name` + simpan `name_source` sebagai jejak audit | Karena saling eksklusif (0 tumpang tindih), penggabungan tidak butuh resolusi konflik sama sekali. |
| 5 | **Seluruh 107 baris `Full Name` berada di dalam grup duplikat — tidak satu pun berdiri sendiri** | 107/107 di dalam klaster; 0 klaster yang semua anggotanya bentuk `Full Name` | Jadikan `Full Name` sebagai **sinyal dedup**, bukan sekadar kolom yang dirapikan | Ini mengubah cara pandang: `Full Name` bukan skema alternatif, melainkan **jejak baris hasil re-entry**. Saat orang dimasukkan ulang, sistem sumber menaruh namanya di `Full Name`, sering dalam bentuk inisial. |
| 6 | Bentuk inisial lolos dari string similarity | `fuzz.ratio("ji-woo yoon", "j. yoon")` = **0,63** — di bawah ambang wajar | Aturan khusus **initial-form match** (skor 0,95) | Tanpa ini, seluruh kelas duplikat re-entry lolos. Aturannya hanya aktif kalau minimal satu sisi memang berbentuk inisial (`^[A-Za-z]\.?$`) — supaya `Marcus Ho` tidak tersamakan dengan `Mia Ho`. |

**Contoh nyata (grup `G0012`):**

```
100234955  Ji-woo Yoon   Foster Studio    ji-wooy@foster.biz      +34696235827
100234956  J. Yoon       Foster Trading   j.yoon@foster.biz       +34696235827
100234957  J. Yoon       Foster Partners  ji-woo.yoon@foster.biz  +34696235827
```

Satu orang, tiga baris, tiga nama perusahaan, tiga email — satu nomor telepon.

## 1.3 Format tidak konsisten

| # | Masalah | Bukti | Solusi | Justifikasi |
|---|---|---|---|---|
| 7 | `Lead Status` 35 varian | `New`, `new`, `NEW`, `" New"`, `"New "` — semuanya 7 status kanonik | Trim → collapse spasi → cocokkan lowercase → Title Case. **Nilai asing dipertahankan apa adanya** | Memaksa nilai tak dikenal jadi `Other` akan menyembunyikan perubahan skema selama berbulan-bulan. Meloloskannya membuat status baru langsung terlihat di dashboard. |
| 8 | `Country/Region` 62 varian | `germany` vs `Germany` | Title-case per kata, **dengan pengecualian akronim** | Tanpa pengecualian, `UAE` jadi `Uae`. |
| 9 | `Contact Owner` 20 varian | tepat 10 owner, masing-masing punya varian trailing space | Trim | Satu-satunya perbedaan adalah whitespace. |
| 10 | **3 format tanggal** | `2026-06-02` (1.125) · `6/4/2026` (599) · `2026-05-20T00:00:00Z` (325) | Semua → ISO-8601 UTC | Standar tunggal yang bisa di-sort sebagai string. |
| 11 | `M/D/YYYY` vs `D/M/YYYY` ambigu | Dari 599 nilai: komponen pertama **maks 12**, komponen kedua **mencapai 31** (341 baris > 12) | **US month-first, terbukti bukan diasumsikan** | Kalau urutannya `D/M/YYYY`, mustahil ada nilai 31 di posisi bulan. Ini bukti aritmetik, bukan tebakan berdasarkan "biasanya CRM Amerika". |
| 12 | `Last Modified Date` kosong 553 baris | 1.496 terisi | **Tidak diisi dari `Create Date`** | "Belum pernah diubah" dan "diubah pada tanggal dibuat" adalah dua fakta berbeda. Mengisinya = mengarang riwayat. |
| 13 | Telepon 2 format | 1.890 `+CC` dengan pemisah · 159 digit polos | `phone_e164` untuk display + **9 digit terakhir** sebagai kunci match | `+34 696 235 827` dan `34696235827` nomor yang sama. Normalisasi digit saja tidak cukup kalau satu baris menyertakan kode negara dan yang lain tidak. Memotong 9 digit terakhir membuat pencocokan tahan selisih prefix. Ini setara dengan *national significant number* di `libphonenumber`. |
| 14 | Email beda titik = orang sama | 1.499 email punya titik di localpart; `luca.wagner@` vs `lucawagner@` | `email_key`: buang titik/dash/underscore + plus-tag dari localpart | Pola ini terbukti menandai orang yang sama di dataset ini. **Catatan jujur:** ini perilaku Gmail, bukan standar RFC — karena itu bobotnya 0,97, bukan 1,00, sehingga asumsi yang salah berujung di zona review, bukan merge otomatis. |
| 15 | Artefak generator di nama perusahaan | 95 baris: `Chen Digital and and Co`, `Gupta Textiles Retail Retail Group` | `company_display`: rapikan `and and` → `&`, buang kata berulang | Kerusakan yang tak terbantahkan — ada jawaban benar yang jelas. |
| 16 | **Suffix perusahaan menyamarkan duplikat** | Orang sama muncul sebagai `Foster Studio`, `Foster Trading`, `Foster Partners` | `company_core`: kupas suffix legal + deskriptif **secara berulang** sampai stabil → `foster` | Satu pass tidak cukup: `Gupta Textiles Retail Retail Group` butuh 3 iterasi. Dua representasi dipakai — `display` (konservatif, untuk manusia) dan `core` (agresif, untuk mesin). |

**Prinsip yang berlaku di seluruh §1.3:**

> Simpan bentuk asli untuk ditampilkan, buat bentuk kanonik terpisah untuk dicocokkan.
> Jangan pernah menimpa yang satu dengan yang lain.

Karena itu tiap entitas punya dua kolom: `email`+`email_key`,
`phone_e164`+`phone_key`, `company_display`+`company_core`. Reviewer melihat data
seperti aslinya; mesin mencocokkan pakai kunci.

## 1.4 Duplikasi — temuan inti

| # | Masalah | Bukti | Solusi | Justifikasi |
|---|---|---|---|---|
| 17 | **`Record ID` duplikat?** | **2.049 ID unik dari 2.049 baris** | Aman dipakai sebagai primary key | Hipotesis awal **terbantah**. Tidak perlu penanganan. |
| 18 | Duplikasi tersebar & tak terlihat | 58 email persis sama → 116 baris · 232 nomor sama → 495 baris · 136 baris bertanda `"possible duplicate"` di `Notes` | Blocking + scoring + union-find → **232 grup, 263 baris redundan** | Penanda di `Notes` hanya menutupi ~27% kasus nyata. 103 dari 232 grup ditemukan **tanpa** bantuan penanda itu. |
| 19 | **2.098.176 pasangan** kalau dibandingkan semua-lawan-semua | 2.049² / 2 | **Blocking 4 kunci** → 513 kandidat (**reduksi 99,9756%**) | README menyebut brute-force tidak praktis. Empat kunci dipakai karena tiap kunci punya titik buta dan gabungannya saling menutup (tabel di §1.5). |
| 20 | **Nama mirip ≠ orang sama** | 112 pasangan kandidat nama mirip + perusahaan sama tapi **bukan** duplikat; 11 di antaranya bahkan lolos ambang nama 80% | **Aturan Keras #1:** tanpa anchor email/telepon, confidence diplafon **0,45** | Lihat §1.6 — ini keputusan terpenting di seluruh sistem. |
| 21 | Telepon kantor bersama | satu nomor dipakai beberapa orang | **Aturan Keras #2:** anchor kuat tapi kemiripan nama < 0,55 → plafon 0,55 | Mencegah nomor bersama menggabungkan dua orang berbeda. |
| 22 | Duplikat transitif | A≈B, B≈C, tapi A dan C tidak pernah berbagi blok | **Union-Find (DSU)** | Bisnis butuh *grup*, bukan *pasangan*. Hasil: 201 pasang, 31 triplet, **0 grup > 3** — ketiadaan grup besar membuktikan tidak ada over-merging transitif. |
| 23 | **Anggota grup punya nilai berbeda di kolom lain** | konflik `Company Name` **231/232 grup** · `Email` **193/232** · field bisnis lain **0** | Tampilkan daftar `conflicts` eksplisit per grup | Hipotesis di `ListMasalah.md` **terkonfirmasi**, tapi kabar baiknya: setelah normalisasi, `Lead Status`/`Lifecycle Stage`/`Owner`/`Country`/`Job Title`/`Lead Score`/`Original Source`/`Last Modified` **tidak pernah berkonflik**. Anggota selalu sepakat pada field bisnis — yang beda hanya *representasi*. Jadi tidak ada kasus "dua nilai sama-sama valid, pilih mana". |
| 24 | **95 grup (41%) justru *dapat* informasi kalau digabung** | satu anggota punya `Last Modified Date`, anggota lain kosong | Non-destruktif: 0 baris dihapus | Ini bukan konflik, melainkan saling melengkapi. Menghapus baris yang salah di 95 grup ini membuang timestamp yang tidak ada di baris satunya — persis yang dikhawatirkan di `ListMasalah.md`. |

## 1.5 Kenapa 4 kunci blocking, bukan satu

| Kunci | Buta terhadap | Ditutup oleh |
|---|---|---|
| `phone_key` (9 digit terakhir) | nomor diganti antar entri | kunci email |
| `email` (persis) | localpart beda titik | `email_key` |
| `email_key` (ternormalisasi) | localpart benar-benar beda (`m.ho` vs `marcus.h`) | `dom_last` |
| `dom_last` (domain + nama belakang) | nama belakang hilang / domain beda | `phone_key` |

Pasangan dibentuk dari **union** semua blok — cukup satu kunci cocok untuk masuk
kandidat. Inilah yang menjaga recall tinggi meski tiap kunci individual lemah.

`BLOCK_MAX = 50` sebagai pengaman *block explosion*: blok yang mengumpulkan ratusan
baris bukan sinyal, dan menghitung C(n,2)-nya akan membanjiri kandidat. Di dataset ini
tidak ada blok yang melampaui batas — pengaman ini untuk data masa depan.

## 1.6 Aturan Keras — lahir dari dua kegagalan kalibrasi nyata

Kedua aturan ini **bukan desain awal.**

**Kalibrasi #1 — terlalu sedikit tertangkap.** Versi pertama memberi bobot 0,30 pada
kesamaan email persis. Duplikat jelas yang localpart emailnya berbeda (padahal telepon
+ nama + perusahaan identik) hanya mencetak ~0,69 dan tidak pernah di-merge.
Hasilnya: cuma 58 grup, dan hanya 33 dari 136 baris bertanda yang tertangkap.

→ **Perbaikan:** restrukturisasi jadi tiga komponen — *identity* / *person* / *org* —
supaya **jenis** bukti yang dinilai, bukan sekadar penjumlahan field yang cocok.

**Kalibrasi #2 — false positive.** Setelah perbaikan itu muncul masalah kebalikan:

```
Rania Andersen  vs  Hana Andersen  @ Sim Robotics
  nama 0,62 · perusahaan 1,00 · negara beda · telepon beda · email beda
  → 0,791   ← nyaris ter-merge, padahal jelas dua orang
```

Yang salah bukan angkanya, tapi **premisnya**: sistem memperbolehkan nama + perusahaan
saling menumpuk melewati ambang tanpa bukti identitas sama sekali.

→ **Perbaikan:** Aturan Keras menutup jalan itu secara **struktural** — bukan dengan
menaikkan ambang (yang akan mengorbankan kasus benar), tapi dengan menyatakan bahwa
kelas bukti tertentu **tidak memenuhi syarat** untuk merge, seberapa pun skornya.

```python
identity = max(bobot anchor yang cocok)      # email/telepon
person   = max(kemiripan_nama, 0.95 jika bentuk_inisial_cocok)
org      = 1.0 jika domain_root sama, selain itu kemiripan company_core

conf = 0.45·identity + 0.33·person + 0.12·org
     + 0.05·negara_sama + 0.05·(≥2 anchor kuat)

if identity <  0.95:                    conf = min(conf, 0.45)   # ATURAN KERAS 1
if identity >= 0.95 and person < 0.55:  conf = min(conf, 0.55)   # ATURAN KERAS 2
```

| Anchor identitas | Bobot | Alasan bobotnya begitu |
|---|---:|---|
| email persis sama | **1,00** | bukti terkuat yang tersedia |
| email sama setelah normalisasi | **0,97** | sedikit di bawah 1,00 karena asumsi Gmail-style |
| 9 digit telepon terakhir sama | **0,95** | kuat, tapi bisa nomor kantor bersama |
| domain sama + localpart mirip ≥62% | **0,70** | sugestif saja, **tidak pernah cukup sendiri** |

Distribusi bobot ini mewujudkan satu kalimat:
**identitas membuktikan · nama mengonfirmasi · organisasi hanya mendukung.**

### Kasus uji `Marcus Ho` — jebakan yang sengaja ditanam dataset

```
100235561  Marcus Ho  Asante Retail Ltd     m.ho@asanteretail.io      +86 132 2249 7096  China
100236210  Marcus Ho  Asante Retail & Co    marcus.h@asanteretail.com +852 8646 1508     Hong Kong
100236211  Marcus Ho  Asante Retail & Labs  marcush@asanteretail.com  +852 8646 1508     Hong Kong
```

Jawaban yang benar bukan "semua sama" dan bukan "semua beda":

| Pasangan | Confidence | Hasil |
|---|---:|---|
| `100236210` ↔ `100236211` | **0,987** | duplikat — telepon & domain identik |
| `100235561` ↔ keduanya | **0,45** | orang berbeda — telepon, negara, TLD email beda |

Satu nama, satu perusahaan, tiga baris — dipisahkan dengan benar.

### Pasangan lain di zona review

| Pasangan | Kenapa tidak di-merge |
|---|---|
| `Freya Al-Sayed` / `Sophia Al-Sayed` @ Koh & Sons | nama belakang sama, mungkin saudara — Swedia vs China |
| `Lucas Schmidt` / `Lucas Schmidt` @ Chua Textiles | **nama & perusahaan identik**, Nigeria vs Vietnam |
| `Arjun Carvalho` / `Arjun Carvalho` @ Lotus Finance | **nama & perusahaan identik**, Polandia vs Italia |
| `Ravi Agyemang` / `Rin Agyemang` @ Zhang Holdings | nama depan mirip, Indonesia vs Polandia |
| `Aisha Gomes` / `Abena Gomes` @ Yap Ventures | Indonesia vs Argentina |
| `Min-jun Fischer` / `Youssef Fischer` @ Verma Consulting | Nigeria vs Jerman |

Total **17 pasangan** — jumlah yang realistis untuk ditinjau manusia dalam satu duduk.

### Bukti blocking tidak kehilangan duplikat

Reduksi 99,98% tak berarti kalau yang terbuang justru jawabannya. Tiga pemeriksaan:

| Uji | Hasil |
|---|---|
| **Ground truth** — baris bertanda `"possible duplicate"` | **136/136 (100%)** tertangkap. Dan kami menemukan lebih banyak: 103 grup ditemukan tanpa bantuan penanda |
| **Brute force tandingan** — scan `nama\|domain_root` di luar hasil klaster | hanya **4 pasangan** tak terkelompok; keempatnya diperiksa manual dan memang **orang berbeda** (persis jebakan README) → bukan kebocoran, tapi perilaku benar |
| **Stabilitas ambang** — sapu 0,70 → 0,95 | **clustering identik**. Tidak ada pasangan mengambang di zona tengah; 0,90 bisa digeser jauh tanpa mengubah hasil |

```
dari 513 pasangan kandidat:
  ≥ 0,90   : 294   ← hampir pasti duplikat
  0,45–0,90:  17   ← review manusia
  < 0,45   : 202   ← kemungkinan orang berbeda
```

Tidak ada penumpukan di tengah — tanda fiturnya diskriminatif, bukan ambang yang dipaksakan.

## 1.7 `Original Source` tidak bisa dipercaya — `Notes` yang bisa

| # | Masalah | Bukti | Solusi | Justifikasi |
|---|---|---|---|---|
| 25 | `Original Source` 49,5% kosong | 1.014 dari 2.049 | Turunkan jadi **sinyal fallback**, bukan sumber utama | Setengah data tidak punya nilai sama sekali. |
| 26 | Yang terisi pun generik | **129 baris** `"Offline Sources"` yang semuanya ternyata lead **event** | Ekstrak channel dari `Notes` | `"Offline Sources"` benar secara teknis tapi tidak berguna untuk keputusan marketing. |
| 27 | **Label sama → tiga channel berbeda** | `Other Campaigns` → Manual/Sales (170), Other (71), **Event (31)** | `Other Campaigns` & `Offline Sources` **sengaja tidak dipetakan** di fallback | Kolom itu tidak punya daya pisah. Memakainya sebagai fallback = melempar koin lalu mencatatnya sebagai fakta. |
| 28 | **311 baris cocok ke ≥2 channel** | `"Found us through organic google search then landed on the pricing page."` → Organic Search **dan** Website | **Urutan prioritas eksplisit**: Event > Referral > LinkedIn > Manual/Sales > Organic Search > Website > Other | Semakin spesifik channel-nya, semakin tinggi prioritasnya. `Website` hampir selalu benar secara harfiah (semua orang akhirnya mendarat di website) — justru karena itu nyaris tak punya daya informasi, jadi ditaruh paling bawah. `Event` paling atas karena "bertemu di booth" adalah fakta tak terbantahkan. |
| 29 | **`google ad` bukan Organic Search** | 119 baris `"...after clicking a google ad."` | `PAID_HINT` override → `Website` | Aturan naif yang menangkap kata "google" akan melaporkan lead **berbayar** sebagai **organik** — kesalahan atribusi yang persis menyesatkan keputusan budget. |
| 30 | Outcome di `Notes` bukan channel | `"Qualifying now."`, `"Not interested for now."` | Tidak dipakai sebagai sinyal channel | Itu status follow-up, bukan sumber lead. |
| 31 | **91 baris genuinely ambigu** | `"Saw our post about replacing hubspot and commented."` — "post" bisa LinkedIn, blog sendiri, atau forum | `needs_llm_review = true`, confidence 0,3, **tidak ditebak** | Total **162 baris (7,9%)** masuk kategori ini. Angka itu adalah *estimasi biaya LLM yang sebenarnya* — bukan 2.049 panggilan, tapi 162. |

**Hasil klasifikasi:** Website 507 · Event 374 · Organic Search 311 · Manual/Sales 268 ·
Referral 241 · LinkedIn 226 · Other 122. Mean confidence **0,831**; **92,1%**
terklasifikasi tanpa LLM.

## 1.8 `website_form_submissions.json`

| # | Masalah | Bukti | Solusi | Justifikasi |
|---|---|---|---|---|
| 32 | **`form_id` & `form_name` saling bertentangan** | **16 kombinasi** dari 4 `form_id` × 5 `form_name`. Contoh: `form_id: "form_demo_request"` + `form_name: "Newsletter Signup"` + `page_url: "/blog"` | Ketiganya **tidak dipakai** untuk menentukan channel. Semua form website → `Website`; `page_url` disimpan sebagai `detail` | `page_url` satu-satunya yang merekam **fakta** (URL tempat form benar-benar dikirim), bukan label yang bisa salah konfigurasi. |
| 33 | `message` mayoritas boilerplate | hanya **39 pesan unik dari 90**; satu kalimat muncul **49× (54%)** | Kalau boilerplate → pakai `Website` dari konteks form, jangan paksa ekstraksi | Klasifikasi polos akan melabeli 54% submission sebagai `Other` dengan percaya diri. 51 entri sisanya (`"Met at the booth..."`, `"Referred by Elena Han"`) membawa channel yang **berbeda** dari Website — untuk ini `message` lebih dipercaya. |
| 34 | Masalah format sama seperti CSV | 2 telepon tanpa `+` · 1 negara huruf kecil (`malaysia`) | Normalizer **yang sama** dipakai untuk kedua sumber | Inilah alasan logika normalisasi ditaruh di satu modul, bukan di-inline per loader. |
| 35 | **49 dari 90 entri sudah ada di seed** | cocok pada email **dan** telepon-9-digit (set identik) · 41 benar-benar baru · 0 duplikat internal | `POST /leads/ingest` **wajib dedup sebelum insert** | Ingest naif akan menambah 49 duplikat baru — 54% payload. |
| 36 | 9 dari 49 mendarat di baris yang **sendirinya** sudah dalam grup duplikat | | matcher yang sama (§1.6) dipakai di jalur ingest | Tanpa ini, orang yang sudah punya 2 entri akan dapat entri ketiga. |

## 1.9 Yang sengaja TIDAK dibersihkan

Sama pentingnya dengan yang dibersihkan.

| Temuan | Kenapa dibiarkan |
|---|---|
| `Lead Status` × `Lifecycle Stage` sama sekali tidak berkorelasi (crosstab merata) | Di HubSpot keduanya memang dimensi independen. Memaksa konsistensi = mengarang aturan bisnis yang tidak ada buktinya. |
| Outcome `Notes` bertentangan dengan `Lead Status` (`"Not interested"` pada lead `Closed Won`) | `Notes` = riwayat, `Lead Status` = keadaan kini. Keduanya **boleh** berbeda. Menimpa salah satunya menghapus jejak. |
| `Lead Score` 92,5% kosong · `Job Title` 40% kosong | Tidak bisa disimpulkan dari field lain. Imputasi = mengarang. |
| Penanda `"possible duplicate"` di `Notes` | Dipertahankan di `Notes` asli (jejak audit), tapi **dilepas sebelum klasifikasi channel** agar tidak mengotori ekstraksi. |
| Telepon tidak divalidasi per-negara (`+86` dengan `Country = Hong Kong`) | Data sintetis — validasi semacam ini akan menghasilkan ribuan false invalid tanpa nilai informasi. Di produksi ini sinyal bagus; di sini tidak. |

**Aturan yang dipegang:** kalau menuliskan aturan perbaikan mengharuskan saya
mengarang aturan bisnis yang tak ada buktinya di data, saya tidak menulisnya. Data
kosong yang jujur lebih berguna daripada data terisi yang dikarang — yang pertama
terlihat sebagai *gap*, yang kedua terlihat sebagai *fakta*.

---

# BAGIAN 2 — Keputusan yang Diambil dalam Pemrosesan Data

## 2.1 Arsitektur: 4 tahap, satu arah

```
  leads_seed.csv (2.049 × 22)
           │
  ┌────────▼────────┐
  │ 1. NORMALISASI  │  per baris, tanpa konteks baris lain
  └────────┬────────┘  nama · email · telepon · perusahaan · tanggal · enum
           │
  ┌────────▼────────┐
  │ 2. EKSTRAKSI    │  Notes → {channel, detail, confidence, needs_llm_review}
  │    SUMBER       │  rules-first, LLM hanya untuk sisa yang ambigu
  └────────┬────────┘
           │
  ┌────────▼────────┐
  │ 3. DEDUP        │  blocking → scoring → union-find
  └────────┬────────┘  2.098.176 → 513 kandidat → 232 grup
           │
  ┌────────▼────────┐
  │ 4. SURVIVORSHIP │  usulkan master + golden record + daftar konflik
  └────────┬────────┘  TIDAK menghapus apa pun
           ▼
     out/*.csv, out/*.json
```

**Kenapa satu arah tanpa loop balik?** Karena tiap tahap hanya bergantung pada output
tahap sebelumnya, seluruh pipeline bisa dites per tahap dan dijalankan ulang dari titik
mana pun. Ini juga yang membuat `POST /leads/ingest` nanti bisa memakai ulang tahap
1–3 untuk **satu** record tanpa memuat seluruh dataset.

## 2.2 Tujuh keputusan besar

### Keputusan 1 — Non-destruktif: tidak ada baris yang dihapus

| Pilihan | Konsekuensi |
|---|---|
| Hapus duplikat langsung | output bersih, tapi 263 baris hilang permanen dan 95 grup kehilangan `Last Modified Date` yang hanya ada di baris yang dibuang |
| **Tandai + usulkan master** ✅ | butuh satu langkah tambahan, tapi **idempoten**, bisa diaudit, tidak ada yang hilang |

**Alasan:** operasi ini punya **asimetri biaya**. Merge yang salah itu mahal dan sulit
dibatalkan; menunda merge itu murah. Ketika biaya kesalahan tidak simetris, default
harus ke arah yang bisa diperbaiki. Ditambah README memang menyatakannya:
*"You do not need to auto-merge leads."*

**Harga yang dibayar:** konsumen `out/leads_clean.csv` harus sadar file itu **masih
mengandung duplikat**, dan perlu `out/dedupe_groups.json` untuk menyatukannya.
Didokumentasikan, bukan disembunyikan.

### Keputusan 2 — Rules dulu, LLM untuk sisanya

| | Rules | LLM |
|---|---|---|
| Teks `Notes` | **775 nilai unik, pola sangat berulang** | dirancang untuk teks bebas & bervariasi |
| Determinisme | sama input → sama output, selamanya | bisa berubah antar versi model |
| Bisa dites | `assert extract(...)["channel"] == "Event"` | butuh mock/snapshot |
| Biaya per 2.049 baris | ~0 | 2.049 panggilan |
| **Kasus genuinely ambigu** | **gagal, dan tahu bahwa ia gagal** | menebak dengan percaya diri |

Baris terakhir itu poin utamanya:

> LLM selalu punya jawaban. Untuk `"Saw our post about replacing hubspot and
> commented."` — yang memang tidak bisa ditentukan dari teks — jawaban yang benar
> adalah **"tidak tahu"**. Rules bisa mengatakannya.

Pembagian tugas: **rules menangani 92,1% yang berpola, LLM disediakan untuk 7,9%
yang benar-benar butuh penilaian.**

**Kenapa bukan LLM untuk semuanya?** Bukan soal uang (162 vs 2.049 panggilan sama-sama
murah), tapi **determinisme**: fungsi berbasis rules bisa dites dengan `assert` dan
hasilnya tidak berubah saat versi model naik. Untuk logika yang jadi input dashboard,
sifat itu berharga.

**Trade-off jujur:** pendekatan ini **tidak akan bertahan** kalau `Notes` di produksi
jauh lebih bervariasi. Regex adalah taruhan pada keteraturan. Mitigasinya sudah
terpasang: `needs_llm_review` adalah **metrik terukur** — kalau naik dari 7,9% ke 40%,
itu sinyal otomatis bahwa distribusi bergeser, bukan sesuatu yang harus ditemukan
lewat keluhan pengguna.

### Keputusan 3 — Identity anchor wajib; nama tidak pernah cukup

Ini **menolak sebagian usulan di `ListMasalah.md`** (nama >80% → duplikat), dan
penolakannya berbasis data:

| Arah kesalahan | Bukti |
|---|---|
| **Terlalu longgar** | di ambang 80%: **11 pasangan** nama mirip + perusahaan sama tapi jelas orang berbeda. Turunkan ke 60% → **112** |
| **Terlalu ketat** | `J. Yoon` vs `Ji-woo Yoon` = **63%**, di bawah 80%, padahal orang yang sama |

Jadi ambang nama salah **di dua arah sekaligus**. Bukan angkanya yang perlu disetel,
tapi **sinyalnya yang perlu diganti**.

**Yang dipertahankan dari usulan itu:** gagasan *human-in-the-loop* — dan gagasan itu
justru jadi lebih berguna. Dengan aturan berbasis nama, manusia menghadapi ratusan
pasangan. Dengan identity anchor, yang tersisa **17 pasangan**, masing-masing sudah
disertai alasan dan daftar konflik.

**Harga:** kalau ada duplikat nyata yang email **dan** teleponnya sama-sama berbeda di
kedua entri, sistem melewatkannya. Risiko ini diperiksa (brute force §1.6) dan
diterima secara sadar: **lebih baik melewatkan duplikat daripada menggabungkan dua
orang berbeda.** Merge yang salah berarti riwayat dua orang tercampur dan sales
menghubungi orang yang keliru — kerusakan jauh lebih mahal daripada satu baris
duplikat yang lolos.

### Keputusan 4 — Blocking deterministik, bukan embeddings

| | Blocking | Embeddings + ANN |
|---|---|---|
| Kesamaan semantik (`Bob` ≈ `Robert`) | tidak | ya |
| Deterministik & bisa dijelaskan | **ya** | tidak sepenuhnya |
| Dependency | tidak ada | model + index |
| Cocok untuk data ini | **ya** | berlebihan |

**Alasan:** duplikat di dataset ini adalah **re-entry**, bukan variasi semantik.
Orangnya membawa nomor telepon dan domain email yang sama; yang berubah cuma format.
Embedding memecahkan masalah *"dua string berbeda merujuk hal yang sama secara makna"* —
masalah nyata di sini adalah *"satu identitas ditulis beberapa cara"*.

Bonus praktis: setiap keputusan merge bisa dibaca sebagai kalimat
(*"9 digit terakhir telepon identik, nama bentuk inisial cocok"*). Dengan cosine
similarity, penjelasannya berhenti di angka.

### Keputusan 5 — Zona review, bukan satu ambang tunggal

Satu ambang memaksa setiap pasangan jadi ya/tidak. Padahal kelas kasus ketiga memang
eksis: **nama sama, perusahaan sama, kontak berbeda.** Tidak ada nilai ambang yang
bisa memutuskannya dengan benar, karena informasinya memang **tidak ada di dalam data**.

Menyerahkan 17 pasangan ke manusia adalah jawaban yang jujur.
`out/dedupe_review.csv` dirancang untuk dibuka di spreadsheet: kedua record
bersebelahan kolom demi kolom, plus kalimat `why`.

### Keputusan 6 — Survivorship berlapis, master bukan pemenang mutlak

```python
sorted(members, key=lambda r: (
    -_completeness(r),              # 1. paling banyak field terisi
    -_name_quality(r),              # 2. nama penuh > bentuk inisial
    _inv(r["last_modified_date"]),  # 3. paling baru diubah
    r["record_id"],                 # 4. Record ID terkecil (deterministik)
))[0]
```

| # | Kriteria | Alasan |
|---|---|---|
| 1 | Kelengkapan | record yang membawa lebih banyak info = fondasi lebih baik, lebih sedikit field perlu ditambal |
| 2 | Kualitas nama | `Joon Diallo` > `J. Diallo`. Bentuk inisial adalah **artefak re-entry**, bukan preferensi orangnya |
| 3 | Recency | di antara yang setara, yang terakhir disentuh sales biasanya paling akurat |
| 4 | Record ID terkecil | tie-break **deterministik** — jalankan 2× harus sama; sekaligus cenderung mempertahankan record tertua yang mungkin sudah dirujuk sistem lain |

Tapi **master tidak menang mutlak** — `merged_view()` mengambil yang terbaik *per field*:

```python
best_name  = bentuk TERLENGKAP dari SELURUH anggota, bukan dari master
company    = nama TERPENDEK setelah dirapikan (paling sedikit artefak suffix)
create_date= PALING AWAL — saat lead sungguh pertama masuk
field lain = nilai non-kosong pertama menurut urutan survivorship
```

Efeknya di grup 3-anggota Yoon: nama terbaik dari satu anggota (`Ji-woo Yoon`),
perusahaan terbersih dari anggota lain (`Foster Studio`), tanggal paling awal dari
anggota ketiga. Tidak ada baris yang "menang total".

`create_date` diambil paling awal karena secara semantik ia menjawab *"sejak kapan
orang ini ada di pipeline kita"*. Mengambil yang terbaru akan membuat lead lama tampak
baru dan merusak laporan aging.

> **Bug yang pernah terjadi di sini.** Versi awal `pick_master` punya konstruksi sort
> yang keliru dan memilih `J. Diallo` sebagai master padahal `Joon Diallo` tersedia —
> persis kesalahan yang dikhawatirkan di `ListMasalah.md`: versi yang benar kalah dari
> versi yang cacat. Ditemukan lewat inspeksi hasil, lalu **dikunci dengan test**.

### Keputusan 7 — Bersihkan hanya yang punya jawaban benar

| Dibersihkan | Kenapa ada jawaban benar |
|---|---|
| `Lead Status` casing | `"NEW"` dan `" New"` tak terbantahkan sama |
| Format tanggal | `6/4/2026` dan `2026-06-04` momen yang sama |
| Format telepon | `+34 696 235 827` dan `34696235827` nomor yang sama |
| Artefak `and and` | jelas kerusakan generator |

| Dibiarkan | Kenapa tidak ada jawaban benar |
|---|---|
| `Lead Score` 92,5% kosong | nilai skor tidak bisa disimpulkan dari field lain |
| `Status` × `Lifecycle` tidak berkorelasi | di HubSpot keduanya memang independen |
| `Notes` vs `Lead Status` bertentangan | riwayat vs keadaan kini |
| `Last Modified Date` kosong | "belum diubah" ≠ "diubah saat dibuat" |

Ini menjawab langsung arahan README: *"Deciding what to normalize, what to ignore, and
how much cleaning effort is worth it ... is part of what we're evaluating."*

## 2.3 Output yang dihasilkan

| File | Isi |
|---|---|
| `out/leads_clean.csv` | 2.049 baris ternormalisasi + kolom turunan, **0 dihapus** |
| `out/dedupe_groups.json` | 232 grup: anggota, bukti per pasangan, usulan master, `conflicts`, `merged_preview` |
| `out/dedupe_review.csv` | 17 pasangan untuk mata manusia |
| `out/report.json` | seluruh metrik di dokumen ini, agar reproducible |
| `out/leads.db` | SQLite siap pakai untuk API (2.049 lead + 232 grup + index) |

**Contoh satu grup (`G0001`) — konflik ditampilkan, tidak disembunyikan:**

```json
{
  "group_id": "G0001",
  "size": 2,
  "group_confidence": 0.984,
  "suggested_master_record_id": "100234834",
  "members": [
    { "record_id": "100234834", "name": "Joon Diallo",
      "company": "Huang Analytics & Co",       "email": "joond@huanganalytics.co" },
    { "record_id": "100234835", "name": "J. Diallo",
      "company": "Huang Analytics & Pte. Ltd.", "email": "joond@huanganalytics.co" }
  ],
  "conflicts": {
    "company_display": ["Huang Analytics & Co", "Huang Analytics & Pte. Ltd."]
  },
  "merged_preview": { "display_name": "Joon Diallo",
                      "company_display": "Huang Analytics & Co" },
  "evidence": [{
    "confidence": 0.984,
    "why": "hampir pasti duplikat: email identik, 9 digit terakhir telepon identik, nama bentuk inisial cocok, perusahaan sama setelah suffix legal dibuang"
  }]
}
```

Reviewer melihat **apa yang dipertaruhkan** sebelum menyetujui, bukan hanya skor.

## 2.4 Testing — 70 test, fokus pada yang ambigu

| Test | Yang dijaga |
|---|---|
| `test_same_name_same_company_but_different_phone_and_email_stays_in_review` | jebakan Marcus Ho — assert `0,45 ≤ conf < 0,90` |
| `test_siblings_same_surname_same_company_not_merged` | Freya vs Sophia Al-Sayed |
| `test_shared_phone_but_clearly_different_person_is_capped` | Aturan Keras #2 |
| `test_initial_name_form_matches_full_first_name` | `J. Yoon` ↔ `Ji-woo Yoon` |
| `test_google_ad_is_website_not_organic_search` | jebakan atribusi paid/organic |
| `test_unmatched_text_is_flagged_for_llm_not_guessed` | sistem berani bilang tidak tahu |
| `test_generic_original_source_is_not_trusted_blindly` | `Other Campaigns` tidak dipetakan |
| `test_date_three_formats_converge` | 3 format → 1 ISO |
| `test_company_display_repairs_generator_artifacts` | `and and` → `&` |

Test pertama sengaja meng-assert **rentang**, bukan `!=`. Assert "tidak di-merge" akan
tetap lolos kalau confidence-nya 0,02 — padahal itu berarti sistem **yakin** mereka
orang berbeda, sedangkan yang benar adalah *sistem seharusnya ragu*. Yang dites bukan
cuma hasilnya, tapi **kadar keyakinannya**.

**42 test API** (`tests/test_api.py`) menjaga hal yang berbeda — perilaku yang bisa
salah tanpa terlihat:

| Test | Yang dijaga |
|---|---|
| `test_ingest_existing_person_does_not_create_a_new_row` | inti ingest: hitung baris sebelum/sesudah, bukan sekadar status 200 |
| `test_ingest_is_idempotent` | klik ganda pada form tidak menghasilkan dua lead |
| `test_ingest_fills_empty_fields_but_never_overwrites` | isian form tidak menimpa data terverifikasi sales |
| `test_ingest_ambiguous_match_creates_lead_but_flags_it` | zona review **membuat** lead, tidak menahannya |
| `test_patch_normalizes_status_before_storing` | DB tidak terisi ulang dengan 35 varian casing |
| `test_patch_rejects_non_patchable_field` | kolom kunci tidak bisa dibuat tidak konsisten lewat API |
| `test_unknown_field_is_rejected_not_silently_ignored` | salah ketik nama field jadi 422, bukan 200 tanpa efek |
| `test_patchable_set_matches_the_patch_schema` | dua deklarasi "field apa yang boleh diubah" tidak boleh berbeda |
| `test_q_with_sql_metacharacters_is_not_injected` | `'; DROP TABLE leads; --` → 0 hasil, tabel utuh |
| `test_export_route_is_not_shadowed_by_the_id_route` | `/leads/export` bukan lead dengan id `"export"` |
| `test_dashboard_counts_match_the_lead_list` | dashboard dan `GET /leads` tidak boleh saling berbeda |
| `test_pagination_does_not_lose_or_repeat_rows` | halaman 1 + halaman 2 = seluruh hasil, tanpa celah |

Satu bug asli tertangkap oleh tes ini: `db.connect(path=DB_PATH)` menaruh `DB_PATH`
sebagai **nilai default argumen**, yang di-bind sekali saat fungsi didefinisikan.
Akibatnya mengganti `db.DB_PATH` tidak berpengaruh apa pun dan setiap pemanggilan
tetap membuka DB lama. Di tes gejalanya adalah 16 kegagalan sekaligus; di produksi
gejalanya adalah tulisan yang diam-diam mendarat di database yang salah.

### Bug kedua: 200 untuk pertanyaan yang tidak pernah diajukan

Yang ini tidak ditemukan oleh tes — tesnya justru ikut tertipu.

Saat mencoba `/leads/dedupe-candidates` lewat `curl`, saya mengirim
`{"record_id": "100234811"}` padahal nama field-nya `lead`. Server membalas **200**
berisi daftar 232 grup global. Jawaban yang terlihat sangat wajar, untuk pertanyaan
yang sama sekali tidak saya ajukan.

Penyebabnya default Pydantic: field yang tidak dikenal **dibuang diam-diam**. Dan
begitu penyebabnya ketahuan, satu tes yang selama ini hijau ternyata hijau karena
alasan yang salah:

```python
# yang saya kira sedang diuji:  email ditolak karena bukan field PATCHABLE
# yang sebenarnya terjadi:      email dibuang Pydantic → body kosong →
#                               400 dari cabang "tidak ada field yang diubah"
assert client.patch("/leads/100000001", json={"email": "new@x.com"}).status_code == 400
```

Cek `bad = set(fields) - PATCHABLE` di dalam handler tidak pernah bisa tercapai —
**dead code yang menyamar sebagai pengaman**, dengan sebuah tes hijau menempel di
atasnya sebagai bukti palsu.

Perbaikannya di batas, bukan di handler: seluruh model request mewarisi satu basis
`Strict` dengan `extra="forbid"`. Tesnya diperketat — bukan lagi "status 400", tapi
**errornya harus menyebut nama field-nya** dan **nilai di DB harus tidak berubah**:

```python
r = client.patch("/leads/100000001", json={"email": "new@x.com"})
assert r.status_code == 422
assert "email" in r.text
assert client.get("/leads/100000001").json()["email"] != "new@x.com"
```

Pelajaran yang saya ambil: tes yang meng-assert *kode status* saja menguji bahwa
sesuatu gagal, bukan bahwa sesuatu gagal **karena alasan yang benar**. Dua jalur
berbeda bisa sampai ke 400 yang sama. Ini varian dari catatan desain tes di dedup —
`assert REVIEW_T <= conf < MERGE_T`, bukan `assert conf != merge` — dan kali ini
saya melanggarnya sendiri.

---

## 2.5 Lapisan API — keputusan dan alasannya

| # | Keputusan | Alternatif | Kenapa yang ini |
|---|---|---|---|
| 8 | **SQLite**, bukan Postgres atau in-memory | Postgres · dict in-memory | Penilai menjalankan ini di mesin mereka: SQLite menghapus seluruh langkah setup. In-memory ditolak karena `POST /leads/ingest` **menulis** — tanpa persistensi, hasil ingest lenyap dan endpoint-nya jadi demo, bukan fitur. Yang dipakai SQL standar, jadi pindah ke Postgres = ganti driver. |
| 9 | **Blocking key disimpan sebagai kolom + index**, bukan dihitung saat query | hitung di SQL · scan penuh | `phone_key` butuh ekstraksi digit lalu 9 karakter terakhir; `email_key` butuh strip titik dan tag `+`. Keduanya **tidak bisa** ditulis sebagai ekspresi SQL yang bisa diindeks. Menyimpannya membuat dedup saat ingest jadi 4 lookup terindeks, bukan 2.049 perbandingan. |
| 10 | **Satu `build_record()` dipakai pipeline offline dan ingest** | normalisasi terpisah per jalur | Kalau ingest menormalisasi sedikit saja berbeda, blocking key-nya meleset dan dedup online gagal menemukan duplikat yang sebenarnya ada — diam-diam, tanpa error. |
| 10b | **Semua model request `extra="forbid"`** | default Pydantic (buang field asing) | Mengabaikan field asing terlihat ramah, tapi menghasilkan kelas bug yang paling sulit dilihat: server membalas 200, klien yakin sesuatu terjadi, tidak ada yang berubah. Lihat "Bug kedua" di atas — ini bukan kekhawatiran teoretis, saya kena sendiri. |
| 11 | **Ambang yang sama (0,90 / 0,45) dipakai di ingest** | ambang lebih longgar untuk ingest | Kalibrasi yang sudah divalidasi terhadap 2.049 baris tidak ada alasannya diulang dengan angka berbeda. Buktinya: dry-run 90 payload JSON menghasilkan **49 merge / 41 create** — persis angka yang ditemukan analisis offline lewat jalur yang sepenuhnya berbeda. |
| 12 | **Zona review saat ingest tetap MEMBUAT lead**, lalu menandainya | tahan di antrian review | Form submission adalah orang nyata yang sedang menunggu ditelepon. Menahannya berarti prospek hangat menganggur sementara seseorang memutuskan. Biaya salahnya asimetris: duplikat yang ditandai bisa digabung nanti, prospek yang hilang tidak bisa dikembalikan. |
| 13 | **Merge saat ingest hanya mengisi field kosong**, tidak pernah menimpa | timpa dengan data terbaru | Form diisi sendiri oleh lead dan sering lebih miskin (nama panggilan, telepon pribadi) daripada yang sudah diverifikasi sales. Pengecualiannya `notes`, yang di-append karena isinya kronologi. |
| 14 | **`PATCH` hanya menerima 3 field, whitelist** | terima field apa pun | `email` ikut menentukan blocking key. Membiarkannya diubah lewat PATCH tanpa menghitung ulang kunci akan membuat dedup berhenti bekerja tanpa satu pun error muncul. |
| 15 | **Filter dinormalisasi sebelum dicocokkan** | cocokkan apa adanya | Nilai mentah punya 35 varian untuk 7 status. Klien yang menyalin nilai dari data asli tetap harus bisa memfilter dengan benar tanpa tahu varian mana yang ia pegang. |
| 16 | **Dedup precomputed disimpan di tabel**, bukan dihitung per request | hitung ulang tiap panggilan | 232 grup tidak berubah antar request. Menghitung ulang memakan waktu ~detik untuk hasil yang identik. |
| 17 | **Agregasi dashboard di SQL**, bukan di Python | tarik semua baris lalu hitung | Bukan soal kecepatan di 2.049 baris, tapi soal siapa yang memegang kebenaran: kalau dashboard dan `GET /leads` punya dua jalur hitung, cepat atau lambat keduanya berbeda dan tidak ada yang tahu mana yang benar. Ada tes yang memaksa keduanya cocok. |

### Endpoint

| Method | Path | Catatan |
|---|---|---|
| `GET` | `/leads` | filter `status` · `owner` · `country` · `channel` · `q` · paginasi. Semua filter dinormalisasi |
| `GET` | `/leads/{id}` | ikut mengembalikan grup duplikatnya dan riwayat perubahan |
| `PATCH` | `/leads/{id}` | `lead_status` · `contact_owner` · `notes` |
| `GET` | `/leads/export` | CSV streaming dari view yang sedang difilter |
| `POST` | `/leads/ingest` | dedup dulu, tulis kemudian. `?dry_run=true` untuk menghitung tanpa menulis |
| `POST` | `/leads/dedupe-candidates` | 2 mode: grup precomputed, atau skor satu lead terhadap DB |
| `POST` | `/source/extract` | kanal + detail dari teks bebas |
| `GET` | `/dashboard` | hitungan per status/kanal/owner/negara + metrik kualitas data |
| `GET` | `/` | halaman HTML dashboard (bonus) |

### Bukti bahwa ingest benar-benar melakukan dedup

```
DRY RUN 90 entri : {'would_merge': 49, 'would_create': 41}
INGEST NYATA     : {'merged': 49, 'created': 41}   → 2.049 baris jadi 2.090 (+41)
INGEST ULANG     : {'merged': 90}                  → 2.090 baris, tidak bertambah
```

Baris kedua adalah yang penting: ingest naif akan menghasilkan 2.139 baris (+90) di
run pertama dan 2.229 di run kedua. Baris ketiga membuktikan endpoint-nya idempoten —
mengirim ulang payload yang sama tidak menghasilkan satu pun baris baru.

---

# BAGIAN 3 — Keputusan yang Masih Harus Diambil

Hal-hal yang **belum** diputuskan dan butuh input, bukan sekadar pekerjaan sisa.

## 3.1 Butuh keputusan bisnis / stakeholder

| # | Keputusan | Pilihan | Rekomendasi saya |
|---|---|---|---|
| 1 | **Siapa yang menyetujui merge?** 232 grup menunggu | (a) auto-merge semua ≥0,90 · (b) manusia approve batch pertama lalu auto · (c) manusia approve selamanya | **(b)** — approve batch pertama untuk membangun kepercayaan pada aturannya, lalu auto-merge untuk ≥0,90. 17 pasangan zona review tetap manual selamanya. |
| 2 | **Apa yang terjadi pada baris duplikat setelah merge?** | (a) hapus · (b) `merged_into` menunjuk master, baris tetap ada | **(b)** — merge jadi bisa dibatalkan, dan `GET /leads` cukup filter `merged_into IS NULL`. Konsisten dengan prinsip non-destruktif. |
| 3 | **17 pasangan zona review — siapa yang punya konteks?** | Owner lead-nya? Satu orang data steward? | Owner lead — mereka yang pernah berbicara dengan orangnya dan bisa tahu apakah `Lucas Schmidt` di Nigeria dan Vietnam orang yang sama |
| 4 | **Grup duplikat punya `Contact Owner` berbeda — siapa yang pegang setelah merge?** | (a) owner dari master · (b) owner yang paling baru menyentuh · (c) eskalasi ke manajer | Perlu konfirmasi — ini menyangkut komisi sales, jadi bukan keputusan teknis. **Catatan:** di dataset ini `Contact Owner` **tidak pernah berkonflik** dalam satu grup, jadi masalahnya belum muncul — tapi akan muncul di data nyata. |
| 5 | **162 baris `needs_llm_review` — LLM atau `Other`?** | (a) jalankan LLM · (b) biarkan di channel fallback · (c) tanya sales satu-satu | **(a)** — satu panggilan batch, murah, dan mengubah 122 `Other` jadi angka yang lebih berguna |

## 3.2 Butuh keputusan teknis

| # | Keputusan | Trade-off | Rekomendasi saya |
|---|---|---|---|
| 6 | ~~**Penyimpanan**~~ — **sudah diputuskan, lihat §2.5** | SQLite (nol infra) · Postgres (siap produksi, tambah setup) · in-memory (hilang saat restart) | **SQLite**, sudah diimplementasi. Keputusan yang tersisa: kapan pindah ke Postgres — pemicunya adalah penulis konkuren, bukan jumlah baris. |
| 7 | **Ambang merge 0,90 — permanen?** | sapu 0,70–0,95 menghasilkan clustering **identik**, jadi angka pastinya tidak sensitif di data ini | Biarkan 0,90 dan pantau. Kalau data baru membuat hasil mulai berubah saat ambang digeser, itu sinyal fitur mulai kehilangan daya pisah. |
| 8 | **Normalisasi email gaya Gmail untuk semua domain?** | membuang titik adalah perilaku Gmail, bukan RFC | Sempurnakan: batasi ke domain penyedia yang diketahui memakainya, turunkan bobot untuk domain korporat |
| 9 | ~~**Dedup saat ingest: sinkron atau async?**~~ — **sudah diputuskan** | sinkron = latensi naik tapi respons langsung akurat · async = cepat tapi duplikat sempat terlihat | **Sinkron**, sudah diimplementasi: 4 lookup ber-index, terukur cepat. Yang belum diputuskan: apakah tetap sinkron kalau volume form naik 100× — saat itu batching jadi masuk akal. |
| 10 | ~~**Apakah ingest boleh meng-update record yang ada?**~~ — **sudah diputuskan** | (a) update kalau ≥0,90 · (b) selalu insert + tandai | **(a) untuk field kosong saja**, sudah diimplementasi (`enrich()`). Yang **masih** butuh keputusan: bolehkah ingest menimpa nilai yang **sudah terisi** kalau form jelas lebih baru — itu bergantung pada keputusan #1. |
| 11 | **Merge dua lead yang sudah ada — lewat API?** | belum ada endpoint `POST /leads/merge` | Sengaja belum dibuat: bentuknya bergantung pada keputusan #2 (baris duplikat dihapus atau ditandai `merged_into`). Membuatnya sekarang berarti menebak keputusan yang bukan milik saya. |
| 12 | **Autentikasi** | eksplisit out of scope di assignment | Tidak dibuat. Catatan untuk produksi: `PATCH` dan `ingest` adalah endpoint tulis tanpa proteksi apa pun — itu hal pertama yang harus ditambahkan sebelum menyentuh jaringan nyata. |

## 3.3 Kalau `Notes` di produksi jauh lebih bervariasi

Ini **bukan** kalau-kalau — ini asumsi terbesar di sistem ini (Keputusan 2). Keputusan
yang harus diambil saat `needs_llm_review` naik melewati ~25%:

| Pilihan | Kapan dipilih |
|---|---|
| Tambah rule baru | pola barunya jelas dan berulang |
| **Balik jadi LLM-first, rules sebagai validator** | pola sudah terlalu beragam untuk regex |
| Fine-tune model kecil untuk klasifikasi channel | volume sangat besar dan biaya LLM jadi masalah |

Yang penting: **metriknya sudah terpasang**, jadi keputusan ini akan dipicu oleh angka,
bukan oleh keluhan.

---

# BAGIAN 4 — Next Improvement

Berurutan menurut rasio **nilai terhadap usaha**.

## 4.1 Prioritas tinggi

| # | Improvement | Nilai konkret | Usaha |
|---|---|---|---|
| 1 | **Jalankan LLM untuk 162 baris `needs_llm_review`** — satu panggilan batch, structured output dengan enum channel dikunci, `confidence` 0,6 untuk menandai asal model | `Other` turun dari 122; atribusi channel jadi lengkap | Kecil — titik sambungnya sudah ada, kontrak output tidak berubah |
| 2 | **UI review duplikat** — 17 pasangan zona review + 232 grup usulan, tampilan berdampingan, tombol setuju/tolak | Ini yang mengubah "analisis" jadi **alat kerja**. Datanya sudah siap di `dedupe_review.csv`; yang kurang cuma antarmuka | Sedang |
| 3 | **Ganti potong-9-digit dengan `libphonenumber`** — pecah nomor jadi kode negara + national number secara benar | Menghilangkan batasan tabrakan 9-digit secara **struktural**, bukan dimitigasi | Kecil |

## 4.2 Prioritas menengah

| # | Improvement | Nilai | Usaha |
|---|---|---|---|
| 4 | **Kunci blocking berbasis embedding sebagai kunci kelima** | Menangkap alias nama (`Bob`/`Robert`, `Bill`/`William`) dan transliterasi lintas aksara — kelas duplikat yang sekarang **pasti** terlewat | Sedang. Arsitekturnya sudah union-of-keys, jadi penambahannya **aditif** — tidak membongkar apa pun |
| 5 | **Validasi silang negara ↔ kode telepon sebagai *flag*, bukan koreksi** | Ketidakcocokan sering menandakan data entry salah. Di produksi ini sinyal bagus | Kecil |
| 6 | **Turunkan agresivitas `company_core`** — beri bobot lebih rendah untuk suffix deskriptif (`Retail`, `Digital`, `Labs`) alih-alih membuangnya total; atau pakai domain email sebagai identitas perusahaan utama | Sekarang `Chen Digital` dan `Chen Retail` runtuh ke `chen` yang sama. Dampaknya terbatas (bobot org cuma 0,12) tapi tidak elegan. Domain jauh lebih stabil daripada nama dagang | Kecil |
| 7 | **Kunci blocking cadangan berbasis nama+perusahaan** untuk baris tanpa email **dan** telepon, hasilnya langsung ke zona review | Di dataset ini dampaknya **nol** (email & telepon terisi 100%), tapi di produksi asumsi itu rapuh — baris tanpa keduanya sekarang **mustahil** terdeteksi | Kecil |

## 4.3 Prioritas rendah / skala besar

| # | Improvement | Kapan relevan |
|---|---|---|
| 8 | **Blocking di sisi database** (`GROUP BY phone_key`) + scoring per blok secara streaming | Sekarang semuanya di memori. 2.049 baris muat nyaman; pada ~500 ribu baris `candidate_pairs()` sebagai `set` jadi masalah. Struktur kode sudah mendukung — `build_blocks()` sudah terpisah dari `score_pair()` |
| 9 | **Monitoring drift**: alert kalau `needs_llm_review` naik melewati ambang, atau kalau distribusi confidence mulai menumpuk di zona tengah | Begitu pipeline jalan berulang, bukan sekali |
| 10 | **Golden record versioning** — simpan riwayat setiap merge agar bisa dibatalkan per-field, bukan per-grup | Kalau merge sudah auto dan volumenya besar |
| 11 | **FTS5 untuk `q`** menggantikan `LIKE '%…%'` | `LIKE` dengan wildcard di depan tidak bisa memakai index — ia memindai. Di 2.049 baris itu 0,12 ms, jadi tidak masalah sekarang. Di ratusan ribu baris, FTS5 adalah langkah berikutnya, bukan menambah index |
| 12 | **Recompute grup duplikat setelah ingest** | Grup di tabel adalah snapshot dari pipeline offline. Lead yang masuk lewat ingest sudah dicek satu-satu terhadap DB, tapi grup lama tidak dihitung ulang — di produksi ini perlu job berkala, bukan perhitungan per request |

## 4.4 Di luar scope — tidak akan dikerjakan

README menyebutnya eksplisit: autentikasi/user role, integrasi analytics/GA, webhook
di luar satu endpoint ingest, UI audit-log lengkap, tooling migrasi HubSpot, dan urusan
produksi (deployment/scaling/monitoring).

---

## Catatan penggunaan LLM

Sampai titik ini **tidak ada panggilan LLM berbayar yang dipakai** — biaya kredit
**nol**. Seluruh klasifikasi dan dedup berjalan dengan rules + fuzzy matching lokal
(`rapidfuzz`).

Ini keputusan desain, bukan penghematan: untuk 92,1% baris, rules memberi hasil
deterministik yang bisa dites — sifat yang tidak diberikan LLM. LLM disiapkan secara
spesifik untuk 162 baris yang memang butuh penilaian, dan `needs_llm_review` menandai
persis baris mana. Kalau nanti dijalankan, providernya akan dicatat beserta perkiraan
biayanya.

---

## Lampiran — ringkasan semua keputusan dalam satu tabel

| Keputusan | Alternatif yang ditolak | Alasan |
|---|---|---|
| Tandai duplikat, jangan hapus | auto-merge | biaya kesalahan asimetris; 41% grup punya info komplementer |
| Rules dulu, LLM untuk sisa | LLM untuk semua | deterministik, bisa dites, dan berani bilang "tidak tahu" |
| Identity anchor wajib | ambang kemiripan nama | nama salah di dua arah: 11 false positive di ambang 80%, sementara duplikat asli `J. Yoon`↔`Ji-woo Yoon` cuma 63% |
| Blocking deterministik | embeddings + ANN | duplikatnya re-entry, bukan variasi semantik; bisa dijelaskan |
| Bersihkan hanya yang punya jawaban benar | imputasi menyeluruh | data kosong yang jujur > data terisi yang dikarang |
| Zona review 0,45–0,90 | satu ambang tunggal | kelas "ambigu sejati" memang ada; 17 pasangan bisa ditinjau manusia |
| Dua representasi per entitas | timpa yang asli | reviewer butuh bentuk asli, mesin butuh bentuk kanonik |
| SQLite | Postgres / in-memory | butuh persistensi + SQL, tidak butuh concurrency |
| Ingest pakai skor yang sama | logika dedup terpisah | mencegah dua jalur menyimpang diam-diam |
