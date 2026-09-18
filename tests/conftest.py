"""Fixture DB untuk tes API.

Setiap tes dapat file DB sendiri di tmp_path, bukan `:memory:` dan bukan
out/leads.db. Alasannya dua:

1. `:memory:` tidak bisa dipakai karena `db.DB_PATH` dicek keberadaannya saat
   lifespan startup -- dan mengakali itu berarti menguji jalur yang berbeda
   dari yang dipakai produksi.
2. out/leads.db tidak boleh dipakai karena tes ingest MENULIS. Tes yang
   mengotori artefak asli akan membuat angka di dokumentasi ikut bergeser.

Isinya subset kecil yang dirancang tangan (bukan 2.049 baris asli): tes harus
gagal karena logikanya salah, bukan karena data seed kebetulan berubah.
"""
import sys, json
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

import db as db_mod
from clean_leads import build_record


def row(record_id, first, last, email, phone, company, country="Singapore",
        status="New", owner="Wei Chen", notes="", full="", job="", modified=""):
    return {
        "Record ID": record_id, "First Name": first, "Last Name": last, "Full Name": full,
        "Job Title": job, "Company Name": company, "Email": email, "Phone Number": phone,
        "Country/Region": country, "Lead Status": status, "Lifecycle Stage": "Lead",
        "Original Source": "", "Contact Owner": owner, "Create Date": "2026-01-15",
        "Last Modified Date": modified, "Lead Score": "", "Notes": notes,
    }


# Subset yang sengaja memuat tiap kasus sulit yang perlu diuji:
SEED_ROWS = [
    # 1-2: duplikat jelas -- email sama, format telepon beda, nama bentuk inisial
    row("100000001", "Joon", "Diallo", "joond@huanganalytics.co", "+65 8123 4567",
        "Huang Analytics & Co", job="Head of Ops", modified="2026-03-01"),
    row("100000002", "", "", "joond@huanganalytics.co", "65-8123-4567",
        "Huang Analytics Pte. Ltd.", full="J. Diallo"),
    # 3-4: orang BERBEDA, nama mirip + perusahaan sama (jebakan klasik)
    row("100000003", "Marcus", "Ho", "m.ho@wongrobotics.io", "+65 9111 2222", "Wong Robotics"),
    row("100000004", "Marcus", "Ho", "marcus.ho2@wongrobotics.io", "+44 20 7946 0100",
        "Wong Robotics", country="United Kingdom"),
    # 5: lead sendirian, tanpa kembaran
    row("100000005", "Priya", "Nair", "priya@lunartextiles.com", "+91 98765 43210",
        "Lunar Textiles Ltd", country="India", status="Qualified", owner="Grace Osei",
        notes="Met at the SaaStr Annual booth, scanned QR code"),
    # 6: field sengaja dikosongi -- untuk menguji enrich saat ingest
    row("100000006", "Karim", "Toure", "k.toure@liutrading.biz", "+61 462 210 338",
        "Liu Trading Studio", country="Australia"),
]


@pytest.fixture
def api_db(tmp_path, monkeypatch):
    """DB terisi + monkeypatch DB_PATH supaya app memakainya."""
    path = tmp_path / "test_leads.db"
    monkeypatch.setattr(db_mod, "DB_PATH", path)

    con = db_mod.connect(path)
    db_mod.init_schema(con)
    recs = [build_record(r) for r in SEED_ROWS]
    db_mod.insert_many(con, recs)

    # satu grup duplikat precomputed (baris 1 & 2)
    payload = {"group_id": "G0001", "size": 2, "group_confidence": 0.98,
               "suggested_master_record_id": "100000001",
               "members": [{"record_id": "100000001", "name": "Joon Diallo"},
                           {"record_id": "100000002", "name": "J. Diallo"}],
               "evidence": [{"a": "100000001", "b": "100000002", "confidence": 0.98,
                             "why": "email identik"}],
               "conflicts": {"company_display": ["Huang Analytics & Co",
                                                 "Huang Analytics Pte. Ltd."]}}
    con.execute("INSERT INTO dedupe_groups VALUES (?,?,?,?,?)",
                ("G0001", 2, 0.98, "100000001", json.dumps(payload)))
    con.executemany("INSERT INTO dedupe_members VALUES (?,?)",
                    [("G0001", "100000001"), ("G0001", "100000002")])
    con.commit()
    con.close()
    return path


@pytest.fixture
def client(api_db, monkeypatch):
    import api as api_mod
    monkeypatch.setattr(api_mod.db, "DB_PATH", api_db)
    from fastapi.testclient import TestClient
    with TestClient(api_mod.app) as c:
        yield c
