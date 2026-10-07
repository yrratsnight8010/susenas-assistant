from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from starlette.concurrency import run_in_threadpool

from app.core.security import require_role
from app.dependencies import get_resources
from app.schemas.chat import (
    CorrectionRequest,
    CorrectionResponse,
    CorrectionUpdateRequest,
    DeleteCorrectionResponse,
    DeleteKBDocumentResponse,
    InteractionSummary,
    KBDocumentItem,
    PDFUploadResponse,
    VerifyRequest,
    VerifyResponse,
)
from app.services.rag_pipeline import PipelineResources, extract_pdf_pages

router = APIRouter()

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB
VALID_STATUS_FILTERS = {"all", "unverified", "verified", "corrected"}


def _get_interaction_or_404(resources: PipelineResources, interaction_id: str) -> dict:
    interaction = resources.conversation_store.get_interaction(interaction_id)
    if interaction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Percakapan tidak ditemukan.")
    return interaction


# ---------------------------------------------------------------------
# Tinjau Percakapan
# ---------------------------------------------------------------------

@router.get(
    "/interactions",
    response_model=list[InteractionSummary],
    summary="Daftar seluruh percakapan (semua user) untuk ditinjau instruktur",
    description=(
        "Parameter `status`: all | unverified | verified | corrected. Setiap "
        "item sudah menyertakan data koreksinya (correction_id, correction_text, "
        "dst.) bila berstatus corrected, sehingga edit/hapus koreksi bisa "
        "dilakukan langsung dari daftar ini."
    ),
)
def list_interactions(
    status_filter: str = Query("all", alias="status"),
    resources: PipelineResources = Depends(get_resources),
    _user: dict = Depends(require_role("instruktur")),
) -> list[InteractionSummary]:
    if status_filter not in VALID_STATUS_FILTERS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Parameter status harus salah satu dari: {', '.join(sorted(VALID_STATUS_FILTERS))}.",
        )
    return [InteractionSummary(**item) for item in resources.conversation_store.list_interactions(status_filter)]


@router.post(
    "/correct",
    response_model=CorrectionResponse,
    summary="Simpan koreksi instruktur & injeksikan ke Knowledge Base",
    description=(
        "Menyuntikkan koreksi sebagai chunk baru ke KB (Qdrant + BM25 + KB JSON) "
        "lalu menandai interaksi sebagai Corrected. Hanya untuk interaksi "
        "berstatus Unverified (kalau sudah Verified, batalkan verifikasinya dulu)."
    ),
)
def submit_correction(
    payload: CorrectionRequest,
    resources: PipelineResources = Depends(get_resources),
    user: dict = Depends(require_role("instruktur")),
) -> CorrectionResponse:
    interaction = _get_interaction_or_404(resources, payload.interaction_id)
    if interaction["status"] == "corrected":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Percakapan ini sudah dikoreksi.")
    if interaction["status"] == "verified":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Percakapan ini berstatus Verified. Batalkan verifikasinya dulu sebelum mengoreksi.",
        )

    correction_text = payload.correction_text.strip()
    if not correction_text:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Isi koreksi tidak boleh kosong.")

    try:
        chunk_id = resources.kb_manager.inject_correction(
            interaction_id=payload.interaction_id,
            question=interaction["question"],
            correction_text=correction_text,
            corrected_by=user["username"],
            collection_name=resources.retrieval_config.collection_name,
        )
        resources.conversation_store.mark_corrected(
            interaction_id=payload.interaction_id,
            correction_text=correction_text,
            corrected_by=user["username"],
            chunk_id=chunk_id,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gagal menyimpan koreksi: {exc}",
        ) from exc

    return CorrectionResponse(interaction_id=payload.interaction_id, chunk_id=chunk_id)


