"""
Dependency bersama untuk endpoint-endpoint API.

`get_resources` adalah pengganti langsung dari `get_resources()` +
`@st.cache_resource` di app.py Streamlit: resource berat (model
embedding, koneksi Qdrant, dsb.) dibangun SEKALI saat server
start (lihat `lifespan` di app/main.py) dan disimpan di
`request.app.state.resources`. Semua endpoint mengambilnya lewat
dependency ini, bukan membangunnya ulang per-request.
"""

from __future__ import annotations

from fastapi import Request

from app.schemas.chat import SourceItem
from app.services.rag_pipeline import PipelineResources, format_source_label


def get_resources(request: Request) -> PipelineResources:
    return request.app.state.resources


def to_source_items(sources: list[dict]) -> list[SourceItem]:
    """Konversi list dict metadata sumber (dari rag_pipeline.py) menjadi
    SourceItem yang sudah divalidasi tipe & punya label siap-tampil.
    Sumber dengan label yang sama (mis. beberapa chunk dari halaman yang
    sama) digabung jadi satu, urutan kemunculan dipertahankan."""
    items: list[SourceItem] = []
    seen: set[str] = set()
    for source in sources:
        label = format_source_label(source)
        if label in seen:
            continue
        seen.add(label)
        items.append(SourceItem(**{**source, "label": label}))
    return items


def sources_for_user(item: dict) -> list[SourceItem]:
    """Sumber yang boleh ditampilkan ke petugas untuk 1 interaksi:
    - Corrected  -> hanya label koreksi instruktur (sumber retrieval
                    asli tidak lagi relevan dengan jawaban yang tampil);
    - Abstain    -> kosong (tidak ada jawaban, jadi tidak ada sumber);
    - lainnya    -> sumber hasil retrieval."""
    if item.get("corrected"):
        correction_source = {
            "source": "human_correction",
            "corrected_by": item.get("corrected_by"),
            "correction_date": item.get("correction_date"),
        }
        return to_source_items([correction_source])
    if item.get("is_abstained"):
        return []
    return to_source_items(item.get("sources") or [])
