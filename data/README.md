# `data/` — Input mentah (read-only)

Dataset sintetis dari penyelenggara assignment. **Jangan diedit.** Seluruh perbaikan
dilakukan di pipeline (`src/clean_leads.py`), bukan dengan menyunting sumber — supaya
setiap transformasi bisa diaudit dan dijalankan ulang dari nol.

| File | Isi |
|---|---|
| `leads_seed.csv` | 2.049 baris × 22 kolom, meniru bentuk export kontak HubSpot |
| `website_form_submissions.json` | 90 submission form website, 10 field per entri |

## `leads_seed.csv` — bentuknya sengaja berantakan

```
Record ID, First Name, Last Name, Full Name, Job Title, Company Name, Email,
Phone Number, Country/Region, City, Lead Status, Lifecycle Stage, Original Source,
Original Source Drill-Down 1, Contact Owner, Create Date, Last Modified Date,
Notes, Annual Revenue, Marketing contact status, GDPR consent, Lead Score
```

Yang perlu diketahui sebelum memakainya:

- **5 kolom kosong total** — `City`, `Original Source Drill-Down 1`, `Annual Revenue`,
  `Marketing contact status`, `GDPR consent`
- **2 bentuk penulisan nama** — 1.942 baris pakai `First`+`Last`, 107 baris pakai
  `Full Name`, dan tidak ada yang pakai keduanya
- **3 format tanggal** dalam satu kolom — `2026-06-02`, `6/4/2026`, `2026-05-20T00:00:00Z`
- **`Lead Status` punya 35 varian** untuk 7 nilai nyata (beda casing & whitespace)
- **`Original Source` 49,5% kosong**, sisanya sering terlalu generik untuk dipakai
- **± 263 baris adalah duplikat** orang yang sudah ada di file yang sama

## `website_form_submissions.json`

```json
{ "form_id": "...", "form_name": "...", "page_url": "...", "submitted_at": "...",
  "name": "...", "email": "...", "phone": "...", "company": "...",
  "country": "...", "message": "..." }
```

Peringatan penting: **`form_id`, `form_name`, dan `page_url` saling bertentangan**
(16 kombinasi yang banyak di antaranya tidak masuk akal), jadi ketiganya tidak bisa
dipercaya sebagai sumber kebenaran channel. Selain itu **49 dari 90 entri sudah ada
di `leads_seed.csv`** — ingest tanpa dedup akan melipatgandakan separuh payload.

Detail lengkap + angkanya: [`../docs/ANALISIS-DATA.md`](../docs/ANALISIS-DATA.md)
