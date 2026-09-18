"""Penyimpanan SQLite untuk lead store.

Kenapa SQLite dan bukan Postgres: dataset ini 2.049 baris dan penilaian
assignment berjalan di mesin orang lain. SQLite menghilangkan seluruh langkah
setup -- `git clone && uvicorn` langsung jalan. Yang dipakai di sini semuanya
SQL standar (index, LIKE, GROUP BY), jadi pindah ke Postgres nanti tinggal
mengganti driver, bukan menulis ulang query.

Kenapa tabel ini bukan cerminan CSV mentah: kolom kanonik (hasil normalisasi)
dan kolom kunci (blocking key) disimpan sebagai kolom nyata, bukan dihitung
saat query. Blocking key TIDAK BISA dihitung di SQL -- `phone_key` butuh
ekstraksi digit lalu 9 karakter terakhir, `email_key` butuh strip titik/tag.
Menyimpannya berarti `POST /leads/ingest` bisa mencari kandidat lewat index,
bukan memindai 2.049 baris tiap kali form disubmit.
"""
from __future__ import annotations
import sqlite3, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "out" / "leads.db"

# Kolom yang disimpan. Urutannya = urutan kolom tabel.
COLUMNS = [
    "record_id", "first", "last", "display_name", "name_source", "is_initial",
    "job_title", "company_raw", "company_display", "company_core",
    "email", "email_key", "local", "domain", "domain_root",
    "phone_raw", "phone_e164", "phone_key",
    "country", "lead_status", "lifecycle_stage", "original_source", "contact_owner",
    "create_date", "last_modified_date", "lead_score", "notes", "flagged_in_notes",
    "source_channel", "source_detail", "source_confidence", "source_needs_llm",
]

# Field yang boleh diubah lewat PATCH. Sengaja whitelist, bukan blacklist:
# kolom kunci (email_key, phone_key, ...) harus tetap konsisten dengan hasil
# normalisasi, jadi tidak boleh ditulisi langsung dari request.
PATCHABLE = {"lead_status", "contact_owner", "notes"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    record_id          TEXT PRIMARY KEY,
    first              TEXT NOT NULL DEFAULT '',
    last               TEXT NOT NULL DEFAULT '',
    display_name       TEXT NOT NULL DEFAULT '',
    name_source        TEXT NOT NULL DEFAULT '',
    is_initial         INTEGER NOT NULL DEFAULT 0,
    job_title          TEXT NOT NULL DEFAULT '',
    company_raw        TEXT NOT NULL DEFAULT '',
    company_display    TEXT NOT NULL DEFAULT '',
    company_core       TEXT NOT NULL DEFAULT '',
    email              TEXT NOT NULL DEFAULT '',
    email_key          TEXT NOT NULL DEFAULT '',
    local              TEXT NOT NULL DEFAULT '',
    domain             TEXT NOT NULL DEFAULT '',
    domain_root        TEXT NOT NULL DEFAULT '',
    phone_raw          TEXT NOT NULL DEFAULT '',
    phone_e164         TEXT NOT NULL DEFAULT '',
    phone_key          TEXT NOT NULL DEFAULT '',
    country            TEXT NOT NULL DEFAULT '',
    lead_status        TEXT NOT NULL DEFAULT '',
    lifecycle_stage    TEXT NOT NULL DEFAULT '',
    original_source    TEXT NOT NULL DEFAULT '',
    contact_owner      TEXT NOT NULL DEFAULT '',
    create_date        TEXT NOT NULL DEFAULT '',
    last_modified_date TEXT NOT NULL DEFAULT '',
    lead_score         TEXT NOT NULL DEFAULT '',
    notes              TEXT NOT NULL DEFAULT '',
    flagged_in_notes   INTEGER NOT NULL DEFAULT 0,
    source_channel     TEXT NOT NULL DEFAULT '',
    source_detail      TEXT NOT NULL DEFAULT '',
    source_confidence  REAL NOT NULL DEFAULT 0,
    source_needs_llm   INTEGER NOT NULL DEFAULT 0
);

-- Index untuk filter di GET /leads.
CREATE INDEX IF NOT EXISTS ix_leads_status  ON leads(lead_status);
CREATE INDEX IF NOT EXISTS ix_leads_owner   ON leads(contact_owner);
CREATE INDEX IF NOT EXISTS ix_leads_country ON leads(country);
CREATE INDEX IF NOT EXISTS ix_leads_channel ON leads(source_channel);

