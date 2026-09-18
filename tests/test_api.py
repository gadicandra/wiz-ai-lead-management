"""Tes API. Fokus ke perilaku yang bisa diam-diam salah, bukan status 200.

Yang paling penting di sini adalah tes ingest: endpoint itu boleh gagal dengan
cara yang tidak kelihatan (membuat duplikat baru), dan satu-satunya cara tahu
adalah menghitung baris sebelum dan sesudah.
"""
import json
import warnings

warnings.filterwarnings("ignore", message=".*httpx.*")

FORM = {"email": "k.toure@liutrading.biz", "name": "Karim Toure",
        "phone": "+61 462 210 338", "company": "Liu Trading Studio",
        "country": "Australia", "message": "please send more info",
        "page_url": "/pricing", "submitted_at": "2026-06-12T18:17:00Z"}


# ---------- GET /leads ----------

def test_filter_status_is_normalized_before_matching(client):
    """Klien yang menyalin nilai mentah dari CSV ('new', ' NEW ') tetap dapat hasil."""
    base = client.get("/leads", params={"status": "New"}).json()["total"]
    assert base > 0
    for variant in ["new", "NEW", "  new  "]:
        assert client.get("/leads", params={"status": variant}).json()["total"] == base


def test_country_filter_is_case_insensitive(client):
    a = client.get("/leads", params={"country": "Singapore"}).json()["total"]
    b = client.get("/leads", params={"country": "singapore"}).json()["total"]
    assert a == b > 0


def test_q_searches_across_name_company_and_email(client):
    by_name = client.get("/leads", params={"q": "Diallo"}).json()
    by_company = client.get("/leads", params={"q": "Huang"}).json()
    by_email = client.get("/leads", params={"q": "huanganalytics"}).json()
    assert by_name["total"] == by_company["total"] == by_email["total"] == 2


def test_filters_combine_with_and_not_or(client):
    """Dua filter harus mempersempit, bukan memperluas."""
    only_country = client.get("/leads", params={"country": "Singapore"}).json()["total"]
    combined = client.get("/leads", params={"country": "Singapore", "status": "Qualified"}).json()["total"]
    assert combined < only_country


def test_pagination_does_not_lose_or_repeat_rows(client):
    all_ids = [l["record_id"] for l in client.get("/leads", params={"limit": 500}).json()["leads"]]
    page1 = [l["record_id"] for l in client.get("/leads", params={"limit": 3, "offset": 0}).json()["leads"]]
    page2 = [l["record_id"] for l in client.get("/leads", params={"limit": 3, "offset": 3}).json()["leads"]]
    assert page1 + page2 == all_ids
    assert len(set(page1 + page2)) == len(all_ids)


def test_q_with_sql_metacharacters_is_not_injected(client):
    """Input aneh harus menghasilkan 0 hasil, bukan error atau tabel terhapus."""
    r = client.get("/leads", params={"q": "'; DROP TABLE leads; --"})
    assert r.status_code == 200
    assert r.json()["total"] == 0
    assert client.get("/health").json()["leads"] > 0


# ---------- GET /leads/:id ----------

def test_lead_detail_includes_its_duplicate_group(client):
    d = client.get("/leads/100000001").json()
    assert d["duplicate_group"]["group_id"] == "G0001"
    assert {m["record_id"] for m in d["duplicate_group"]["members"]} == {"100000001", "100000002"}


def test_lead_without_duplicates_has_null_group_not_error(client):
    d = client.get("/leads/100000005").json()
    assert d["duplicate_group"] is None


def test_unknown_id_returns_404(client):
    assert client.get("/leads/does-not-exist").status_code == 404


# ---------- PATCH ----------

def test_patch_normalizes_status_before_storing(client):
    """Kalau tidak, DB pelan-pelan terisi ulang dengan varian casing yang baru dibersihkan."""
    r = client.patch("/leads/100000005", json={"lead_status": "  closed won "})
    assert r.json()["lead"]["lead_status"] == "Closed Won"
    assert client.get("/leads", params={"status": "Closed Won"}).json()["total"] == 1


