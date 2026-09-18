"""Dedup online: cari kandidat duplikat untuk SATU record, lewat index SQLite.

Pipeline offline (`clean_leads.py`) membangun blok untuk 2.049 baris sekaligus.
Di sini persoalannya kebalikannya: satu form submission masuk, dan kita perlu
tahu apakah orang ini sudah ada -- tanpa memindai seluruh tabel.

Caranya sama persis (blocking key yang identik), hanya arah lookup-nya yang
dibalik: bukan "kelompokkan semua baris menurut kunci", tapi "ambil baris yang
kuncinya sama dengan record ini". Empat query indexed, bukan 2.049 perbandingan.

Fungsi skoringnya sengaja diimpor dari `clean_leads`, bukan disalin. Kalau
Aturan Keras di sana berubah, ingest ikut berubah di detik yang sama.
"""
from __future__ import annotations
import sqlite3

from clean_leads import score_pair, explain, MERGE_T, REVIEW_T, BLOCK_MAX
from db import row_to_lead


def find_candidates(con: sqlite3.Connection, rec: dict, limit_per_block: int = BLOCK_MAX) -> list[dict]:
    """Ambil baris yang berbagi minimal satu blocking key dengan `rec`.

    `limit_per_block` meniru `BLOCK_MAX` di pipeline offline: blok yang terlalu
    besar (mis. ribuan lead dengan domain perusahaan yang sama) tidak informatif
    dan hanya akan membakar waktu. Batas yang sama dipakai supaya perilaku
    online dan offline tidak berbeda.
    """
    found: dict[str, sqlite3.Row] = {}

    def take(sql: str, *params):
        for row in con.execute(sql + " LIMIT ?", (*params, limit_per_block)):
            if row["record_id"] != rec.get("record_id"):
                found[row["record_id"]] = row

    if rec.get("phone_key"):
        take("SELECT * FROM leads WHERE phone_key = ?", rec["phone_key"])
    if rec.get("email_key"):
        take("SELECT * FROM leads WHERE email_key = ?", rec["email_key"])
    if rec.get("email"):
        take("SELECT * FROM leads WHERE email = ?", rec["email"])
    if rec.get("domain_root") and rec.get("last"):
        take("SELECT * FROM leads WHERE domain_root = ? AND lower(last) = lower(?)",
             rec["domain_root"], rec["last"])

    return [row_to_lead(r) for r in found.values()]


def rank_matches(con: sqlite3.Connection, rec: dict, min_confidence: float = 0.0) -> list[dict]:
    """Skor seluruh kandidat, urut dari yang paling meyakinkan."""
    out = []
    for cand in find_candidates(con, rec):
        conf, ev = score_pair(rec, cand)
        if conf < min_confidence:
            continue
        out.append({
            "record_id": cand["record_id"],
            "display_name": cand["display_name"],
            "company": cand["company_display"],
            "email": cand["email"],
            "phone": cand["phone_e164"],
            "confidence": conf,
            "decision": decide(conf),
            "why": explain(conf, ev),
            "signals": ev,
        })
    out.sort(key=lambda m: -m["confidence"])
    return out


def decide(conf: float) -> str:
    if conf >= MERGE_T:
        return "merge"
    if conf >= REVIEW_T:
        return "review"
    return "distinct"


# Field yang boleh diisi dari payload ingest ke lead yang sudah ada.
# Hanya field kosong yang diisi: data yang sudah ada di CRM tidak ditimpa oleh
# form submission, karena form diisi sendiri oleh lead dan sering lebih miskin
# (nama panggilan, telepon pribadi) daripada yang sudah diverifikasi sales.
ENRICHABLE = ["job_title", "company_display", "phone_e164", "country",
              "email", "last_modified_date", "notes"]


def enrich(existing: dict, incoming: dict) -> tuple[dict, list[str]]:
    """Isi field yang KOSONG di `existing` dari `incoming`. Tidak pernah menimpa.

    Ini sisi praktis dari temuan bahwa 41% grup duplikat punya field yang saling
    melengkapi: menggabungkan bukan soal memilih pemenang, tapi soal mengisi
    lubang. Satu-satunya pengecualian adalah `notes`, yang di-append karena
    isinya kronologi -- catatan lama tetap punya nilai setelah ada yang baru.
    """
    updates, filled = {}, []
    for f in ENRICHABLE:
        new = (incoming.get(f) or "").strip()
        if not new:
            continue
        cur = (existing.get(f) or "").strip()
        if f == "notes":
            if new and new not in cur:
                updates[f] = f"{cur}\n{new}".strip()
                filled.append(f)
        elif not cur:
            updates[f] = new
            filled.append(f)
    return updates, filled
