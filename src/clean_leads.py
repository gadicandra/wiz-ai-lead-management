"""
Normalisasi + dedup kandidat untuk leads_seed.csv.

Prinsip: pipeline ini TIDAK menghapus baris apa pun. Ia menghasilkan
(a) kolom kanonik hasil normalisasi, (b) grup duplikat berikut confidence
dan alasannya, (c) usulan master record per grup.
Keputusan merge tetap di tangan manusia (human-in-the-loop).

Jalankan:  python src/clean_leads.py
Output  :  out/leads_clean.csv, out/dedupe_groups.json, out/dedupe_review.csv, out/report.json
"""
from __future__ import annotations
import csv, json, re, sys, unicodedata, itertools, collections
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz

ROOT = Path(__file__).resolve().parents[1]
SRC_CSV = ROOT / "data" / "leads_seed.csv"
OUT = ROOT / "out"; OUT.mkdir(exist_ok=True)

# Kolom yang 100% kosong di seluruh 2.049 baris -> tidak dimodelkan.
DROP_ALWAYS_EMPTY = ["City", "Original Source Drill-Down 1",
                     "Annual Revenue", "Marketing contact status", "GDPR consent"]

STATUS_CANON = {"new","contacted","connected","qualified","opportunity","closed won","closed lost"}
LIFECYCLE_CANON = {"lead","marketing qualified lead","sales qualified lead",
                   "opportunity","customer","other"}

# ---------------------------------------------------------------- normalisasi

def norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def norm_status(s: str) -> str:
    v = norm_ws(s).lower()
    return v.title() if v in STATUS_CANON else (norm_ws(s) or "")

def norm_lifecycle(s: str) -> str:
    v = norm_ws(s).lower()
    if not v: return ""
    return {"lead":"Lead","marketing qualified lead":"Marketing Qualified Lead",
            "sales qualified lead":"Sales Qualified Lead","opportunity":"Opportunity",
            "customer":"Customer","other":"Other"}.get(v, norm_ws(s))

def norm_country(s: str) -> str:
    v = norm_ws(s)
    if not v: return ""
    special = {"uae":"UAE","usa":"United States","uk":"United Kingdom"}
    if v.lower() in special: return special[v.lower()]
    # title-case per kata, kecuali kata sambung
    small = {"of","and","the"}
    parts = [w if w.lower() in small else w.capitalize() for w in v.lower().split()]
    return " ".join(parts)

DATE_FORMATS = ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%m/%d/%Y")

def norm_date(s: str) -> str:
    """Kembalikan ISO-8601 UTC. M/D/YYYY diasumsikan US-order (lihat docs)."""
    v = norm_ws(s)
    if not v: return ""
    for fmt in DATE_FORMATS:
        try:
            dt = datetime.strptime(v, fmt)
            return dt.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue
    return ""  # tak terparsir -> kosong, dicatat di report

def norm_email(s: str) -> str:
    return norm_ws(s).lower()

def email_key(s: str) -> str:
    """Localpart tanpa titik/dash/plus-tag + domain. Dipakai sebagai identity anchor."""
    e = norm_email(s)
    if "@" not in e: return e
    local, dom = e.split("@", 1)
    local = local.split("+", 1)[0]
    local = re.sub(r"[.\-_]", "", local)
    return f"{local}@{dom}"

def phone_digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")

def phone_key(s: str) -> str:
    """9 digit terakhir: tahan terhadap beda format +CC / 00CC / tanpa prefix."""
    d = phone_digits(s)
    return d[-9:] if len(d) >= 9 else d

def phone_e164(s: str) -> str:
    d = phone_digits(s)
    if not d: return ""
    if d.startswith("00"): d = d[2:]
    return "+" + d

LEGAL_SUFFIX = (r"\b(pte\.?\s*ltd\.?|ltd\.?|llc|l\.l\.c\.|inc\.?|corp\.?|gmbh|s\.r\.l\.|srl|"
                r"ab|a/s|as|bv|n\.v\.|nv|s\.a\.|sa|plc|co\.?|holdings|group|partners|ventures|"
                r"studio|labs|solutions|digital|trading|retail|freight|analytics|robotics|"
                r"consulting|imports|logistics|textiles|biotech|legal|finance|fintech|"
                r"enterprises|bros|sons|manufacturing)\b")