@router.post(
    "/verify",
    response_model=VerifyResponse,
    summary="Tandai jawaban chatbot Verified (sudah benar, tanpa koreksi)",
    description=(
        "Dipakai saat jawaban chatbot SUDAH BENAR apa adanya: tanpa "
        "correction_text dan tanpa chunk baru di KB. Ditolak (409) kalau "
        "percakapan sudah berstatus Corrected."
    ),
)
def verify(
    payload: VerifyRequest,
    resources: PipelineResources = Depends(get_resources),
    user: dict = Depends(require_role("instruktur")),
) -> VerifyResponse:
    interaction = _get_interaction_or_404(resources, payload.interaction_id)
    if interaction["status"] == "corrected":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Percakapan ini sudah dikoreksi. Hapus koreksinya dulu kalau ingin menandainya Verified.",
        )
    if interaction["status"] != "verified":
        resources.conversation_store.mark_verified(payload.interaction_id, verified_by=user["username"])
    return VerifyResponse(interaction_id=payload.interaction_id)


@router.post(
    "/unverify",
    response_model=VerifyResponse,
    summary="Batalkan verifikasi (kembali Unverified)",
    description="Hanya untuk percakapan berstatus Verified.",
)
def unverify(
    payload: VerifyRequest,
    resources: PipelineResources = Depends(get_resources),
    _user: dict = Depends(require_role("instruktur")),
) -> VerifyResponse:
    interaction = _get_interaction_or_404(resources, payload.interaction_id)
    if interaction["status"] != "verified":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Percakapan ini tidak berstatus Verified.")
    resources.conversation_store.mark_unverified(payload.interaction_id)
    return VerifyResponse(interaction_id=payload.interaction_id)


@router.patch(
    "/corrections/{correction_id}",
    response_model=CorrectionResponse,
    summary="Edit isi 1 koreksi yang sudah ada & re-injeksi ke KB",
    description=(
        "Interaksi terkait TETAP berstatus Corrected, hanya isi koreksinya "
        "yang diganti. Di baliknya: chunk versi BARU disuntikkan lebih dulu, "
        "baru chunk versi LAMA dicabut dari KB JSON + Qdrant (chunk_id "
        "berubah karena deterministik dari isi teks), dan correction_date "
        "digeser ke SEKARANG supaya aturan 'ambil informasi paling baru' di "
        "system prompt menganggap hasil edit ini sebagai versi terbaru."
    ),
)
def update_correction(
    correction_id: str,
    payload: CorrectionUpdateRequest,
    resources: PipelineResources = Depends(get_resources),
    user: dict = Depends(require_role("instruktur")),
) -> CorrectionResponse:
    existing = resources.conversation_store.get_correction(correction_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Koreksi tidak ditemukan.")

    new_text = payload.correction_text.strip()
    if not new_text:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Isi koreksi tidak boleh kosong.")

    try:
        new_chunk_id = resources.kb_manager.inject_correction(
            interaction_id=existing["interaction_id"],
            question=existing["original_question"],
            correction_text=new_text,
            corrected_by=user["username"],
            collection_name=resources.retrieval_config.collection_name,
        )
        old_chunk_id = existing.get("chunk_id")
        if old_chunk_id and old_chunk_id != new_chunk_id:
            resources.kb_manager.delete_chunk(old_chunk_id, resources.retrieval_config.collection_name)

        resources.conversation_store.update_correction(
            correction_id=correction_id,
            correction_text=new_text,
            corrected_by=user["username"],
            chunk_id=new_chunk_id,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gagal memperbarui koreksi: {exc}",
        ) from exc

    return CorrectionResponse(interaction_id=existing["interaction_id"], chunk_id=new_chunk_id)


@router.delete(
    "/corrections/{correction_id}",
    response_model=DeleteCorrectionResponse,
    summary="Hapus 1 koreksi: dari log, KB JSON, dan Qdrant",
    description=(
        "Baris koreksi dihapus dari log, chunk-nya dicabut dari KB JSON + "
        "Qdrant/BM25, dan interaksi terkait kembali berstatus Unverified."
    ),
)
def delete_correction(
    correction_id: str,
    resources: PipelineResources = Depends(get_resources),
    _user: dict = Depends(require_role("instruktur")),
) -> DeleteCorrectionResponse:
    chunk_id = resources.conversation_store.delete_correction(correction_id)
    if chunk_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Koreksi tidak ditemukan.")
    if chunk_id:
        resources.kb_manager.delete_chunk(chunk_id, resources.retrieval_config.collection_name)
    return DeleteCorrectionResponse(correction_id=correction_id, chunk_id=chunk_id or "")


# ---------------------------------------------------------------------
# Kelola KB
# ---------------------------------------------------------------------

@router.get(
    "/kb/documents",
    response_model=list[KBDocumentItem],
    summary="Daftar dokumen di Knowledge Base",
    description=(
        "Ringkasan isi KB per dokumen: KB awal (terkunci), PDF unggahan "
        "(bisa dihapus), dan seluruh chunk koreksi (dikelola dari tab "
        "Tinjau Percakapan)."
    ),
)
def list_kb_documents(
    resources: PipelineResources = Depends(get_resources),
    _user: dict = Depends(require_role("instruktur")),
) -> list[KBDocumentItem]:
    return [KBDocumentItem(**item) for item in resources.kb_manager.list_documents()]


@router.delete(
    "/kb/documents",
    response_model=DeleteKBDocumentResponse,
    summary="Hapus 1 dokumen unggahan dari Knowledge Base",
    description=(
        "Mencabut SEMUA chunk dari satu dokumen unggahan (KB JSON + Qdrant + "
        "BM25). KB awal dan chunk koreksi tidak bisa dihapus lewat endpoint "
        "ini. `document_id` dikirim sebagai query parameter karena bisa "
        "mengandung karakter khusus."
    ),
)
async def delete_kb_document(
    document_id: str = Query(..., min_length=1),
    resources: PipelineResources = Depends(get_resources),
    _user: dict = Depends(require_role("instruktur")),
) -> DeleteKBDocumentResponse:
    try:
        deleted = await run_in_threadpool(
            resources.kb_manager.delete_document, document_id, resources.retrieval_config.collection_name
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gagal menghapus dokumen: {exc}",
        ) from exc
    if deleted == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokumen unggahan tidak ditemukan (KB awal dan koreksi tidak bisa dihapus dari sini).",
        )
    return DeleteKBDocumentResponse(document_id=document_id, chunks_deleted=deleted)


