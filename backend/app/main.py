"""
Entry point aplikasi FastAPI -- Asisten Susenas Maret 2025.

Jalankan dari folder `backend/`:
    uvicorn app.main:app --reload --port 8000

Lihat README.md di root proyek untuk panduan setup lengkap.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# Muat .env SEBELUM modul lain (terutama rag_pipeline) sempat membaca
# os.environ -- ini pengganti langsung dari `_load_secrets_to_env()`
# di app.py Streamlit, yang menyalin st.secrets ke environment variable.
load_dotenv()

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from app.api.v1 import auth as auth_router  # noqa: E402
from app.api.v1 import chat as chat_router  # noqa: E402
from app.api.v1 import instructor as instructor_router  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.services.rag_pipeline import build_resources  # noqa: E402

logger = logging.getLogger("uvicorn")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Bangun semua resource berat (embedding model, reranker, index
    Qdrant/BM25, koneksi Gemini, dsb.) SEKALI saat server start, lalu
    simpan di app.state -- pengganti langsung dari
    `@st.cache_resource` + `get_resources()` di app.py Streamlit."""
    settings = get_settings()
    logger.info("Base dir data yang dipakai: %s", settings.data_dir)
    logger.info("Menyiapkan resource RAG (model & index)... ini bisa makan waktu di percobaan pertama.")
    app.state.resources = build_resources(base_dir=settings.data_dir)

    # Log jumlah titik di Qdrant & chunk yang termuat -- cara cepat
    # memverifikasi index yang kepakai FastAPI sama persis (jumlahnya)
    # dengan yang dipakai versi Streamlit, tanpa perlu buka database
    # manual. Kalau angkanya beda/nol, itu tandanya data_dir mengarah
    # ke folder/KB yang salah, bukan masalah di logika retrieval-nya.
    try:
        collection_info = app.state.resources.qdrant_client.get_collection(
            app.state.resources.retrieval_config.collection_name
        )
        logger.info(
            "Qdrant collection '%s': %s titik vektor.",
            app.state.resources.retrieval_config.collection_name,
            collection_info.points_count,
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "Gagal membaca info collection Qdrant -- cek apakah qdrant_db di data_dir "
            "di atas benar-benar berisi collection yang sama dengan versi Streamlit."
        )
    logger.info(
        "BM25 index: %d chunk (harus SAMA dengan jumlah 'Total chunks dimuat' di atas "
        "dan dengan log Streamlit kalau KB-nya memang sama).",
        len(app.state.resources.retriever.chunks),
    )

    logger.info("Resource siap. Server FastAPI aktif.")
    yield
    logger.info("Server dimatikan.")


app = FastAPI(
    title="Asisten Susenas Maret 2025 -- API",
    description="Backend RAG untuk chatbot tanya-jawab Susenas Maret 2025 (retrieval hybrid + Gemini + abstention detector).",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS diaktifkan untuk berjaga-jaga kalau frontend dijalankan di server/port
# terpisah dari backend (mis. lewat `python -m http.server` atau Live Server).
# Kalau frontend di-serve lewat mount StaticFiles di bawah (satu origin yang
# sama dengan API), CORS ini sebenarnya tidak diperlukan, tapi tidak merugikan.
settings = get_settings()
allow_origins = ["*"] if settings.cors_origins.strip() == "*" else [
    origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    # allow_credentials=False -- autentikasi di sini pakai JWT lewat header
    # `Authorization: Bearer <token>` (localStorage), BUKAN cookie, jadi
    # frontend tidak pernah mengirim fetch dengan `credentials: "include"`.
    # allow_credentials=True dikombinasikan dengan allow_origins=["*"] justru
    # melanggar spesifikasi CORS browser (Access-Control-Allow-Origin: *
    # tidak sah kalau Access-Control-Allow-Credentials: true) -- selama ini
    # "aman" cuma karena kombinasi itu kebetulan tidak pernah benar-benar
    # dipakai. Kalau nanti pindah ke auth berbasis cookie, aktifkan lagi
    # bersamaan dengan mempersempit allow_origins ke domain frontend asli.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Router API ---
app.include_router(auth_router.router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(chat_router.router, prefix="/api/v1/chat", tags=["Chat (role: user)"])
app.include_router(instructor_router.router, prefix="/api/v1/instructor", tags=["Instruktur"])


@app.get("/api/health", tags=["Health"], summary="Cek status server")
def health() -> dict:
    return {"status": "ok"}


# --- Frontend statis ---
# Mount PALING TERAKHIR & di path "/" supaya tidak menutupi route API di
# atas (Starlette mencocokkan rute sesuai urutan didaftarkan). Dengan ini,
# `uvicorn app.main:app` sudah menyajikan API sekaligus UI dari satu proses/port.
#
# BUG YANG DIPERBAIKI: sebelumnya baris ini mem-mount folder `frontend/`
# MENTAH (source Vite+React: index.html, src/*.jsx, dll). Itu cuma benar
# untuk frontend vanilla JS versi lama (index.html + js/app.js yang bisa
# langsung dibuka browser tanpa build step). Sejak frontend dikonversi ke
# React (lihat frontend/README.md), `index.html` me-load `/src/main.jsx`
# lewat `<script type="module">` -- browser TIDAK BISA menjalankan JSX
# mentah atau me-resolve bare import seperti `import "react"` tanpa
# bundler. Kalau folder source ini yang di-mount, halamannya akan
# blank/error di console browser walau server start tanpa error apa pun.
#
# Yang benar: build dulu (`cd frontend && npm run build`), lalu sajikan
# folder HASIL build-nya (`frontend/dist/`) yang isinya sudah berupa
# HTML/JS/CSS statis siap pakai.
FRONTEND_DIST_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if FRONTEND_DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST_DIR), html=True), name="frontend")
else:
    logger.warning(
        "Folder frontend/dist tidak ditemukan di %s -- hanya API yang aktif. "
        "Jalankan `cd frontend && npm install && npm run build` dulu supaya "
        "frontend ikut disajikan dari satu proses/port yang sama, atau "
        "jalankan frontend secara terpisah lewat `npm run dev` (lihat "
        "frontend/README.md).",
        FRONTEND_DIST_DIR,
    )