-- Index untuk blocking saat ingest. Inilah yang membuat dedup online tetap
-- O(ukuran blok) alih-alih O(n) scan penuh.
CREATE INDEX IF NOT EXISTS ix_leads_phone_key ON leads(phone_key);
CREATE INDEX IF NOT EXISTS ix_leads_email_key ON leads(email_key);
CREATE INDEX IF NOT EXISTS ix_leads_email     ON leads(email);
CREATE INDEX IF NOT EXISTS ix_leads_dom_last  ON leads(domain_root, last);

-- Grup duplikat hasil pipeline offline, disimpan supaya
-- POST /leads/dedupe-candidates bisa menjawab tanpa menghitung ulang.
CREATE TABLE IF NOT EXISTS dedupe_groups (
    group_id          TEXT PRIMARY KEY,
    size              INTEGER NOT NULL,
    group_confidence  REAL    NOT NULL,
    suggested_master  TEXT    NOT NULL,
    payload           TEXT    NOT NULL   -- JSON grup lengkap (members, evidence, conflicts)
);
CREATE INDEX IF NOT EXISTS ix_groups_conf ON dedupe_groups(group_confidence DESC);

-- Baris mana ikut grup mana. Dipakai GET /leads/:id untuk menampilkan
-- "lead ini punya kemungkinan duplikat" tanpa memindai seluruh payload JSON.
CREATE TABLE IF NOT EXISTS dedupe_members (
    group_id  TEXT NOT NULL,
    record_id TEXT NOT NULL,
    PRIMARY KEY (group_id, record_id)
);
CREATE INDEX IF NOT EXISTS ix_members_record ON dedupe_members(record_id);

-- Jejak perubahan. Bukan audit-log UI (itu out of scope) -- ini hanya tabel
-- append-only supaya PATCH dan hasil merge saat ingest bisa ditelusuri
-- kalau ada yang bertanya "kenapa lead ini berubah?".
CREATE TABLE IF NOT EXISTS lead_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id  TEXT NOT NULL,
    at         TEXT NOT NULL,
    action     TEXT NOT NULL,
    detail     TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_events_record ON lead_events(record_id);
"""


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    # DB_PATH dibaca saat dipanggil, BUKAN sebagai nilai default argumen.
    # Default argumen di-bind sekali saat fungsi didefinisikan, jadi kalau
    # ditulis `path=DB_PATH` tes tidak bisa mengarahkannya ke DB sementara
    # dan akan diam-diam menulis ke out/leads.db yang asli.
    con = sqlite3.connect(path if path is not None else DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    # WAL: baca tidak memblokir tulis. Relevan karena ingest menulis sementara
    # GET /leads mungkin sedang membaca.
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def init_schema(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA)
    con.commit()


def insert_lead(con: sqlite3.Connection, rec: dict) -> None:
    cols = ", ".join(COLUMNS)
    marks = ", ".join("?" * len(COLUMNS))
    con.execute(f"INSERT INTO leads ({cols}) VALUES ({marks})",
                [_coerce(rec.get(c, "")) for c in COLUMNS])


def insert_many(con: sqlite3.Connection, recs: list[dict]) -> None:
    cols = ", ".join(COLUMNS)
    marks = ", ".join("?" * len(COLUMNS))
    con.executemany(f"INSERT OR REPLACE INTO leads ({cols}) VALUES ({marks})",
                    [[_coerce(r.get(c, "")) for c in COLUMNS] for r in recs])


def _coerce(v):
    if isinstance(v, bool):
        return int(v)
    return v if v is not None else ""


def row_to_lead(row: sqlite3.Row) -> dict:
    d = dict(row)
    for b in ("is_initial", "flagged_in_notes", "source_needs_llm"):
        if b in d:
            d[b] = bool(d[b])
    return d


def log_event(con: sqlite3.Connection, record_id: str, action: str, detail: str = "") -> None:
    from datetime import datetime, timezone
    con.execute("INSERT INTO lead_events (record_id, at, action, detail) VALUES (?,?,?,?)",
                (record_id, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 action, detail))


def next_record_id(con: sqlite3.Connection) -> str:
    """Record ID seed berupa angka berurutan (100234833...). Lead baru melanjutkan
    urutan itu supaya ID tetap satu ruang, bukan dua skema yang bercampur."""
    row = con.execute("SELECT MAX(CAST(record_id AS INTEGER)) AS m FROM leads").fetchone()
    return str((row["m"] or 100000000) + 1)
