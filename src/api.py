"""REST API untuk mini lead management system.

Jalankan:  uvicorn api:app --reload --app-dir src
Dokumen :  http://127.0.0.1:8000/docs

Catatan desain penting ada di docstring masing-masing endpoint; yang berlaku
untuk seluruh file:

* Response memakai istilah kanonik (`lead_status`, `contact_owner`), bukan nama
  kolom HubSpot asli ("Lead Status", "Contact Owner"). Nama kolom itu adalah
  artefak sistem lama; API ini tidak mewariskannya.
* Tidak ada auth (eksplisit out of scope di assignment).
* Penulisan selalu lewat satu transaksi dan mencatat baris di `lead_events`.
"""
from __future__ import annotations
import csv, io, json, sqlite3, sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.responses import StreamingResponse, FileResponse

import db
from clean_leads import build_record, extract_source, norm_status, norm_ws, MERGE_T, REVIEW_T
from matching import rank_matches, enrich, decide
from schemas import (LeadPatch, FormSubmission, SourceExtractRequest,
                     SourceExtractResponse, DedupeCandidatesRequest)

STATE: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Buka koneksi sekali saat startup, bukan per request.

    SQLite di sini dipakai satu proses; membuka koneksi tiap request berarti
    membayar ongkos buka file berulang kali tanpa manfaat. `check_same_thread`
    sudah dimatikan di `db.connect`, dan setiap penulisan dibungkus transaksi.
    """
    if not db.DB_PATH.exists():
        raise RuntimeError(
            f"{db.DB_PATH} belum ada. Jalankan dulu:\n"
            "  python src/clean_leads.py && python src/load_db.py")
    STATE["con"] = db.connect()
    db.init_schema(STATE["con"])
    yield
    STATE["con"].close()


app = FastAPI(
    title="Mini Lead Management System",
    version="1.0.0",
    description="Lead store + dedup + ekstraksi sumber. Dataset: 2.049 lead hasil export CRM.",
    lifespan=lifespan,
)


def get_con() -> sqlite3.Connection:
    return STATE["con"]


Con = Annotated[sqlite3.Connection, Depends(get_con)]


# ---------------------------------------------------------------- query filter

def _where(status, owner, country, channel, q) -> tuple[str, list]:
    """Rakit klausa WHERE. Selalu parameterized -- `q` datang dari user.

    `q` mencari di nama, perusahaan, dan email sekaligus. LIKE sudah cukup di
    skala 2.049 baris (12 ms untuk 100 query); kalau dataset tumbuh ke ratusan
    ribu, FTS5 adalah langkah berikutnya, bukan index tambahan di LIKE.
    """
    clauses, params = [], []
    if status:
        clauses.append("lead_status = ?"); params.append(norm_status(status))
    if owner:
        clauses.append("contact_owner = ?"); params.append(norm_ws(owner))
    if country:
        clauses.append("lower(country) = lower(?)"); params.append(norm_ws(country))
    if channel:
        clauses.append("source_channel = ?"); params.append(channel)
    if q:
        clauses.append("(display_name LIKE ? OR company_display LIKE ? OR email LIKE ?)")
        like = f"%{q.strip()}%"
        params += [like, like, like]
    return (" WHERE " + " AND ".join(clauses) if clauses else ""), params


@app.get("/leads", tags=["leads"], summary="Daftar lead dengan filter")
def list_leads(
    con: Con,
    status:  Annotated[Optional[str], Query(description="Lead Status, dicocokkan setelah dinormalisasi ('new', ' NEW ' -> 'New')")] = None,
    owner:   Annotated[Optional[str], Query(description="Contact Owner")] = None,
    country: Annotated[Optional[str], Query(description="Country/Region, case-insensitive")] = None,
    channel: Annotated[Optional[str], Query(description="Kanal hasil ekstraksi sumber")] = None,
    q:       Annotated[Optional[str], Query(description="Cari di nama / perusahaan / email")] = None,
    limit:   Annotated[int, Query(ge=1, le=500)] = 50,
    offset:  Annotated[int, Query(ge=0)] = 0,
):
    """Filter dinormalisasi sebelum dicocokkan.

    `?status=new`, `?status=NEW`, dan `?status=%20New%20` semuanya mengembalikan
    hasil yang sama. Ini bukan kemewahan: nilai mentah di CSV punya 35 varian
    untuk 7 status, jadi klien yang menyalin nilai dari data asli tetap bisa
    memfilter dengan benar tanpa tahu varian mana yang ia pegang.
    """
    where, params = _where(status, owner, country, channel, q)
    total = con.execute(f"SELECT COUNT(*) c FROM leads{where}", params).fetchone()["c"]
    rows = con.execute(
        f"SELECT * FROM leads{where} ORDER BY CAST(record_id AS INTEGER) LIMIT ? OFFSET ?",
        [*params, limit, offset]).fetchall()
    return {
        "total": total, "limit": limit, "offset": offset,
        "filters_applied": {k: v for k, v in
                            {"status": status, "owner": owner, "country": country,
                             "channel": channel, "q": q}.items() if v},
        "leads": [db.row_to_lead(r) for r in rows],
    }


@app.get("/leads/export", tags=["leads"], summary="Ekspor CSV dari view yang sedang difilter")
def export_leads(
    con: Con,
    status: Optional[str] = None, owner: Optional[str] = None,
    country: Optional[str] = None, channel: Optional[str] = None, q: Optional[str] = None,
):
    """Filter identik dengan GET /leads, tapi tanpa limit -- ekspor mengambil
    seluruh view, bukan satu halaman.

    Streaming, bukan membangun string di memori: 2.049 baris memang muat, tapi
    endpoint yang runtuh begitu datanya bertambah adalah bug yang menunggu
    waktu, dan generator di sini tidak lebih rumit.
    """
    where, params = _where(status, owner, country, channel, q)
    fields = ["record_id", "display_name", "job_title", "company_display", "email",
              "phone_e164", "country", "lead_status", "lifecycle_stage", "contact_owner",
              "create_date", "last_modified_date", "lead_score",
              "source_channel", "source_detail", "source_confidence", "notes"]

    def rows():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(fields)
        yield buf.getvalue(); buf.seek(0); buf.truncate(0)
        for r in con.execute(f"SELECT * FROM leads{where} ORDER BY CAST(record_id AS INTEGER)", params):
            w.writerow([r[f] for f in fields])
            yield buf.getvalue(); buf.seek(0); buf.truncate(0)

    return StreamingResponse(
        rows(), media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="leads_export.csv"'})


@app.get("/leads/{record_id}", tags=["leads"], summary="Detail satu lead")
def get_lead(record_id: str, con: Con):
    """Selain field lead, ikut dikembalikan grup duplikatnya kalau ada.

    Alasannya: pertanyaan "apakah lead ini duplikat?" hampir selalu muncul
    bersamaan dengan membuka detailnya. Memaksa klien memanggil endpoint kedua
    untuk itu hanya menambah bolak-balik tanpa menambah informasi.
    """
    row = con.execute("SELECT * FROM leads WHERE record_id = ?", (record_id,)).fetchone()
    if row is None:
        raise HTTPException(404, f"Lead {record_id} tidak ditemukan")
    lead = db.row_to_lead(row)

    gm = con.execute("SELECT group_id FROM dedupe_members WHERE record_id = ?", (record_id,)).fetchone()
    lead["duplicate_group"] = None
    if gm:
        g = con.execute("SELECT payload FROM dedupe_groups WHERE group_id = ?", (gm["group_id"],)).fetchone()
        lead["duplicate_group"] = json.loads(g["payload"])

    events = con.execute(
        "SELECT at, action, detail FROM lead_events WHERE record_id = ? ORDER BY id DESC LIMIT 20",
        (record_id,)).fetchall()
    lead["history"] = [dict(e) for e in events]
    return lead


@app.patch("/leads/{record_id}", tags=["leads"], summary="Ubah status, owner, atau notes")
def patch_lead(record_id: str, patch: LeadPatch, con: Con):
    """`lead_status` dinormalisasi sebelum disimpan.

    Klien boleh mengirim "qualified" atau " QUALIFIED "; yang tersimpan tetap
    "Qualified". Kalau tidak, DB akan pelan-pelan terisi ulang dengan 35 varian
    yang sama seperti data aslinya -- masalah yang baru saja kita bereskan.

    Nilai di luar 7 status kanonik tidak ditolak, hanya disimpan apa adanya
    (dan tampil sebagai kategori sendiri di dashboard). Menolaknya berarti
    memutuskan bahwa daftar status tidak akan pernah bertambah, dan itu bukan
    keputusan yang pantas diambil oleh lapisan penyimpanan.
    """
    fields = {k: v for k, v in patch.model_dump(exclude_unset=True).items() if v is not None}
    if not fields:
        raise HTTPException(400, "Tidak ada field yang diubah. Field yang bisa diubah: "
                                 + ", ".join(sorted(db.PATCHABLE)))
    bad = set(fields) - db.PATCHABLE
    if bad:
        raise HTTPException(400, f"Field tidak bisa diubah lewat PATCH: {sorted(bad)}")

    row = con.execute("SELECT * FROM leads WHERE record_id = ?", (record_id,)).fetchone()
    if row is None:
        raise HTTPException(404, f"Lead {record_id} tidak ditemukan")

    if "lead_status" in fields:
        fields["lead_status"] = norm_status(fields["lead_status"])
    if "contact_owner" in fields:
        fields["contact_owner"] = norm_ws(fields["contact_owner"])

    before = {k: row[k] for k in fields}
    changed = {k: v for k, v in fields.items() if v != before[k]}
    if changed:
        sets = ", ".join(f"{k} = ?" for k in changed)
        con.execute(f"UPDATE leads SET {sets} WHERE record_id = ?",
                    [*changed.values(), record_id])
        db.log_event(con, record_id, "patch",
                     json.dumps({k: [before[k], v] for k, v in changed.items()}, ensure_ascii=False))
        con.commit()

    row = con.execute("SELECT * FROM leads WHERE record_id = ?", (record_id,)).fetchone()
    return {"updated": sorted(changed), "unchanged": sorted(set(fields) - set(changed)),
            "lead": db.row_to_lead(row)}


# ---------------------------------------------------------------- ingest

def _record_from_submission(s: FormSubmission, record_id: str = "") -> dict:
    """Petakan payload form ke bentuk baris CSV, lalu lewatkan ke `build_record`.

    Sengaja memetakan ke nama kolom CSV alih-alih membangun record langsung:
    dengan begitu lead dari form melewati jalur normalisasi yang persis sama
    dengan lead dari seed. Satu jalur, satu perilaku.

    `name` dipetakan ke Full Name, bukan dipecah di sini -- `split_name` sudah
    menangani bentuk inisial ("J. Diallo") dan itu logika yang tidak perlu
    diduplikasi.
    """
    return build_record({
        "Record ID": record_id,
        "First Name": "", "Last Name": "", "Full Name": s.name,
        "Job Title": "", "Company Name": s.company,
        "Email": s.email, "Phone Number": s.phone,
        "Country/Region": s.country,
        "Lead Status": "New", "Lifecycle Stage": "Lead",
        "Original Source": "", "Contact Owner": "",
        "Create Date": s.submitted_at, "Last Modified Date": s.submitted_at,
        "Lead Score": "", "Notes": s.message,
        "Page URL": s.page_url,
    })


@app.post("/leads/ingest", tags=["ingest"], status_code=200,
          summary="Terima form submission: buat lead baru ATAU perkaya yang sudah ada")
def ingest(sub: FormSubmission, con: Con,
           dry_run: Annotated[bool, Query(description="Hitung keputusan tanpa menulis apa pun")] = False):
    """Dedup dulu, tulis kemudian. Ini inti endpoint ini.

    49 dari 90 entri di `website_form_submissions.json` adalah orang yang sudah
    ada di seed. Ingest tanpa dedup akan menggandakan 54% payload -- persis
    masalah yang sedang kita coba selesaikan, tapi masuk lewat pintu depan.

    Tiga keputusan, ambangnya sama dengan pipeline offline:

    | confidence | keputusan | efek |
    |---|---|---|
    | >= 0.90 | `merged`  | lead lama diperkaya, TIDAK ada baris baru |
    | >= 0.45 | `created_pending_review` | lead baru dibuat, TAPI ditandai kembar |
    | <  0.45 | `created` | lead baru, bersih |

    Zona tengah sengaja **membuat** lead, bukan menahannya. Form submission
    adalah orang nyata yang sedang menunggu ditelepon; menahannya di antrian
    review berarti prospek hangat menganggur sementara seseorang memutuskan.
    Membuat lead lalu menandainya membalik biaya kesalahan ke sisi yang benar:
    duplikat yang ditandai bisa digabung nanti, prospek yang hilang tidak bisa.
    """
    rec = _record_from_submission(sub)
    matches = rank_matches(con, rec)
    best = matches[0] if matches else None
    action = decide(best["confidence"]) if best else "distinct"

    if action == "merge" and not dry_run:
        existing = db.row_to_lead(
            con.execute("SELECT * FROM leads WHERE record_id = ?", (best["record_id"],)).fetchone())
        updates, filled = enrich(existing, rec)
        if updates:
            sets = ", ".join(f"{k} = ?" for k in updates)
            con.execute(f"UPDATE leads SET {sets} WHERE record_id = ?",
                        [*updates.values(), best["record_id"]])
        db.log_event(con, best["record_id"], "ingest_merge",
                     json.dumps({"from_form": sub.email, "confidence": best["confidence"],
                                 "fields_filled": filled}, ensure_ascii=False))
        con.commit()
        row = con.execute("SELECT * FROM leads WHERE record_id = ?", (best["record_id"],)).fetchone()
        return {"action": "merged", "record_id": best["record_id"],
                "matched_with": best, "fields_filled": filled,
                "lead": db.row_to_lead(row), "all_matches": matches}

    if action == "merge" and dry_run:
        return {"action": "would_merge", "record_id": best["record_id"],
                "matched_with": best, "all_matches": matches, "lead": None}

    new_id = db.next_record_id(con)
    rec["record_id"] = new_id
    pending = action == "review"
    if not dry_run:
        db.insert_lead(con, rec)
        db.log_event(con, new_id, "ingest_create",
                     json.dumps({"pending_review": pending,
                                 "closest": best["record_id"] if best else None,
                                 "confidence": best["confidence"] if best else 0.0},
                                ensure_ascii=False))
        if pending:
            gid = f"GI{new_id}"
            con.execute("INSERT OR REPLACE INTO dedupe_groups "
                        "(group_id, size, group_confidence, suggested_master, payload) VALUES (?,?,?,?,?)",
                        (gid, 2, best["confidence"], best["record_id"],
                         json.dumps({"group_id": gid, "size": 2,
                                     "group_confidence": best["confidence"],
                                     "suggested_master_record_id": best["record_id"],
                                     "origin": "ingest",
                                     "members": [{"record_id": best["record_id"],
                                                  "name": best["display_name"]},
                                                 {"record_id": new_id,
                                                  "name": rec["display_name"]}],
                                     "evidence": [{"a": best["record_id"], "b": new_id,
                                                   "confidence": best["confidence"],
                                                   "why": best["why"],
                                                   "signals": best["signals"]}]},
                                    ensure_ascii=False)))
            con.executemany("INSERT OR REPLACE INTO dedupe_members (group_id, record_id) VALUES (?,?)",
                            [(gid, best["record_id"]), (gid, new_id)])
        con.commit()

    prefix = "would_create" if dry_run else "created"
    return {"action": f"{prefix}_pending_review" if pending else prefix,
            "record_id": None if dry_run else new_id,
            "matched_with": best, "all_matches": matches,
            "lead": None if dry_run else rec}


@app.post("/leads/dedupe-candidates", tags=["dedup"],
          summary="Grup duplikat, atau cek satu lead terhadap DB")
def dedupe_candidates(req: DedupeCandidatesRequest, con: Con):
    """Dua mode dalam satu endpoint.

    **Tanpa `lead`** -- kembalikan grup hasil pipeline offline, urut confidence.
    Grup ini dihitung sekali untuk 2.049 baris; menghitung ulang per request
    akan memakan waktu ~detik tanpa hasil yang berbeda.

    **Dengan `lead`** -- dry-run: skor satu record terhadap isi DB lewat blocking
    index yang sama, tanpa menulis apa pun. Inilah yang dipanggil kalau sebuah
    form ingin tahu "apakah orang ini sudah ada?" sebelum benar-benar mengirim.
    """
    if req.lead is not None:
        rec = _record_from_submission(req.lead)
        matches = rank_matches(con, rec, min_confidence=req.min_confidence)[:req.limit]
        return {"mode": "single_lead",
                "thresholds": {"merge": MERGE_T, "review": REVIEW_T},
                "would_action": decide(matches[0]["confidence"]) if matches else "distinct",
                "candidates": matches}

    rows = con.execute(
        "SELECT payload FROM dedupe_groups WHERE group_confidence >= ? "
        "ORDER BY group_confidence DESC, group_id LIMIT ?",
        (req.min_confidence, req.limit)).fetchall()
    total = con.execute("SELECT COUNT(*) c FROM dedupe_groups WHERE group_confidence >= ?",
                        (req.min_confidence,)).fetchone()["c"]
    return {"mode": "precomputed_groups", "total": total, "returned": len(rows),
            "thresholds": {"merge": MERGE_T, "review": REVIEW_T},
            "groups": [json.loads(r["payload"]) for r in rows]}


@app.post("/source/extract", tags=["source"], response_model=SourceExtractResponse,
          summary="Ekstrak kanal + detail dari teks bebas")
def source_extract(req: SourceExtractRequest):
    """Fungsi ekstraksi yang sama yang dipakai pipeline, diekspos sebagai endpoint.

    `needs_llm_review: true` berarti rule tidak mengenali teksnya -- itu jawaban
    "tidak tahu" yang jujur, bukan kegagalan. Untuk teks seperti "Saw our post
    about replacing hubspot and commented", sumbernya memang tidak bisa
    ditentukan dari teks itu sendiri, dan menebak akan lebih buruk daripada
    mengaku tidak tahu.
    """
    return extract_source(req.text, req.original_source, req.page_url)


@app.get("/dashboard", tags=["dashboard"], summary="Hitungan lead per status dan per kanal")
def dashboard(con: Con):
    """Agregasi di SQL, bukan di Python.

    Bukan soal performa di 2.049 baris (bedanya milidetik), tapi soal siapa
    yang memegang kebenaran: kalau hitungan dashboard dan hitungan `GET /leads`
    berasal dari dua jalur berbeda, cepat atau lambat keduanya tidak cocok dan
    tidak ada yang tahu mana yang benar.
    """
    def group(col):
        return {r[col] or "(kosong)": r["c"] for r in con.execute(
            f"SELECT {col}, COUNT(*) c FROM leads GROUP BY {col} ORDER BY c DESC")}

    total = con.execute("SELECT COUNT(*) c FROM leads").fetchone()["c"]
    dupes = con.execute("SELECT COUNT(*) c FROM dedupe_groups").fetchone()["c"]
    in_groups = con.execute("SELECT COUNT(DISTINCT record_id) c FROM dedupe_members").fetchone()["c"]
    needs_llm = con.execute("SELECT COUNT(*) c FROM leads WHERE source_needs_llm = 1").fetchone()["c"]
    mean_conf = con.execute("SELECT AVG(source_confidence) a FROM leads").fetchone()["a"]

    return {
        "total_leads": total,
        "by_status": group("lead_status"),
        "by_channel": group("source_channel"),
        "by_country": dict(list(group("country").items())[:10]),
        "by_owner": group("contact_owner"),
        "by_lifecycle_stage": group("lifecycle_stage"),
        "data_quality": {
            "duplicate_groups": dupes,
            "rows_in_duplicate_groups": in_groups,
            "redundant_rows": in_groups - dupes,
            "distinct_people_estimate": total - (in_groups - dupes),
            "source_needs_llm_review": needs_llm,
            "source_needs_llm_pct": round(100 * needs_llm / total, 1) if total else 0,
            "source_mean_confidence": round(mean_conf or 0, 3),
        },
    }


@app.get("/", include_in_schema=False)
def dashboard_page():
    """Halaman HTML statis yang membaca /dashboard lewat fetch.

    Bonus di assignment menyebut "rendered chart is a nice-to-have". Dibuat
    sebagai satu file statis tanpa build step dan tanpa dependency frontend --
    menambahkan React + bundler untuk enam bar chart akan menambah lebih banyak
    hal yang bisa rusak daripada yang ia perlihatkan.
    """
    return FileResponse(Path(__file__).resolve().parent / "static" / "dashboard.html")


@app.get("/health", tags=["meta"], summary="Cek DB hidup dan terisi")
def health(con: Con):
    n = con.execute("SELECT COUNT(*) c FROM leads").fetchone()["c"]
    return {"status": "ok" if n else "empty", "leads": n, "db": str(db.DB_PATH)}
