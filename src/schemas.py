"""Model request/response. Pydantic dipakai supaya validasi ada di batas API,
bukan tersebar di dalam handler -- dan supaya /docs terisi otomatis."""
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field

Channel = Literal["Website", "Event", "LinkedIn", "Organic Search",
                  "Referral", "Manual/Sales", "Other"]


class LeadPatch(BaseModel):
    """Semua field opsional: PATCH bersifat parsial.

    Sengaja hanya tiga field ini (sesuai spesifikasi). Kolom kunci seperti
    `email_key` tidak boleh ditulis langsung -- nilainya harus selalu hasil
    normalisasi, kalau tidak blocking key jadi tidak konsisten dan dedup
    diam-diam berhenti bekerja.
    """
    lead_status: Optional[str] = Field(None, examples=["Qualified"])
    contact_owner: Optional[str] = Field(None, examples=["Priya Raman"])
    notes: Optional[str] = Field(None, examples=["Called back, wants pricing."])


class FormSubmission(BaseModel):
    """Bentuknya mengikuti entri data/website_form_submissions.json.

    Hanya `email` yang wajib -- tanpa email atau telepon, tidak ada identity
    anchor sama sekali, dan lead yang masuk tanpa itu akan selalu berakhir di
    zona review. Lebih baik ditolak di batas API daripada menumpuk antrian.
    """
    email: str
    name: str = ""
    phone: str = ""
    company: str = ""
    country: str = ""
    message: str = ""
    form_id: str = ""
    form_name: str = ""
    page_url: str = ""
    submitted_at: str = ""


class SourceExtractRequest(BaseModel):
    text: str = Field(..., examples=["Met him at the SFF booth, scanned our QR code"])
    original_source: str = ""
    page_url: str = ""


class SourceExtractResponse(BaseModel):
    channel: Channel
    detail: str
    confidence: float
    needs_llm_review: bool


class DedupeCandidatesRequest(BaseModel):
    """Dua mode.

    Tanpa `lead`: kembalikan grup duplikat yang sudah dihitung pipeline offline.
    Dengan `lead`: skor satu record baru terhadap isi DB (dry-run ingest --
    tanya "apakah orang ini sudah ada?" tanpa menulis apa pun).
    """
    lead: Optional[FormSubmission] = None
    min_confidence: float = Field(0.0, ge=0.0, le=1.0)
    limit: int = Field(50, ge=1, le=500)
