# `docs/`

| File | Isi |
|---|---|
| `ANALISIS-DATA.md` | Dokumen utama: temuan → solusi → justifikasi, keputusan pemrosesan, keputusan yang masih terbuka, rencana perbaikan |

Struktur `ANALISIS-DATA.md`:

1. **Bagian 1 — Temuan, Solusi, Justifikasi** · 36 temuan dalam bentuk tabel, masing-masing dengan bukti, solusi, dan alasan pemilihan solusinya
2. **Bagian 2 — Keputusan Pemrosesan** · 7 keputusan pipeline + 10 keputusan lapisan API (§2.5), masing-masing dengan alternatif yang ditolak
3. **Bagian 3 — Keputusan yang Masih Harus Diambil** · keputusan terbuka yang butuh input bisnis atau teknis; yang sudah terjawab oleh API ditandai coret
4. **Bagian 4 — Next Improvement** · rencana perbaikan berurutan menurut rasio nilai/usaha

Setiap angka di dokumen itu bisa diverifikasi dari [`../out/report.json`](../out/report.json).