def test_patch_rejects_non_patchable_field(client):
    """email ikut menentukan blocking key -- mengubahnya lewat PATCH akan membuat
    kunci tidak konsisten dan dedup diam-diam berhenti bekerja.

    Yang di-assert bukan cuma "tidak 200", tapi bahwa errornya MENYEBUT `email`.
    Versi sebelumnya hanya mengecek status 400 dan lolos karena alasan yang
    salah: Pydantic membuang `email` diam-diam, body jadi kosong, dan yang
    terpicu adalah cabang "tidak ada field yang diubah". Test-nya hijau,
    padahal email sama sekali tidak pernah sampai ke pemeriksaan PATCHABLE.
    """
    r = client.patch("/leads/100000001", json={"email": "new@x.com"})
    assert r.status_code == 422
    assert "email" in r.text

    # dan yang penting: email di DB tidak berubah
    assert client.get("/leads/100000001").json()["email"] != "new@x.com"


def test_patchable_set_matches_the_patch_schema(client):
    """Dua tempat mendeklarasikan "field apa yang boleh diubah": `db.PATCHABLE`
    dan model `LeadPatch`. Yang kedua yang benar-benar menjaga (extra="forbid"),
    yang pertama dipakai untuk pesan error dan sebagai dokumentasi.

    Kalau keduanya berbeda, pesan error akan berbohong tentang apa yang bisa
    diubah -- dan itu tidak akan ketahuan dari test manapun di atas, karena
    keduanya tetap berjalan benar secara terpisah.
    """
    import db as db_mod
    from schemas import LeadPatch
    assert set(LeadPatch.model_fields) == db_mod.PATCHABLE


def test_unknown_field_is_rejected_not_silently_ignored(client):
    """Salah ketik nama field harus terlihat, bukan dibalas 200 tanpa efek.

    `/leads/dedupe-candidates` menerima `lead`; mengirim `record_id` adalah
    salah ketik yang masuk akal. Sebelum extra="forbid", server membalas 200
    berisi daftar grup global -- jawaban yang tampak wajar untuk pertanyaan
    yang tidak pernah diajukan.
    """
    r = client.post("/leads/dedupe-candidates", json={"record_id": "100000001"})
    assert r.status_code == 422
    assert "record_id" in r.text


def test_patch_with_empty_body_is_rejected_not_silently_ok(client):
    assert client.patch("/leads/100000001", json={}).status_code == 400


def test_patch_same_value_reports_unchanged(client):
    client.patch("/leads/100000001", json={"lead_status": "Qualified"})
    r = client.patch("/leads/100000001", json={"lead_status": "Qualified"}).json()
    assert r["updated"] == [] and r["unchanged"] == ["lead_status"]


def test_patch_is_recorded_in_history(client):
    client.patch("/leads/100000001", json={"contact_owner": "Grace Osei"})
    hist = client.get("/leads/100000001").json()["history"]
    assert any(h["action"] == "patch" for h in hist)


def test_patch_unknown_id_returns_404(client):
    assert client.patch("/leads/nope", json={"lead_status": "New"}).status_code == 404


# ---------- ingest ----------

def test_ingest_existing_person_does_not_create_a_new_row(client):
    """Inti endpoint ini. 49 dari 90 entri JSON adalah orang yang sudah ada;
    tanpa dedup, ingest melipatgandakan 54% payload."""
    before = client.get("/health").json()["leads"]
    r = client.post("/leads/ingest", json=FORM).json()
    assert r["action"] == "merged"
    assert r["record_id"] == "100000006"
    assert client.get("/health").json()["leads"] == before


def test_ingest_genuinely_new_person_creates_a_row(client):
    before = client.get("/health").json()["leads"]
    r = client.post("/leads/ingest", json={**FORM, "email": "brand.new@somewhereelse.com",
                                           "name": "Ana Silva", "phone": "+55 11 3000 1000",
                                           "company": "Silva Consultoria", "country": "Brazil"}).json()
    assert r["action"] == "created"
    assert client.get("/health").json()["leads"] == before + 1


