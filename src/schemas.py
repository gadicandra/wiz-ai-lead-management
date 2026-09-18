"""Model request/response. Pydantic dipakai supaya validasi ada di batas API,
bukan tersebar di dalam handler -- dan supaya /docs terisi otomatis."""
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    """Basis semua model request: field yang tidak dikenal DITOLAK, bukan dibuang.

    Default Pydantic adalah mengabaikan field asing diam-diam. Untuk API internal
    itu kelihatan ramah, tapi efeknya adalah kelas bug yang paling sulit dilihat:
    klien mengirim `{"record_id": "..."}` padahal field-nya bernama `lead`, server
    membalas 200, dan keduanya yakin sesuatu telah terjadi. Tidak ada yang error,
    tidak ada yang berubah.

    Kesalahan itu benar-benar terjadi saat menguji `/leads/dedupe-candidates`
    secara manual, dan test PATCH untuk "field tidak boleh diubah" ternyata lolos
    karena alasan yang salah -- `email` dibuang Pydantic sebelum sampai ke cek
    PATCHABLE, jadi yang terpicu adalah cabang "body kosong".

    Salah ketik nama field lebih baik jadi 422 yang menyebutkan namanya.
    """
    model_config = ConfigDict(extra="forbid")

Channel = Literal["Website", "Event", "LinkedIn", "Organic Search",
                  "Referral", "Manual/Sales", "Other"]


class LeadPatch(Strict):
    """Semua field opsional: PATCH bersifat parsial.

    Sengaja hanya tiga field ini (sesuai spesifikasi). Kolom kunci seperti
    `email_key` tidak boleh ditulis langsung -- nilainya harus selalu hasil
    normalisasi, kalau tidak blocking key jadi tidak konsisten dan dedup
    diam-diam berhenti bekerja.
    """
    lead_status: Optional[str] = Field(None, examples=["Qualified"])
    contact_owner: Optional[str] = Field(None, examples=["Priya Raman"])
    notes: Optional[str] = Field(None, examples=["Called back, wants pricing."])


class FormSubmission(Strict):
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


class SourceExtractRequest(Strict):
    text: str = Field(..., examples=["Met him at the SFF booth, scanned our QR code"])
    original_source: str = ""
    page_url: str = ""


class SourceExtractResponse(BaseModel):
    channel: Channel
    detail: str
    confidence: float
    needs_llm_review: bool


class DedupeCandidatesRequest(Strict):
    """Dua mode.

    Tanpa `lead`: kembalikan grup duplikat yang sudah dihitung pipeline offline.
    Dengan `lead`: skor satu record baru terhadap isi DB (dry-run ingest --
    tanya "apakah orang ini sudah ada?" tanpa menulis apa pun).
    """
    lead: Optional[FormSubmission] = None
    min_confidence: float = Field(0.0, ge=0.0, le=1.0)
    limit: int = Field(50, ge=1, le=500)