def company_core(s: str) -> str:
    """Buang suffix legal + konektor supaya 'Foster Studio' == 'Foster Partners' -> 'foster'."""
    v = norm_ws(s).lower()
    v = unicodedata.normalize("NFKD", v).encode("ascii", "ignore").decode()
    v = v.replace("&", " and ")
    v = re.sub(r"[^a-z0-9\s]", " ", v)
    prev = None
    while prev != v:                       # ulangi: "Retail Retail Group" -> "retail"
        prev = v
        v = re.sub(LEGAL_SUFFIX, " ", v)
        v = re.sub(r"\band\b", " ", v)
        v = norm_ws(v)
    return v

def company_display(s: str) -> str:
    """Rapikan artefak generator: 'Chen Digital and and Co' -> 'Chen Digital & Co'."""
    v = norm_ws(s)
    v = re.sub(r"\b(and\s+){2,}", "and ", v, flags=re.I)
    v = re.sub(r"&\s+and\b", "&", v, flags=re.I)
    v = re.sub(r"\band\b", "&", v)
    v = re.sub(r"\b(\w+)\s+\1\b", r"\1", v, flags=re.I)   # 'Retail Retail' -> 'Retail'
    return norm_ws(v)

def split_name(first: str, last: str, full: str):
    """Kembalikan (first, last, display, is_initial_form).

    Baris seed memakai first+last ATAU full, tidak pernah keduanya.
    'J. Diallo' adalah bentuk inisial -> ditandai supaya matcher tidak
    menghukumnya saat dibandingkan dengan 'Joon Diallo'.
    """
    f, l, fu = norm_ws(first), norm_ws(last), norm_ws(full)
    if f or l:
        return f, l, norm_ws(f + " " + l), False
    if not fu:
        return "", "", "", False
    parts = fu.split()
    f2, l2 = parts[0], parts[-1] if len(parts) > 1 else ""
    is_ini = bool(re.fullmatch(r"[A-Za-z]\.?", f2))
    return f2, l2, fu, is_ini

# ---------------------------------------------------------------- source extraction

CHANNEL_RULES = [
    ("Event",          r"\b(booth|qr code|expo|summit|festival|conference|congress|disrupt|"
                       r"web summit|saastr|money\s*20/20|tech week|trade show|meetup)\b"),
    ("Referral",       r"\b(referred by|warm intro|referral|introduced by)\b"),
    ("LinkedIn",       r"\b(linkedin|linked in)\b"),
    ("Manual/Sales",   r"\b(manual(ly)?\b|cold outreach|inbound phone call|added by sales|"
                       r"walked into our office)\b"),
    ("Organic Search", r"\b(organic (google )?search|googled us|google search|seo)\b"),
    ("Website",        r"\b(filled out the form|book(ed)? a demo|book-a-demo|pricing page|"
                       r"homepage|contact page|product tour|case study|blog post|"
                       r"comparison-vs-hubspot|newsletter|landing page)\b"),
    ("Other",          r"\b(info@|general inbox|other\s*-)\b"),
]
PAID_HINT = re.compile(r"\bgoogle ad(s|word)?\b|\bppc\b|\bpaid (search|ad)\b", re.I)
EVENT_NAMES = [
    "Singapore FinTech Festival 2026","Web Summit 2026","TechCrunch Disrupt","Mobile World Congress",
    "SaaStr Annual","Money20/20 Asia","APAC Logistics Summit","Dubai FinTech Week","London Tech Week",
    "Retail Asia Expo",
]
# Singkatan yang dipakai orang sales saat mengetik cepat. Tidak muncul di seed,
# tapi muncul di contoh assignment ("Met him at the SFF booth") -- dan catatan
# yang diketik manusia memang begini bentuknya di dunia nyata.
EVENT_ALIASES = {
    r"\bsff\b": "Singapore FinTech Festival 2026",
    r"\bmwc\b": "Mobile World Congress",
    r"\btc disrupt\b|\btechcrunch\b": "TechCrunch Disrupt",
    r"\bsaastr\b": "SaaStr Annual",
    r"\bmoney\s*20/20\b": "Money20/20 Asia",
}
PAGE_HINT = {
    "book-a-demo":"Book a Demo page","pricing page":"Pricing page","homepage":"Homepage",
    "contact page":"Contact page","product tour":"Product tour page","case study":"Case study page",
    "blog post on lead scoring":"Blog — lead scoring","comparison-vs-hubspot":"Comparison vs HubSpot page",
}

