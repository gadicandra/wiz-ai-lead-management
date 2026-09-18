"""Tes fokus ke kasus ambigu, bukan happy path."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from clean_leads import (norm_status, norm_country, norm_date, email_key, phone_key,
                         company_core, company_display, split_name, extract_source,
                         score_pair, MERGE_T, REVIEW_T)

def rec(**kw):
    base = dict(record_id="1", first="", last="", display_name="", is_initial=False,
                company_core="", email="", email_key="", local="", domain="", domain_root="",
                phone_key="", country="")
    base.update(kw); return base

def mk(first, last, email, phone, company, country="X", is_initial=False, full=None):
    dom = email.split("@")[1] if "@" in email else ""
    return rec(first=first, last=last, display_name=full or f"{first} {last}".strip(),
               is_initial=is_initial, company_core=company_core(company), email=email.lower(),
               email_key=email_key(email), local=email.split("@")[0], domain=dom,
               domain_root=dom.split(".")[0], phone_key=phone_key(phone), country=country)

# ---------- normalisasi ----------
def test_status_casing_and_whitespace_collapse():
    for v in ["New", "new", "NEW", " New", "New ", "  new  "]:
        assert norm_status(v) == "New"

def test_status_unknown_value_is_preserved_not_silently_dropped():
    assert norm_status("Nurturing") == "Nurturing"

def test_date_three_formats_converge():
    assert norm_date("2026-06-02") == norm_date("6/2/2026") == norm_date("2026-06-02T00:00:00Z")

def test_unparseable_date_returns_blank_not_crash():
    assert norm_date("June 2nd") == ""
    assert norm_date("") == ""

def test_country_casing():
    assert norm_country("malaysia") == "Malaysia"
    assert norm_country("UAE") == "UAE"          # akronim tidak di-title-case
    assert norm_country("united kingdom") == "United Kingdom"

# ---------- kunci identitas ----------
def test_email_key_ignores_dots_and_plus_tag():
    assert email_key("Ji-Woo.Yoon+crm@Foster.biz") == email_key("jiwooyoon@foster.biz")

def test_email_key_keeps_different_localparts_distinct():
    assert email_key("m.ho@asanteretail.io") != email_key("marcush@asanteretail.com")

def test_phone_key_survives_format_differences():
    assert phone_key("+34 696 235 827") == phone_key("34696235827") == phone_key("0034696235827")

def test_phone_key_short_number_not_padded():
    assert phone_key("12345") == "12345"

# ---------- perusahaan ----------
def test_company_core_strips_legal_suffix_variants():
    assert company_core("Foster Studio") == company_core("Foster Partners") == "foster"
    assert company_core("Muller GmbH Pte. Ltd.") == company_core("Muller GmbH & Co")

def test_company_display_repairs_generator_artifacts():
    assert company_display("Chen Digital and and Co") == "Chen Digital & Co"
    assert company_display("Gupta Textiles Retail Retail Group") == "Gupta Textiles Retail Group"

# ---------- nama ----------
def test_full_name_initial_form_detected():
    f, l, d, ini = split_name("", "", "J. Yoon")
    assert (f, l, ini) == ("J.", "Yoon", True)

def test_first_last_form_not_flagged_as_initial():
    assert split_name("Ji-woo", "Yoon", "")[3] is False

# ---------- dedup: kasus yang harus MATCH ----------
def test_same_person_different_email_localpart_but_same_phone_is_high_confidence():
    a = mk("Luca", "Wagner", "luca.wagner@mensahtrading.biz", "+82 10-4251-1128", "Mensah Trading & Co")
    b = mk("Luca", "Wagner", "lucawagner@mensahtrading.biz", "+82 10-4251-1128", "Mensah Trading & and Co")
    conf, _ = score_pair(a, b)
    assert conf >= MERGE_T

def test_initial_name_form_matches_full_first_name():
    a = mk("Ji-woo", "Yoon", "ji-wooy@foster.biz", "+34 696 235 827", "Foster Studio")
    b = mk("J.", "Yoon", "j.yoon@foster.biz", "34696235827", "Foster Trading", is_initial=True)
    conf, ev = score_pair(a, b)
    assert conf >= MERGE_T and ev["name_initial_form_match"]

def test_phone_format_difference_alone_does_not_break_match():
    a = mk("Natasha", "Ba", "natashab@mullergmbh.co", "+45 20 11 32 10", "Muller GmbH Pte. Ltd.")
    b = mk("Natasha", "Ba", "natashab@mullergmbh.co", "4520113210", "Muller GmbH & Co")
    assert score_pair(a, b)[0] >= MERGE_T

# ---------- dedup: kasus yang TIDAK boleh auto-merge ----------
def test_same_name_same_company_but_different_phone_and_email_stays_in_review():
    """Trap dataset: 'Marcus Ho' di Asante Retail ada dua orang berbeda."""
    a = mk("Marcus", "Ho", "m.ho@asanteretail.io", "+86 132 2249 7096", "Asante Retail Ltd", "China")
    b = mk("Marcus", "Ho", "marcush@asanteretail.com", "+852 8646 1508", "Asante Retail and Labs", "Hong Kong")
    conf, _ = score_pair(a, b)
    assert REVIEW_T <= conf < MERGE_T, f"conf={conf} — nama+perusahaan saja tak boleh cukup"

def test_siblings_same_surname_same_company_not_merged():
    a = mk("Freya", "Al-Sayed", "freya.al-sayed@kohsons.io", "+46 70 806 18 15", "Koh & Sons Co.", "Sweden")
    b = mk("Sophia", "Al-Sayed", "s.al-sayed@kohsons.io", "+86 130 6271 1760", "Koh & Sons Co.", "China")
    assert score_pair(a, b)[0] < MERGE_T

def test_shared_phone_but_clearly_different_person_is_capped():
    a = mk("Aisha", "Gomes", "aisha.gomes@yapventures.co", "+62 852 3029 4724", "Yap Ventures")
    b = mk("Bartholomew", "Nakamura", "b.nakamura@yapventures.co", "+62 852 3029 4724", "Yap Ventures")
    assert score_pair(a, b)[0] < MERGE_T   # telepon kantor bersama tidak cukup

# ---------- source extraction ----------
def test_event_with_named_conference():
    r = extract_source("Met her at the Singapore FinTech Festival 2026 booth, scanned our QR code.")
    assert r["channel"] == "Event" and "Singapore FinTech Festival 2026" in r["detail"]

def test_google_ad_is_website_not_organic_search():
    r = extract_source("Booked a demo via the book-a-demo page after clicking a google ad.")
    assert r["channel"] == "Website"

def test_organic_search_beats_landing_page_mention():
    r = extract_source("Found us through organic google search then landed on the pricing page.")
    assert r["channel"] == "Organic Search"

def test_linkedin_wins_over_generic_website_words():
    r = extract_source("Connected on LinkedIn after commenting on our post, then filled out the form.")
    assert r["channel"] == "LinkedIn"

def test_referral_extracts_referrer_name():
    r = extract_source("Referred by Elena Han, warm intro. Connected, sending proposal.")
    assert r["channel"] == "Referral" and "Elena Han" in r["detail"]

def test_unmatched_text_is_flagged_for_llm_not_guessed():
    r = extract_source("Saw our post about replacing hubspot and commented.")
    assert r["needs_llm_review"] is True and r["confidence"] <= 0.55

def test_unmatched_text_falls_back_to_trustworthy_original_source():
    r = extract_source("Saw our post about replacing hubspot and commented.", "Social Media")
    assert r["channel"] == "LinkedIn" and r["needs_llm_review"] is True

def test_generic_original_source_is_not_trusted_blindly():
    """'Offline Sources' untuk lead event tidak boleh jadi channel final."""
    r = extract_source("Met him at the SFF booth, scanned our QR code.", "Offline Sources")
    assert r["channel"] == "Event"

def test_duplicate_marker_stripped_before_classification():
    r = extract_source("Filled out the form on the pricing page. possible duplicate — verify before contacting.")
    assert r["channel"] == "Website" and "duplicate" not in r["detail"].lower()
