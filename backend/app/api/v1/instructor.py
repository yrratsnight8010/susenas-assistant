from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.core.security import require_role
from app.dependencies import get_resources
from app.schemas.chat import (
    CorrectionRequest,
    CorrectionResponse,
    InteractionSummary,
    PDFUploadResponse,
    VerifyRequest,
    VerifyResponse,
)
from app.services.rag_pipeline import PipelineResources, extract_pdf_pages

router = APIRouter()


@router.get(
    "/interactions",
    response_model=list[InteractionSummary],
    summary="Daftar seluruh percakapan (semua user) untuk ditinjau instruktur",
    description="Pengganti langsung dari daftar `st.expander` di `correction_view()`.",
)
def list_interactions(
    only_uncorrected: bool = True,
    resources: PipelineResources = Depends(get_resources),
    _user: dict = Depends(require_role("instruktur")),
) -> list[InteractionSummary]:
    interactions = resources.conversation_store.list_interactions(only_uncorrected=only_uncorrected)
    return [InteractionSummary(**item) for item in interactions]


@router.post(
    "/correct",
    response_model=CorrectionResponse,
    summary="Simpan koreksi instruktur & injeksikan ke Knowledge Base",
    description=(
        "Pengganti tombol 'Simpan & Injeksi ke Knowledge Base' di "
        "`correction_view()`: menyuntikkan koreksi ke KB (Qdrant + BM25 + "
        "kb_susenas_maret2025.json) lalu menandai interaksi sebagai sudah dikoreksi."
    ),
)
def submit_correction(
    payload: CorrectionRequest,
    resources: PipelineResources = Depends(get_resources),
    user: dict = Depends(require_role("instruktur")),
) -> CorrectionResponse:
    try:
        chunk_id = resources.kb_manager.inject_correction(
            question=payload.question,
            correction_text=payload.correction_text,
            corrected_by=user["username"],
            collection_name=resources.retrieval_config.collection_name,
        )
        resources.conversation_store.mark_corrected(
            interaction_id=payload.interaction_id,
            correction_text=payload.correction_text,
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
    summary="Tandai jawaban chatbot sudah benar tanpa koreksi",
    description=(
        "Dipakai saat jawaban chatbot SUDAH BENAR apa adanya -- instruktur "
        "cukup menandai terverifikasi, TANPA menulis correction_text dan "
        "TANPA menyuntikkan chunk baru ke Knowledge Base. Beda dengan "
        "/correct, yang mengganti jawaban DAN menambah pengetahuan baru."
    ),
)
def verify(
    payload: VerifyRequest,
    resources: PipelineResources = Depends(get_resources),
    user: dict = Depends(require_role("instruktur")),
) -> VerifyResponse:
    resources.conversation_store.mark_verified(payload.interaction_id, verified_by=user["username"])
    return VerifyResponse(interaction_id=payload.interaction_id)


@router.post(
    "/upload-pdf",
    response_model=PDFUploadResponse,
    summary="Unggah dokumen PDF baru ke Knowledge Base",
    description="Pengganti langsung dari `upload_view()` -- memakai multipart/form-data karena melibatkan file.",
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

    file_bytes = await file.read()
    try:
        pages = extract_pdf_pages(file_bytes)
        chunk_ids = resources.kb_manager.inject_pdf(
            document_id=document_id.strip(),
            pages=pages,
            collection_name=resources.retrieval_config.collection_name,
            document_year=document_year,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gagal memproses PDF: {exc}",
        ) from exc

    return PDFUploadResponse(
        document_id=document_id.strip(),
        document_year=document_year,
        chunks_added=len(chunk_ids),
        chunk_ids=chunk_ids,
    )