@router.post(
    "/upload-pdf",
    response_model=PDFUploadResponse,
    summary="Unggah dokumen PDF baru ke Knowledge Base",
    description="Memakai multipart/form-data karena melibatkan file.",
)
async def upload_pdf(
    document_id: str = Form(..., min_length=1),
    document_year: int = Form(...),
    file: UploadFile = File(...),
    resources: PipelineResources = Depends(get_resources),
    _user: dict = Depends(require_role("instruktur")),
) -> PDFUploadResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File harus berformat PDF.")

    clean_document_id = document_id.strip()
    if not clean_document_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nama dokumen tidak boleh kosong.")
    if resources.kb_manager.is_base_document_id(clean_document_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nama dokumen ini sudah dipakai oleh KB awal. Gunakan nama lain.",
        )

    file_bytes = await file.read()
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Ukuran file melebihi batas {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
        )

    def _process() -> list[str]:
        pages = extract_pdf_pages(file_bytes)
        return resources.kb_manager.inject_pdf(
            document_id=clean_document_id,
            pages=pages,
            collection_name=resources.retrieval_config.collection_name,
            document_year=document_year,
        )

    # Ekstraksi + embedding bersifat blocking/berat; dijalankan di threadpool
    # supaya event loop tidak macet dan request petugas lain tetap terlayani.
    try:
        chunk_ids = await run_in_threadpool(_process)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gagal memproses PDF: {exc}",
        ) from exc

    return PDFUploadResponse(
        document_id=clean_document_id,
        document_year=document_year,
        chunks_added=len(chunk_ids),
        chunk_ids=chunk_ids,
    )
