from fastapi import APIRouter, Depends, HTTPException, status
import json
import logging
from fastapi.responses import StreamingResponse

from app.core.security import require_role
from app.dependencies import get_resources, to_source_items
from app.schemas.chat import AskRequest, AskResponse, InteractionDetail, RoomCreate, RoomOut
from app.services.rag_pipeline import PipelineResources, answer_question, answer_question_stream

router = APIRouter()
logger = logging.getLogger("chat")


def _friendly_error_message(exc: Exception) -> str:
    """
    Ubah exception mentah (mis. error dari Gemini API yang penuh kode/JSON teknis)
    jadi pesan yang enak dibaca user. Detail aslinya tetap dicatat lewat logger,
    jadi tidak hilang untuk keperluan debugging -- cuma tidak ditampilkan ke user.
    """
    raw = str(exc).lower()
    if any(kw in raw for kw in ["503", "overloaded", "unavailable", "high demand"]):
        return "Server sedang sibuk, coba tanyakan lagi beberapa saat lagi."
    if any(kw in raw for kw in ["429", "quota", "rate limit"]):
        return "Terlalu banyak permintaan saat ini, coba lagi sebentar lagi."
    if any(kw in raw for kw in ["timeout", "timed out", "deadline"]):
        return "Permintaan memakan waktu terlalu lama. Coba tanyakan ulang."
    return "Terjadi kesalahan saat memproses pertanyaan Anda. Coba lagi sebentar lagi."


# ---------------------------------------------------------------------
# Room percakapan -- CRUD ringan di atas ConversationStore.chat_rooms
# ---------------------------------------------------------------------

@router.get(
    "/rooms",
    response_model=list[RoomOut],
    summary="Daftar room percakapan milik user yang sedang login",
    description="Diurutkan dari yang paling baru dipakai. Dipanggil frontend saat sidebar chat dibuka.",
)
def list_rooms(
    resources: PipelineResources = Depends(get_resources),
    user: dict = Depends(require_role("user")),
) -> list[RoomOut]:
    return [RoomOut(**room) for room in resources.conversation_store.list_rooms(user["username"])]


@router.post(
    "/rooms",
    response_model=RoomOut,
    summary="Buka room percakapan yang siap dipakai",
    description=(
        "Kalau user sudah punya room KOSONG (belum ada pesan sama sekali), room itu "
        "yang dikembalikan -- BUKAN bikin room baru. Ini yang mencegah 'Percakapan "
        "Baru' menumpuk kosong tiap kali login ulang atau menekan tombol 'Percakapan "
        "Baru' berkali-kali tanpa pernah benar-benar dipakai. Room baru betulan hanya "
        "dibuat kalau memang belum ada room kosong sama sekali, atau kalau `title` "
        "custom diisi eksplisit."
    ),
)
def create_room(
    payload: RoomCreate,
    resources: PipelineResources = Depends(get_resources),
    user: dict = Depends(require_role("user")),
) -> RoomOut:
    if payload.title:
        return RoomOut(**resources.conversation_store.create_room(user["username"], title=payload.title))
    return RoomOut(**resources.conversation_store.get_or_create_active_room(user["username"]))


@router.delete(
    "/rooms/{room_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hapus room percakapan beserta seluruh riwayatnya",
)
def delete_room(
    room_id: str,
    resources: PipelineResources = Depends(get_resources),
    user: dict = Depends(require_role("user")),
) -> None:
    deleted = resources.conversation_store.delete_room(room_id, user["username"])
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room percakapan tidak ditemukan.",
        )


@router.post(
    "/ask",
    response_model=AskResponse,
    summary="Ajukan pertanyaan ke chatbot Susenas",
    description=(
        "Pengganti blok `if question:` di `chat_view()` (app.py Streamlit): "
        "retrieve -> generate (Gemini) -> deteksi abstain -> log ke "
        "ConversationStore, lalu kembalikan jawaban + sumber sebagai JSON."
    ),
)
def ask(
    payload: AskRequest,
    resources: PipelineResources = Depends(get_resources),
    user: dict = Depends(require_role("user")),
) -> AskResponse:
    if not resources.conversation_store.get_room(payload.room_id, user["username"]):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room percakapan tidak ditemukan.",
        )

    try:
        result = answer_question(resources, payload.question)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Gagal memproses pertanyaan di /ask: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_friendly_error_message(exc),
        ) from exc

    resources.conversation_store.log_interaction(
        username=user["username"],
        room_id=payload.room_id,
        question=payload.question,
        answer=result["answer"],
        context=result["context"],
        is_abstained=result["is_abstained"],
        sources=result["sources"],
    )

    return AskResponse(
        answer=result["answer"],
        context=result["context"],
        sources=to_source_items(result["sources"]),
        is_abstained=result["is_abstained"],
    )

@router.post(
    "/ask/stream",
    summary="Ajukan pertanyaan ke chatbot Susenas (versi streaming)",
    description=(
        "Sama seperti /ask, tapi jawaban dikirim per-potongan (NDJSON) "
        "supaya token pertama muncul lebih cepat di UI, alih-alih "
        "menunggu jawaban lengkap selesai digenerate."
    ),
)
def ask_stream(
    payload: AskRequest,
    resources: PipelineResources = Depends(get_resources),
    user: dict = Depends(require_role("user")),
) -> StreamingResponse:
    if not resources.conversation_store.get_room(payload.room_id, user["username"]):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room percakapan tidak ditemukan.",
        )

    def event_stream():
        try:
            for item in answer_question_stream(resources, payload.question):
                if isinstance(item, dict) and item.get("__final__"):
                    resources.conversation_store.log_interaction(
                        username=user["username"],
                        room_id=payload.room_id,
                        question=payload.question,
                        answer=item["answer"],
                        context=item["context"],
                        is_abstained=item["is_abstained"],
                        sources=item["sources"],
                    )
                    source_items = [s.model_dump() for s in to_source_items(item["sources"])]
                    yield json.dumps({
                        "type": "done",
                        "answer": item["answer"],
                        "context": item["context"],
                        "sources": source_items,
                        "is_abstained": item["is_abstained"],
                    }) + "\n"
                else:
                    yield json.dumps({"type": "token", "text": item}) + "\n"
        except Exception as exc:  # noqa: BLE001
            logger.exception("Gagal memproses pertanyaan di /ask/stream: %s", exc)
            yield json.dumps({
                "type": "error",
                "detail": _friendly_error_message(exc),
            }) + "\n"

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers={"X-Accel-Buffering": "no"},  # cegah nginx/reverse-proxy nge-buffer stream-nya
    )

@router.get(
    "/history",
    response_model=list[InteractionDetail],
    summary="Riwayat percakapan dalam satu room milik user yang sedang login",
    description=(
        "Pengganti bagian atas `chat_view()` yang membaca ulang riwayat dari "
        "ConversationStore setiap render -- di sini frontend cukup memanggil "
        "endpoint ini (dengan room_id) saat sebuah room dibuka / setelah "
        "mengirim pertanyaan baru di room tsb."
    ),
)
def history(
    room_id: str,
    resources: PipelineResources = Depends(get_resources),
    user: dict = Depends(require_role("user")),
) -> list[InteractionDetail]:
    if not resources.conversation_store.get_room(room_id, user["username"]):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room percakapan tidak ditemukan.",
        )
    interactions = resources.conversation_store.list_interactions_for_room(room_id, user["username"])
    return [
        InteractionDetail(
            **{k: v for k, v in item.items() if k != "sources"},
            sources=to_source_items(item["sources"]),
        )
        for item in interactions
    ]