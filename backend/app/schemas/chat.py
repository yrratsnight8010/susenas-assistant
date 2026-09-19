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
    answer: str
    context: str
    sources: list[SourceItem]
    is_abstained: bool


class InteractionSummary(BaseModel):
    """Ringkasan 1 interaksi untuk daftar tinjauan instruktur -- TANPA
    konteks/sumber lengkap, sama seperti query ringan `list_interactions`
    di rag_pipeline.py."""

    id: str
    timestamp: str
    username: str
    question: str
    answer: str
    is_abstained: bool
    corrected: bool
    verified: bool = False


class InteractionDetail(InteractionSummary):
    """Riwayat percakapan lengkap milik satu user, termasuk konteks,
    sumber, dan status koreksi/verifikasi -- dipakai di /chat/history."""

    context: str
    sources: list[SourceItem]
    correction_text: Optional[str] = None
    corrected_by: Optional[str] = None
    correction_date: Optional[str] = None
    verified_by: Optional[str] = None
    verified_at: Optional[str] = None


class CorrectionRequest(BaseModel):
    interaction_id: str = Field(..., min_length=1)
    question: str = Field(..., min_length=1)
    correction_text: str = Field(..., min_length=1)


class CorrectionResponse(BaseModel):
    interaction_id: str
    chunk_id: str
    status: str = "ok"


class VerifyRequest(BaseModel):
    """Dipakai saat jawaban chatbot SUDAH BENAR apa adanya -- instruktur
    cukup menandai terverifikasi tanpa menulis koreksi & tanpa
    menyuntikkan chunk baru ke Knowledge Base (beda dengan /correct,
    yang mengganti jawaban DAN menambah pengetahuan baru)."""

    interaction_id: str = Field(..., min_length=1)


class VerifyResponse(BaseModel):
    interaction_id: str
    status: str = "ok"


class PDFUploadResponse(BaseModel):
    document_id: str
    document_year: int
    chunks_added: int
    chunk_ids: list[str]


class CorrectionLogItem(BaseModel):
    """Satu baris di log koreksi -- untuk GET /instructor/corrections,
    supaya instruktur bisa meninjau (dan mencabut lewat DELETE
    /instructor/corrections/{correction_id}) koreksi yang ternyata salah."""

    correction_id: str
    interaction_id: str
    chunk_id: str
    correction_text: str
    corrected_by: str
    correction_date: str
    correction_at: Optional[str] = None
    username: str
    original_question: str


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