# Halaman tempat form disubmit. Ini fakta yang dicatat server -- beda dengan
# `form_id`/`form_name` yang di dataset ini saling bertentangan (16 kombinasi
# untuk 2 field yang seharusnya 1-1), jadi hanya `page_url` yang dipercaya.
PAGE_URL_HINT = {
    "/book-a-demo": ("Website", "Book a Demo page"),
    "/pricing":     ("Website", "Pricing page"),
    "/contact":     ("Website", "Contact page"),
    "/blog":        ("Website", "Blog"),
}

def extract_source(notes: str, original_source: str = "", page_url: str = "") -> dict:
    """Rules-first. `needs_llm=True` menandai teks yang tidak tertangkap rule.

    `page_url` hanya dipakai sebagai fallback untuk lead dari form submission:
    kalau pesannya basa-basi ("please send more info"), halaman submit tetap
    memberi tahu kita kanalnya adalah Website dan halaman mana persisnya.
    """
    text = re.sub(r"\s*possible duplicate — verify before contacting\.?", "", notes or "").strip()
    low = text.lower()
    hits = [ch for ch, pat in CHANNEL_RULES if re.search(pat, low)]

    channel, detail, conf = "Other", "", 0.5
    if hits:
        channel = hits[0]
        conf = 0.9 if len(hits) == 1 else 0.75

    # Organic vs Paid: 'google ad' bukan organic search
    if PAID_HINT.search(low):
        channel, conf = "Website", 0.85

    # LinkedIn menang atas Website kalau keduanya kena
    if "LinkedIn" in hits:
        channel, conf = "LinkedIn", 0.9

    if channel == "Event":
        ev = next((e for e in EVENT_NAMES if e.lower() in low), "")
        if not ev:
            ev = next((full for pat, full in EVENT_ALIASES.items() if re.search(pat, low)), "")
        qr = "Booth QR Code" if "qr code" in low else "Booth"
        detail = f"{ev} — {qr}" if ev else qr
    elif channel == "Website":
        pg = next((v for k, v in PAGE_HINT.items() if k in low), "")
        detail = (pg + (" — Google Ads" if PAID_HINT.search(low) else "")).strip(" —")
    elif channel == "Organic Search":
        pg = next((v for k, v in PAGE_HINT.items() if k in low), "")
        detail = f"Google organic → {pg}" if pg else "Google organic"
    elif channel == "Referral":
        m = re.search(r"referred by ([A-Z][a-zA-Z\-']+(?: [A-Z][a-zA-Z\-']+)?)", text, re.I)
        detail = f"Referred by {m.group(1)}" if m else "Referral"
    elif channel == "LinkedIn":
        detail = "LinkedIn DM" if "dm" in low else "LinkedIn post engagement"
    elif channel == "Manual/Sales":
        detail = ("Cold outreach call" if "cold outreach" in low else
                  "Walk-in" if "walked into" in low else "Inbound phone call")
    else:
        detail = "General info@ inbox" if "info@" in low else ""

    needs_llm = not hits and not PAID_HINT.search(low)
    if needs_llm:
        conf = 0.3
        # fallback: percaya Original Source kalau ada dan bukan bucket generik
        os_map = {"Organic Search":"Organic Search","Referrals":"Referral",
                  "Social Media":"LinkedIn","Paid Search":"Website","Direct Traffic":"Website"}
        if original_source.strip() in os_map:
            channel, conf, detail = os_map[original_source.strip()], 0.55, f"from Original Source: {original_source.strip()}"
        elif page_url.strip() in PAGE_URL_HINT:
            # Halaman submit adalah bukti perilaku, bukan tebakan: form ini
            # memang dikirim dari halaman tersebut. Lebih kuat dari Original
            # Source yang bucket-nya generik, jadi confidence-nya lebih tinggi.
            channel, detail = PAGE_URL_HINT[page_url.strip()]
            conf, needs_llm = 0.6, False
    return {"channel": channel, "detail": detail,
            "confidence": round(conf, 2), "needs_llm_review": needs_llm}