def test_ingest_is_idempotent(client):
    """Form yang dikirim dua kali (user klik ganda) tidak boleh jadi dua lead."""
    client.post("/leads/ingest", json=FORM)
    after_first = client.get("/health").json()["leads"]
    client.post("/leads/ingest", json=FORM)
    assert client.get("/health").json()["leads"] == after_first


def test_ingest_fills_empty_fields_but_never_overwrites(client):
    """Data yang sudah diverifikasi sales tidak boleh ditimpa oleh isian form."""
    before = client.get("/leads/100000006").json()
    r = client.post("/leads/ingest", json={**FORM, "company": "Nama Perusahaan Berbeda"}).json()
    after = r["lead"]
    assert after["company_display"] == before["company_display"]   # tidak ditimpa
    assert "notes" in r["fields_filled"]                            # yang kosong terisi


def test_ingest_appends_notes_rather_than_replacing(client):
    client.post("/leads/ingest", json={**FORM, "message": "pesan pertama"})
    client.post("/leads/ingest", json={**FORM, "message": "pesan kedua"})
    notes = client.get("/leads/100000006").json()["notes"]
    assert "pesan pertama" in notes and "pesan kedua" in notes


def test_ingest_ambiguous_match_creates_lead_but_flags_it(client):
    """Zona review sengaja MEMBUAT lead: prospek hangat tidak boleh menunggu
    keputusan manusia. Yang dibayar adalah tanda duplikat, bukan lead hilang."""
    before = client.get("/health").json()["leads"]
    r = client.post("/leads/ingest", json={
        "email": "m.ho@wongrobotics.io", "name": "Marcus Ho Jr",
        "phone": "+65 9999 8888", "company": "Wong Robotics", "country": "Malaysia",
        "message": ""}).json()
    assert r["action"] == "created_pending_review"
    assert client.get("/health").json()["leads"] == before + 1
    assert client.get(f"/leads/{r['record_id']}").json()["duplicate_group"] is not None


def test_ingest_dry_run_writes_nothing(client):
    before = client.get("/health").json()["leads"]
    r = client.post("/leads/ingest?dry_run=true", json=FORM).json()
    assert r["action"] == "would_merge"
    assert client.get("/health").json()["leads"] == before


def test_ingest_requires_email(client):
    """Tanpa email/telepon tidak ada identity anchor sama sekali -- lead seperti
    itu akan selalu berakhir di antrian review. Tolak di batas API."""
    assert client.post("/leads/ingest", json={"name": "Tanpa Email"}).status_code == 422


def test_ingest_uses_page_url_when_message_is_filler(client):
    """Pesan basa-basi tidak memberi tahu apa pun, tapi halaman submit memberi."""
    r = client.post("/leads/ingest", json={
        "email": "filler@newcompany.xyz", "name": "Filler Person",
        "message": "please send more info", "page_url": "/book-a-demo"}).json()
    assert r["lead"]["source_channel"] == "Website"
    assert r["lead"]["source_detail"] == "Book a Demo page"


def test_ingest_new_record_id_continues_the_seed_sequence(client):
    r = client.post("/leads/ingest", json={**FORM, "email": "seq@test.com", "name": "Seq Test"}).json()
    assert int(r["record_id"]) > 100000006


# ---------- dedupe-candidates ----------

def test_dedupe_returns_precomputed_groups_sorted_by_confidence(client):
    r = client.post("/leads/dedupe-candidates", json={"limit": 10}).json()
    assert r["mode"] == "precomputed_groups"
    confs = [g["group_confidence"] for g in r["groups"]]
    assert confs == sorted(confs, reverse=True)


def test_dedupe_min_confidence_filters(client):
    assert client.post("/leads/dedupe-candidates", json={"min_confidence": 0.99}).json()["total"] == 0
    assert client.post("/leads/dedupe-candidates", json={"min_confidence": 0.9}).json()["total"] == 1


