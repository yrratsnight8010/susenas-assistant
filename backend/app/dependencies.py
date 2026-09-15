"""
Dependency bersama untuk endpoint-endpoint API.

`get_resources` adalah pengganti langsung dari `get_resources()` +
`@st.cache_resource` di app.py Streamlit: resource berat (model
embedding, reranker, koneksi Qdrant, dsb.) dibangun SEKALI saat server
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
    SourceItem yang sudah divalidasi tipe & punya label siap-tampil."""
    return [SourceItem(**source, label=format_source_label(source)) for source in sources]