# ---------------------------------------------------------------- dedup

BLOCK_MAX = 50   # blok lebih besar dari ini dianggap tak informatif, dilewati

def build_blocks(recs):
    b = collections.defaultdict(set)
    for i, r in enumerate(recs):
        if r["phone_key"]:  b["phone:"  + r["phone_key"]].add(i)
        if r["email_key"]:  b["ekey:"   + r["email_key"]].add(i)
        if r["email"]:      b["email:"  + r["email"]].add(i)
        if r["domain_root"] and r["last"]:
            b["dom_last:" + r["domain_root"] + "|" + r["last"].lower()].add(i)
    return b

def candidate_pairs(recs):
    pairs = set()
    for key, members in build_blocks(recs).items():
        if 1 < len(members) <= BLOCK_MAX:
            pairs.update(itertools.combinations(sorted(members), 2))
    return pairs

def score_pair(a: dict, b: dict) -> tuple[float, dict]:
    same_dom   = bool(a["domain"]) and a["domain"] == b["domain"]
    email_eq   = bool(a["email"]) and a["email"] == b["email"]
    email_norm = bool(a["email_key"]) and a["email_key"] == b["email_key"]
    phone_eq   = bool(a["phone_key"]) and a["phone_key"] == b["phone_key"]
    local_sim  = fuzz.ratio(a["local"], b["local"]) / 100

    anchors = []
    if email_eq:                                   anchors.append(("email_exact", 1.00))
    elif email_norm:                               anchors.append(("email_normalized", 0.97))
    if phone_eq:                                   anchors.append(("phone_exact", 0.95))
    if same_dom and local_sim >= 0.62 and not (email_eq or email_norm):
        anchors.append(("email_same_domain_similar_local", 0.70))
    identity = max([w for _, w in anchors], default=0.0)
    strong   = sum(1 for _, w in anchors if w >= 0.95)

    name_sim = fuzz.token_sort_ratio(a["display_name"].lower(), b["display_name"].lower()) / 100
    initial_match = (
        a["last"].lower() == b["last"].lower() and a["last"]
        and a["first"][:1].lower() == b["first"][:1].lower()
        and (a["is_initial"] or b["is_initial"])
    )
    person = max(name_sim, 0.95 if initial_match else 0.0)
    org = 1.0 if (a["domain_root"] and a["domain_root"] == b["domain_root"]) \
              else fuzz.token_set_ratio(a["company_core"], b["company_core"]) / 100
    same_country = a["country"].lower() == b["country"].lower()

    conf = (0.45 * identity + 0.33 * person + 0.12 * org
            + 0.05 * same_country + 0.05 * (1 if strong >= 2 else 0))

    # ATURAN KERAS 1: tanpa identity anchor kuat (email/telepon), kemiripan
    # nama + perusahaan TIDAK PERNAH cukup -> plafon 0.45 (zona review, bukan merge).
    if identity < 0.95:
        conf = min(conf, 0.45)
    # ATURAN KERAS 2: anchor kuat tapi orangnya jelas beda -> turunkan.
    if identity >= 0.95 and person < 0.55:
        conf = min(conf, 0.55)

    ev = {
        "email_exact": email_eq, "email_normalized_match": email_norm,
        "phone_last9_exact": phone_eq, "same_email_domain": same_dom,
        "email_local_similarity": round(local_sim, 2),
        "name_similarity": round(name_sim, 2), "name_initial_form_match": initial_match,
        "company_similarity": round(org, 2), "same_country": same_country,
        "strong_anchors": [n for n, _ in anchors if _ >= 0.95],
    }
    return round(conf, 3), ev

