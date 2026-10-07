from typing import Optional

from pydantic import BaseModel, Field


class SourceItem(BaseModel):
    """Satu entri sumber/citation di balik sebuah jawaban."""

    label: str
    source: Optional[str] = None
    document_id: Optional[str] = None
    document_year: Optional[int] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    corrected_by: Optional[str] = None
    correction_date: Optional[str] = None


class RoomOut(BaseModel):
    """Satu room percakapan (thread tanya-jawab terpisah) milik user."""

    id: str
    title: str
    created_at: str
    updated_at: str


class RoomCreate(BaseModel):
    title: Optional[str] = None


class AskRequest(BaseModel):
    room_id: str = Field(..., min_length=1)
    question: str = Field(..., min_length=1, examples=["Berapa rata-rata pengeluaran per kapita sebulan?"])


class AskResponse(BaseModel):
    """Respons /ask untuk petugas. Isi konteks yang dikirim ke LLM TIDAK
    disertakan (hanya tersimpan di database untuk keperluan pengembangan).
    Untuk jawaban abstain, `sources` selalu kosong."""

    answer: str
    sources: list[SourceItem]
    is_abstained: bool


class InteractionSummary(BaseModel):
    """Satu interaksi untuk tab Tinjau Percakapan (instruktur), lengkap
    dengan status verifikasi dan data koreksi bila ada -- tanpa
    konteks/sumber."""

    id: str
    timestamp: str
    username: str
    question: str
    answer: str
    is_abstained: bool
    # unverified | verified | corrected
    status: str = "unverified"
    corrected: bool = False
    verified: bool = False
    verified_by: Optional[str] = None
    verified_at: Optional[str] = None
    correction_id: Optional[str] = None
    correction_text: Optional[str] = None
    corrected_by: Optional[str] = None
    correction_date: Optional[str] = None
    correction_at: Optional[str] = None


class InteractionDetail(BaseModel):
    """Riwayat percakapan milik satu petugas -- dipakai di /chat/history.
    Tidak memuat konteks LLM. `sources` kosong untuk jawaban abstain, dan
    berisi label koreksi instruktur untuk jawaban yang sudah dikoreksi."""

    id: str
    timestamp: str
    username: str
    question: str
    answer: str
    is_abstained: bool
    status: str = "unverified"
    corrected: bool = False
    verified: bool = False
    sources: list[SourceItem]
    correction_text: Optional[str] = None
    corrected_by: Optional[str] = None
    correction_date: Optional[str] = None
    verified_by: Optional[str] = None
    verified_at: Optional[str] = None


class CorrectionRequest(BaseModel):
    """Pertanyaan asli diambil server dari database berdasarkan
    interaction_id (bukan dari kiriman klien)."""

    interaction_id: str = Field(..., min_length=1)
    correction_text: str = Field(..., min_length=1)


class CorrectionResponse(BaseModel):
    interaction_id: str
    chunk_id: str
    status: str = "ok"


class VerifyRequest(BaseModel):
    """Dipakai untuk menandai Verified (jawaban chatbot sudah benar
    apa adanya, tanpa koreksi & tanpa chunk baru di KB) maupun untuk
    membatalkan verifikasi (kembali Unverified)."""

    interaction_id: str = Field(..., min_length=1)


class VerifyResponse(BaseModel):
    interaction_id: str
    status: str = "ok"


class PDFUploadResponse(BaseModel):
    document_id: str
    document_year: int
    chunks_added: int
    chunk_ids: list[str]


class DeleteCorrectionResponse(BaseModel):
    correction_id: str
    chunk_id: str
    status: str = "ok"


class CorrectionUpdateRequest(BaseModel):
    """Payload untuk PATCH /instructor/corrections/{correction_id} --
    dipakai instruktur untuk memperbaiki ISI sebuah koreksi yang sudah
    pernah disuntikkan, tanpa perlu menghapusnya dulu (yang akan membuat
    interaksi terkait kembali muncul sebagai 'belum dikoreksi')."""

    correction_text: str = Field(..., min_length=1)


class KBDocumentItem(BaseModel):
    """Satu baris di tab Kelola KB. kind: base (KB awal, terkunci) |
    upload (PDF unggahan, bisa dihapus) | correction (seluruh chunk
    koreksi, dikelola dari tab Tinjau Percakapan)."""

    document_id: str
    display_name: str
    kind: str
    document_year: Optional[int] = None
    chunk_count: int
    created_at: Optional[str] = None
    deletable: bool


class DeleteKBDocumentResponse(BaseModel):
    document_id: str
    chunks_deleted: int
    status: str = "ok"
