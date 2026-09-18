"""Isi out/leads.db dari CSV seed + hasil dedup pipeline.

Jalankan:  python src/load_db.py
Prasyarat: python src/clean_leads.py sudah dijalankan (butuh out/dedupe_groups.json).

Idempoten -- DB lama dihapus dan dibangun ulang, jadi menjalankan ini dua kali
menghasilkan state yang identik.
"""
from __future__ import annotations
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from clean_leads import load, ROOT, OUT
import db


def main() -> None:
    groups_path = OUT / "dedupe_groups.json"
    if not groups_path.exists():
        sys.exit("out/dedupe_groups.json belum ada -- jalankan dulu: python src/clean_leads.py")

    if db.DB_PATH.exists():
        db.DB_PATH.unlink()
    for suffix in ("-wal", "-shm"):
        p = db.DB_PATH.with_name(db.DB_PATH.name + suffix)
        if p.exists():
            p.unlink()

    con = db.connect()
    db.init_schema(con)

    recs = load()
    db.insert_many(con, recs)

    groups = json.loads(groups_path.read_text())
    con.executemany(
        "INSERT OR REPLACE INTO dedupe_groups "
        "(group_id, size, group_confidence, suggested_master, payload) VALUES (?,?,?,?,?)",
        [(g["group_id"], g["size"], g["group_confidence"],
          g["suggested_master_record_id"], json.dumps(g, ensure_ascii=False)) for g in groups])
    con.executemany(
        "INSERT OR REPLACE INTO dedupe_members (group_id, record_id) VALUES (?,?)",
        [(g["group_id"], m["record_id"]) for g in groups for m in g["members"]])
    con.commit()

    n_leads = con.execute("SELECT COUNT(*) c FROM leads").fetchone()["c"]
    n_groups = con.execute("SELECT COUNT(*) c FROM dedupe_groups").fetchone()["c"]
    n_members = con.execute("SELECT COUNT(*) c FROM dedupe_members").fetchone()["c"]
    # Checkpoint dulu: dengan WAL, isi tabel masih ada di file -wal sampai
    # di-checkpoint, jadi stat() pada file .db akan melaporkan ~0 MB dan
    # menyesatkan siapa pun yang mengira loadernya gagal.
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    size_mb = db.DB_PATH.stat().st_size / 1024 / 1024
    print(f"{db.DB_PATH.relative_to(ROOT)}  ({size_mb:.1f} MB)")
    print(f"  leads           {n_leads}")
    print(f"  dedupe_groups   {n_groups}")
    print(f"  dedupe_members  {n_members}")
    con.close()


if __name__ == "__main__":
    main()