def explain(conf, ev):
    bits = []
    if ev["email_exact"]:            bits.append("email identik")
    elif ev["email_normalized_match"]: bits.append("email identik setelah normalisasi titik/tag")
    if ev["phone_last9_exact"]:      bits.append("9 digit terakhir telepon identik")
    if ev["name_initial_form_match"]:bits.append("nama bentuk inisial cocok (mis. 'J. Yoon' vs 'Ji-woo Yoon')")
    elif ev["name_similarity"] >= 0.9: bits.append(f"nama mirip {ev['name_similarity']:.0%}")
    if ev["company_similarity"] >= 0.9: bits.append("perusahaan sama setelah suffix legal dibuang")
    if not bits: bits.append("hanya kemiripan lemah")
    verdict = ("hampir pasti duplikat" if conf >= 0.90 else
               "perlu review manusia"  if conf >= 0.45 else "kemungkinan orang berbeda")
    return f"{verdict}: " + ", ".join(bits)

class DSU:
    def __init__(s, n): s.p = list(range(n))
    def find(s, x):
        while s.p[x] != x: s.p[x] = s.p[s.p[x]]; x = s.p[x]
        return x
    def union(s, a, b):
        ra, rb = s.find(a), s.find(b)
        if ra != rb: s.p[ra] = rb

# ------------------------------------------------- survivorship (usulan master)

def _completeness(r: dict) -> int:
    """Berapa banyak field bernilai yang dibawa satu baris."""
    return sum(1 for k in ("job_title", "lead_score", "lifecycle_stage", "original_source",
                           "last_modified_date", "notes") if r.get(k))

def _name_quality(r: dict) -> int:
    """Nama penuh > bentuk inisial > kosong. 'Joon Diallo' menang atas 'J. Diallo'."""
    if not r["display_name"]: return 0
    if r["is_initial"]: return 1
    return 2

def pick_master(members: list[dict]) -> dict:
    """Survivorship: kelengkapan field -> kualitas nama -> Last Modified terbaru -> Record ID terkecil.

    Record ID terkecil dipakai sebagai tie-break terakhir supaya hasilnya deterministik
    dan cenderung mempertahankan record tertua (yang biasanya sudah dirujuk sistem lain).
    """
    return sorted(members, key=lambda r: (
        -_completeness(r),
        -_name_quality(r),
        _inv(r["last_modified_date"]),
        r["record_id"],
    ))[0]

def _inv(iso: str) -> str:
    """Kunci sort agar tanggal TERBARU lebih dulu saat sort ascending."""
    return "".join(chr(0x10FFFF - ord(c)) if ord(c) < 0x10FFFF else c for c in (iso or ""))

def merged_view(members: list[dict]) -> dict:
    """Golden record: per field ambil nilai non-kosong dari kandidat terbaik.

    Urutan kandidat = urutan survivorship yang sama dengan pick_master, jadi
    field yang kosong di master otomatis diisi dari anggota lain (bukan sebaliknya).
    """
    order = sorted(members, key=lambda r: (
        -_completeness(r), -_name_quality(r), _inv(r["last_modified_date"]), r["record_id"]))
    out = {}
    for f in ("first", "last", "display_name", "job_title", "company_display", "email",
              "phone_e164", "country", "lead_status", "lifecycle_stage", "original_source",
              "contact_owner", "last_modified_date", "lead_score", "notes",
              "source_channel", "source_detail"):
        out[f] = next((r[f] for r in order if r.get(f)), "")
    # Nama: selalu ambil bentuk terlengkap dari seluruh anggota, bukan hanya master.
    best_name = max(members, key=lambda r: (_name_quality(r), len(r["display_name"])))
    out["first"], out["last"] = best_name["first"], best_name["last"]
    out["display_name"] = best_name["display_name"]
    # Nama perusahaan: ambil yang paling pendek setelah dirapikan (paling sedikit artefak).
    comps = [r["company_display"] for r in members if r["company_display"]]
    if comps: out["company_display"] = min(comps, key=len)
    # Create Date: tanggal PALING AWAL, karena itu saat lead benar-benar pertama masuk.
    out["create_date"] = min((r["create_date"] for r in members if r["create_date"]), default="")
    out["merged_from"] = [r["record_id"] for r in members]
    return out