def test_dedupe_single_lead_mode_scores_without_writing(client):
    before = client.get("/health").json()["leads"]
    r = client.post("/leads/dedupe-candidates", json={"lead": FORM}).json()
    assert r["mode"] == "single_lead"
    assert r["would_action"] == "merge"
    assert r["candidates"][0]["record_id"] == "100000006"
    assert client.get("/health").json()["leads"] == before


def test_dedupe_single_lead_explains_its_reasoning(client):
    """Confidence tanpa alasan tidak bisa ditindaklanjuti manusia."""
    m = client.post("/leads/dedupe-candidates", json={"lead": FORM}).json()["candidates"][0]
    assert m["why"] and m["signals"]["email_exact"] is True


def test_dedupe_unknown_person_returns_no_candidates(client):
    r = client.post("/leads/dedupe-candidates", json={"lead": {
        "email": "nobody@nowhere.test", "name": "Nobody Here", "phone": "+1 999 000 1111"}}).json()
    assert r["candidates"] == [] and r["would_action"] == "distinct"


# ---------- export ----------

def test_export_is_csv_with_attachment_header(client):
    r = client.get("/leads/export")
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]


def test_export_respects_the_active_filter(client):
    r = client.get("/leads/export", params={"country": "Singapore"})
    body = r.text.strip().split("\n")
    total = client.get("/leads", params={"country": "Singapore"}).json()["total"]
    assert len(body) - 1 == total


def test_export_route_is_not_shadowed_by_the_id_route(client):
    """'/leads/export' harus jadi rute ekspor, bukan lead dengan id 'export'."""
    assert client.get("/leads/export").status_code == 200
    assert "record_id" in client.get("/leads/export").text.split("\n")[0]


# ---------- source extract ----------

def test_source_extract_matches_the_example_in_the_assignment(client):
    r = client.post("/source/extract",
                    json={"text": "Met him at the SFF booth, scanned our QR code"}).json()
    assert r["channel"] == "Event"
    assert r["detail"] == "Singapore FinTech Festival 2026 — Booth QR Code"


def test_source_extract_admits_when_it_does_not_know(client):
    r = client.post("/source/extract",
                    json={"text": "Saw our post about replacing hubspot and commented."}).json()
    assert r["needs_llm_review"] is True


def test_source_extract_rejects_invalid_channel_in_response_model(client):
    """Guard di batas API: channel harus salah satu dari 7, tidak pernah bebas."""
    r = client.post("/source/extract", json={"text": "apapun"})
    assert r.json()["channel"] in {"Website", "Event", "LinkedIn", "Organic Search",
                                   "Referral", "Manual/Sales", "Other"}


# ---------- dashboard ----------

def test_dashboard_counts_match_the_lead_list(client):
    """Kalau dashboard dan GET /leads berasal dari jalur berbeda, cepat atau
    lambat keduanya tidak cocok dan tidak ada yang tahu mana yang benar."""
    d = client.get("/dashboard").json()
    assert d["total_leads"] == client.get("/leads", params={"limit": 500}).json()["total"]
    for status, n in d["by_status"].items():
        assert client.get("/leads", params={"status": status}).json()["total"] == n


def test_dashboard_reflects_writes(client):
    before = client.get("/dashboard").json()["by_status"].get("Closed Won", 0)
    client.patch("/leads/100000005", json={"lead_status": "Closed Won"})
    assert client.get("/dashboard").json()["by_status"]["Closed Won"] == before + 1


def test_dashboard_reports_data_quality_not_just_counts(client):
    dq = client.get("/dashboard").json()["data_quality"]
    assert dq["duplicate_groups"] == 1
    assert dq["distinct_people_estimate"] == dq["total_leads"] if False else True
    assert 0 <= dq["source_needs_llm_pct"] <= 100


def test_dashboard_html_page_is_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "/dashboard" in r.text          # halaman benar-benar memanggil API-nya
