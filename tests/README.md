# `tests/` — 68 test, fokus pada kasus ambigu

```bash
conda activate WIZ.AI
python -m pytest -q          # 28 pipeline + 40 API
```

| File | Isi |
|---|---|
| `test_clean_leads.py` | 28 test — normalisasi, ekstraksi sumber, skor dedup |
| `test_api.py` | 40 test — 9 endpoint, jalur ingest, isolasi DB |
| `conftest.py` | fixture `api_db` + `client` — DB sementara di `tmp_path` |

README assignment meminta *"enough to show you tested the ambiguous cases, not only
the happy path."* Test happy path (`"New " → "New"`) ada tapi minoritas — yang penting
adalah kasus yang bisa salah ke dua arah.

## Yang dijaga

**Dedup — false positive**

| Test | Kasus |
|---|---|
| `test_same_name_same_company_but_different_phone_and_email_stays_in_review` | jebakan Marcus Ho |
| `test_siblings_same_surname_same_company_not_merged` | Freya vs Sophia Al-Sayed |
| `test_shared_phone_but_clearly_different_person_is_capped` | Aturan Keras #2 |

**Dedup — false negative**

| Test | Kasus |
|---|---|
| `test_initial_name_form_matches_full_first_name` | `J. Yoon` ↔ `Ji-woo Yoon` (similarity cuma 63%) |
| `test_same_person_different_email_localpart_but_same_phone_is_high_confidence` | localpart beda, telepon sama |
| `test_phone_format_difference_alone_does_not_break_match` | `+34 696 235 827` ↔ `34696235827` |

**Ekstraksi sumber**

| Test | Kasus |
|---|---|
| `test_google_ad_is_website_not_organic_search` | paid ≠ organic — kesalahan atribusi yang menyesatkan budget |
| `test_unmatched_text_is_flagged_for_llm_not_guessed` | sistem berani bilang "tidak tahu" |
| `test_generic_original_source_is_not_trusted_blindly` | `Other Campaigns` sengaja tidak dipetakan |
| `test_unmatched_text_falls_back_to_trustworthy_original_source` | `Social Media` → LinkedIn boleh dipercaya |
| `test_organic_search_beats_landing_page_mention` | urutan prioritas channel |
| `test_linkedin_wins_over_generic_website_words` | override LinkedIn > Website |
| `test_duplicate_marker_stripped_before_classification` | penanda duplikat tidak mengotori ekstraksi |

**Normalisasi**

| Test | Kasus |
|---|---|
| `test_date_three_formats_converge` | 3 format → 1 ISO |
| `test_unparseable_date_returns_blank_not_crash` | format ke-4 tidak membuat pipeline mati |
| `test_company_core_strips_legal_suffix_variants` | `Foster Studio`/`Trading`/`Partners` → `foster` |
| `test_company_display_repairs_generator_artifacts` | `and and` → `&` |
| `test_email_key_keeps_different_localparts_distinct` | normalisasi tidak kebablasan |
| `test_status_unknown_value_is_preserved_not_silently_dropped` | nilai asing tidak dipaksa jadi `Other` |

## API — yang dijaga

Test API dijalankan di atas **seed 6 baris yang dirancang tangan**, bukan data asli.
Alasannya: kalau pipeline diubah dan hasil dedup bergeser, test yang bersandar pada data
asli akan gagal karena *seed*-nya berubah, bukan karena logikanya salah. Enam baris itu
berisi jebakan spesifik — dua duplikat jelas, dua orang berbeda bernama sama, satu lead
sendirian, satu dengan field kosong untuk menguji `enrich`.

**Ingest — inti deliverable #1**

| Test | Kasus |
|---|---|
| `test_ingest_existing_person_does_not_create_a_new_row` | payload orang yang sudah ada → merge, bukan insert |
| `test_ingest_is_idempotent` | kirim dua kali → tetap satu baris |
| `test_ingest_fills_empty_fields_but_never_overwrites` | enrich hanya mengisi yang kosong |
| `test_ingest_ambiguous_match_creates_lead_but_flags_it` | zona review → tetap dibuat, tapi ditandai |

**Batas & keamanan**

| Test | Kasus |
|---|---|
| `test_q_with_sql_metacharacters_is_not_injected` | `q = "'; DROP TABLE leads; --"` tidak merusak apa pun |
| `test_patch_rejects_non_patchable_field` | `PATCH` di luar 3 field yang diizinkan ditolak |
| `test_patch_normalizes_status_before_storing` | `" new "` masuk sebagai `New`, bukan varian ke-36 |
| `test_export_route_is_not_shadowed_by_the_id_route` | urutan deklarasi route tidak bisa tertukar diam-diam |

**Konsistensi antar endpoint**

| Test | Kasus |
|---|---|
| `test_dashboard_counts_match_the_lead_list` | angka dashboard = hasil `GET /leads`, bukan hitungan terpisah |
| `test_pagination_does_not_lose_or_repeat_rows` | `limit`/`offset` menutupi seluruh himpunan, tanpa tumpang tindih |
| `test_source_extract_matches_the_example_in_the_assignment` | contoh di ASSIGNMENT.md direproduksi persis |

## Satu catatan desain test

Test jebakan Marcus Ho meng-assert **rentang**, bukan `!=`:

```python
assert REVIEW_T <= conf < MERGE_T
```

Assert "tidak di-merge" akan tetap lolos kalau confidence-nya 0,02 — padahal itu
berarti sistem **yakin** mereka orang berbeda, sedangkan yang benar adalah *sistem
seharusnya ragu*. Yang dites bukan cuma hasilnya, tapi **kadar keyakinannya**.