# ---------------------------------------------------------------- main

def build_record(row: dict) -> dict:
    """Ubah satu baris mentah (kunci = nama kolom CSV) jadi record kanonik.

    Dipakai oleh dua jalur: pipeline offline (`load()`) dan endpoint
    `POST /leads/ingest`. Sengaja satu fungsi -- kalau ingest menormalisasi
    sedikit saja berbeda, kunci blocking-nya meleset dan dedup online gagal
    menemukan duplikat yang sebenarnya ada.
    """
    row = collections.defaultdict(str, row)
    first, last, disp, is_ini = split_name(row["First Name"], row["Last Name"], row["Full Name"])
    email = norm_email(row["Email"])
    dom = email.split("@")[1] if "@" in email else ""
    src = extract_source(row["Notes"], row["Original Source"], row["Page URL"])
    return {
        "record_id": norm_ws(row["Record ID"]),
        "first": first, "last": last, "display_name": disp, "is_initial": is_ini,
        "name_source": "full_name" if norm_ws(row["Full Name"]) else "first_last",
        "job_title": norm_ws(row["Job Title"]),
        "company_raw": norm_ws(row["Company Name"]),
        "company_display": company_display(row["Company Name"]),
        "company_core": company_core(row["Company Name"]),
        "email": email, "email_key": email_key(row["Email"]),
        "local": email.split("@")[0] if "@" in email else email,
        "domain": dom, "domain_root": dom.split(".")[0] if dom else "",
        "phone_raw": norm_ws(row["Phone Number"]),
        "phone_e164": phone_e164(row["Phone Number"]),
        "phone_key": phone_key(row["Phone Number"]),
        "country": norm_country(row["Country/Region"]),
        "lead_status": norm_status(row["Lead Status"]),
        "lifecycle_stage": norm_lifecycle(row["Lifecycle Stage"]),
        "original_source": norm_ws(row["Original Source"]),
        "contact_owner": norm_ws(row["Contact Owner"]),
        "create_date": norm_date(row["Create Date"]),
        "last_modified_date": norm_date(row["Last Modified Date"]),
        "lead_score": norm_ws(row["Lead Score"]),
        "notes": norm_ws(row["Notes"]),
        "flagged_in_notes": bool(re.search("possible duplicate", row["Notes"], re.I)),
        "source_channel": src["channel"], "source_detail": src["detail"],
        "source_confidence": src["confidence"], "source_needs_llm": src["needs_llm_review"],
    }

def load() -> list[dict]:
    df = pd.read_csv(SRC_CSV, dtype=str, keep_default_na=False)
    return [build_record(row) for row in df.to_dict("records")]

MERGE_T, REVIEW_T = 0.90, 0.45

def main():
    recs = load()
    pairs = candidate_pairs(recs)
    scored = []
    for a, b in pairs:
        c, ev = score_pair(recs[a], recs[b])
        scored.append({"a": a, "b": b, "confidence": c, "evidence": ev,
                       "explanation": explain(c, ev)})
    scored.sort(key=lambda p: -p["confidence"])

    dsu = DSU(len(recs))
    for p in scored:
        if p["confidence"] >= MERGE_T: dsu.union(p["a"], p["b"])
    groups = collections.defaultdict(list)
    for i in range(len(recs)): groups[dsu.find(i)].append(i)
    clusters = [sorted(v) for v in groups.values() if len(v) > 1]
    clusters.sort(key=lambda v: recs[v[0]]["record_id"])

    pair_conf = {(p["a"], p["b"]): p for p in scored}
    group_out = []
    for gi, members in enumerate(clusters, 1):
        mrecs = [recs[i] for i in members]
        internal = [pair_conf[(a, b)] for a, b in itertools.combinations(members, 2)
                    if (a, b) in pair_conf]
        gconf = min((p["confidence"] for p in internal), default=1.0)
        master = pick_master(mrecs)
        group_out.append({
            "group_id": f"G{gi:04d}", "size": len(members),
            "group_confidence": round(gconf, 3),
            "suggested_master_record_id": master["record_id"],
            "members": [{"record_id": r["record_id"], "name": r["display_name"],
                         "company": r["company_display"], "email": r["email"],
                         "phone": r["phone_e164"], "status": r["lead_status"],
                         "created": r["create_date"], "modified": r["last_modified_date"],
                         "flagged_in_notes": r["flagged_in_notes"]} for r in mrecs],
            "evidence": [{"a": recs[p["a"]]["record_id"], "b": recs[p["b"]]["record_id"],
                          "confidence": p["confidence"], "why": p["explanation"],
                          "signals": p["evidence"]} for p in internal],
            "merged_preview": merged_view(mrecs),
            "conflicts": {f: sorted({r[f] for r in mrecs if r[f]})
                          for f in ("email","phone_e164","company_display","lead_status",
                                    "country","contact_owner","lifecycle_stage","original_source")
                          if len({r[f] for r in mrecs if r[f]}) > 1},
        })

    review = [p for p in scored if REVIEW_T <= p["confidence"] < MERGE_T]

    # ---- tulis artefak
    fields = ["record_id","first","last","display_name","name_source","job_title",
              "company_display","company_core","email","phone_e164","country","lead_status",
              "lifecycle_stage","original_source","contact_owner","create_date",
              "last_modified_date","lead_score","source_channel","source_detail",
              "source_confidence","source_needs_llm","flagged_in_notes","notes"]
    with open(OUT / "leads_clean.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(recs)

    (OUT / "dedupe_groups.json").write_text(json.dumps(group_out, indent=2, ensure_ascii=False))

    with open(OUT / "dedupe_review.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["confidence","record_id_a","name_a","company_a","email_a","phone_a","country_a",
                    "record_id_b","name_b","company_b","email_b","phone_b","country_b","why"])
        for p in review:
            a, b = recs[p["a"]], recs[p["b"]]
            w.writerow([p["confidence"], a["record_id"], a["display_name"], a["company_display"],
                        a["email"], a["phone_e164"], a["country"],
                        b["record_id"], b["display_name"], b["company_display"], b["email"],
                        b["phone_e164"], b["country"], p["explanation"]])

    n = len(recs)
    report = {
        "rows_in": n,
        "columns_dropped_always_empty": DROP_ALWAYS_EMPTY,
        "blocking": {
            "candidate_pairs": len(pairs),
            "brute_force_pairs": n * (n - 1) // 2,
            "reduction_pct": round(100 * (1 - len(pairs) / (n * (n - 1) / 2)), 4),
        },
        "dedupe": {
            "auto_merge_threshold": MERGE_T, "review_threshold": REVIEW_T,
            "groups": len(clusters),
            "rows_in_groups": sum(len(c) for c in clusters),
            "redundant_rows": sum(len(c) - 1 for c in clusters),
            "distinct_people_estimate": n - sum(len(c) - 1 for c in clusters),
            "group_size_distribution": dict(sorted(collections.Counter(len(c) for c in clusters).items())),
            "pairs_in_review_zone": len(review),
            "notes_flagged_rows": sum(1 for r in recs if r["flagged_in_notes"]),
            "notes_flagged_captured": sum(1 for c in clusters for i in c if recs[i]["flagged_in_notes"]),
        },
        "normalization": {
            "lead_status_variants_before": 35, "lead_status_variants_after":
                len({r["lead_status"] for r in recs}),
            "country_variants_before": 62, "country_variants_after":
                len({r["country"] for r in recs}),
            "owner_variants_before": 20, "owner_variants_after":
                len({r["contact_owner"] for r in recs}),
            "dates_unparsed": sum(1 for r in recs if r["notes"] and not r["create_date"]),
        },
        "source_extraction": {
            "channel_distribution": dict(collections.Counter(r["source_channel"] for r in recs).most_common()),
            "needs_llm_review": sum(1 for r in recs if r["source_needs_llm"]),
            "mean_confidence": round(sum(r["source_confidence"] for r in recs) / n, 3),
        },
    }
    (OUT / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps(report, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
