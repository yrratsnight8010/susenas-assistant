"""
=====================================================================
RAG Pipeline -- Susenas Maret 2025 (versi deployment / FastAPI)
=====================================================================
Modul ini adalah PORTING LANGSUNG dari `rag_pipeline.py` versi Streamlit.

Kenapa hampir tidak berubah? Karena di versi Streamlit pun modul ini
sudah tidak bergantung pada `streamlit` sama sekali -- semua pemanggilan
`st.*` ada di app.py (lapisan UI), bukan di sini. Ini justru contoh
pemisahan tanggung jawab (separation of concerns) yang sudah benar
sejak awal, sehingga saat pindah ke FastAPI, seluruh logika inti
(retrieval, generation, abstention, KB manager, conversation store)
bisa dipakai ulang tanpa modifikasi. Yang berubah hanyalah SIAPA yang
memanggil fungsi-fungsi ini -- dulu app.py Streamlit, sekarang
endpoint-endpoint FastAPI di app/api/v1/.

Berisi HANYA komponen yang dibutuhkan untuk melayani pertanyaan secara
live: retrieval hybrid, generation (Gemini), dan abstention detector.
=====================================================================
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Optional

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, PointIdsList
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder, SentenceTransformer
from Sastrawi.Stemmer.StemmerFactory import StemmerFactory
from Sastrawi.StopWordRemover.StopWordRemoverFactory import StopWordRemoverFactory
from pypdf import PdfReader
import torch


from google import genai
from google.genai import types as genai_types
from groq import Groq

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    force=True,
)
logger = logging.getLogger("rag_pipeline")

from contextlib import contextmanager

@contextmanager
def _timed(label: str):
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        logger.info("[TIMING] %-20s %.3f detik", label, elapsed)

# =====================================================================
# KONFIGURASI
# =====================================================================

@dataclass
class AppPaths:
    """Path untuk versi deployment -- jauh lebih ringkas dari
    PipelinePaths versi riset karena app tidak butuh path checkpoint
    evaluasi, hanya path ke Knowledge Base."""

    base_dir: str = "./data"

    def __post_init__(self) -> None:
        self.kb_json = f"{self.base_dir}/kb_susenas_maret2025.json"
        self.qdrant_db = f"{self.base_dir}/qdrant_db"
        self.conversation_db = f"{self.base_dir}/conversations.db"
        self.kb_backup_dir = f"{self.base_dir}/kb_backups"


@dataclass
class RetrievalConfig:
    kb_json_path: str
    qdrant_db_path: str
    collection_name: str = "susenas_knowledgebase"
    embedding_model_name: str = "BAAI/bge-m3"
    reranker_model_name: str = "BAAI/bge-reranker-base"
    top_k_semantic: int = 5
    top_k_bm25: int = 5
    final_top_k: int = 5  # jumlah kandidat yang di-rerank -- makin kecil, makin cepat
                          # (reranker jalan sebanyak angka ini kali per pertanyaan)
    rrf_k: int = 60
    top_k_rerank: int = 5  # jumlah kandidat FINAL setelah rerank -- dinaikkan dari 3 ke 5
                           # supaya kalau ada 2 chunk yang membahas topik sama tapi
                           # bertentangan (mis. koreksi lama vs koreksi baru), keduanya
                           # punya peluang lebih besar sama-sama lolos ke context block,
                           # bukan cuma salah satu yang menang murni lewat rerank_score.


@dataclass
class GenerationConfig:
    gemini_model: str = "gemini-3.6-flash"
    temperature: float = 0.0
    max_output_tokens: int = 2048
    not_available_answer: str = "Jawaban tidak tersedia dalam sumber data yang diberikan."
    max_retries_per_key: int = 2


@dataclass
class AbstentionConfig:
    exact_phrase: str
    reference_paraphrases: list[str] = None
    semantic_similarity_threshold: float = 0.75  # hasil kalibrasi -- lihat notebook riset

    def __post_init__(self) -> None:
        if not self.reference_paraphrases:
            self.reference_paraphrases = [
                self.exact_phrase,
                "Informasi tersebut tidak tersedia dalam sumber data yang diberikan.",
                "Maaf, informasi ini tidak terdapat dalam konteks yang diberikan.",
                "Data mengenai hal ini tidak tersedia dalam knowledge base saat ini.",
                "Pertanyaan ini tidak dapat dijawab berdasarkan konteks yang ada.",
                "Konteks yang diberikan tidak memuat jawaban atas pertanyaan tersebut.",
                "Saya tidak menemukan informasi terkait pertanyaan ini di dalam data.",
            ]


GEMINI_KEY_NAMES = [
    "GEMINI_API_KEY_TEMP07", "GEMINI_API_KEY", "GEMINI_API_KEY_TEMP04",
    "GEMINI_API_KEY_TEMP01", "GEMINI_API_KEY_TEMP02", "GEMINI_API_KEY_TEMP06",
    "GEMINI_API_KEY_ZEF", "GEMINI_API_KEY_GLO", "GEMINI_API_KEY_NAB", "GEMINI_API_KEY_TEMP03",
]
GROQ_KEY_NAMES = ["GROQ_API_KEY", "GROQ_API_KEY_ZEF", "GROQ_API_KEY_NAB", "GROQ_API_KEY_GLO"]


# =====================================================================
# PREPROCESSING TEKS INDONESIA
# =====================================================================

class IndonesianTextPreprocessor:
    """Bungkus Sastrawi stemmer & stopword remover -- MAHAL untuk
    di-construct, jadi cukup diinisialisasi SEKALI (lewat lifespan
    startup FastAPI di app/main.py) lalu dipakai ulang."""

    def __init__(self) -> None:
        self._stemmer = StemmerFactory().create_stemmer()
        self._stopword_remover = StopWordRemoverFactory().create_stop_word_remover()

    def tokenize(self, text: str) -> list[str]:
        text = text.lower()
        text = self._stopword_remover.remove(text)
        text = self._stemmer.stem(text)
        return text.split()


# =====================================================================
# ROTATING API KEY MANAGER
# =====================================================================

class AllKeysExhaustedError(RuntimeError):
    """Semua API key (Gemini maupun Groq) sudah habis kuotanya."""


def load_api_keys(key_names: list[str]) -> list[dict[str, str]]:
    """Ambil API key dari environment variable. Di app/main.py,
    environment variable ini diisi dari file .env (lewat python-dotenv)
    sebelum modul ini dipakai -- pengganti st.secrets di versi Streamlit."""
    keys: list[dict[str, str]] = []
    for name in key_names:
        value = os.environ.get(name)
        if value:
            keys.append({"name": name, "key": value})

    if not keys:
        raise ValueError(
            "Tidak ada API key yang ditemukan di antara: " + ", ".join(key_names) +
            "\nPastikan sudah diisi di file .env (lihat .env.example)."
        )

    logger.info("API key tersedia: %d (%s)", len(keys), ", ".join(k["name"] for k in keys))
    return keys


class RotatingKeyManager:
    """Manajer generik rotasi API key saat kuota habis. Dipakai baik
    untuk Gemini (generation) maupun Groq."""

    QUOTA_ERROR_KEYWORDS = (
        "429", "resource_exhausted", "rate limit", "rate_limit",
        "too many requests", "quota", "exceeded", "limit exceeded",
        "tokens per day", "tpd",
    )

    def __init__(self, api_keys: list[dict[str, str]], client_factory: Callable[[str], Any]):
        if not api_keys:
            raise ValueError("api_keys tidak boleh kosong.")
        self._api_keys = api_keys
        self._client_factory = client_factory
        self._current_index = 0
        self._exhausted_indices: set[int] = set()
        self.client: Any = None
        self._activate_current_key()

    @property
    def current_name(self) -> str:
        return self._api_keys[self._current_index]["name"]

    def _activate_current_key(self) -> None:
        current_key = self._api_keys[self._current_index]["key"]
        self.client = self._client_factory(current_key)
        logger.info("Menggunakan key: %s", self.current_name)

    def rotate_key(self) -> bool:
        self._exhausted_indices.add(self._current_index)
        logger.warning("Key %s ditandai exhausted.", self.current_name)
        available = [i for i in range(len(self._api_keys)) if i not in self._exhausted_indices]
        if not available:
            logger.error("SEMUA API KEY SUDAH EXHAUSTED.")
            return False
        self._current_index = available[0]
        self._activate_current_key()
        return True

    @classmethod
    def is_quota_error(cls, error: Exception) -> bool:
        text = str(error).lower()
        return any(keyword in text for keyword in cls.QUOTA_ERROR_KEYWORDS)


def call_with_key_rotation(
    func: Callable[[Any, int], Any],
    manager: RotatingKeyManager,
    max_retries_per_key: int,
    base_backoff_sec: float = 1.0,
) -> Any:
    while True:
        last_error: Optional[Exception] = None
        for attempt in range(1, max_retries_per_key + 1):
            try:
                return func(manager.client, attempt)
            except Exception as e:  # noqa: BLE001
                last_error = e
                logger.warning(
                    "Key=%s attempt=%d/%d gagal: %s",
                    manager.current_name, attempt, max_retries_per_key, e,
                )
                if manager.is_quota_error(e):
                    logger.info("Terdeteksi quota/rate-limit.")
                    if not manager.rotate_key():
                        raise AllKeysExhaustedError("Semua API key sudah habis / exhausted.") from e
                    break
                if attempt < max_retries_per_key:
                    time.sleep(base_backoff_sec * (2 ** (attempt - 1)))
                else:
                    raise RuntimeError(
                        f"Gagal setelah {max_retries_per_key} percobaan: {last_error}"
                    ) from last_error


# =====================================================================
# HYBRID RETRIEVER
# =====================================================================

class HybridRetriever:
    """Menggabungkan semantic search (Qdrant) + BM25 + RRF fusion +
    cross-encoder reranking."""

    def __init__(
        self,
        config: RetrievalConfig,
        embedding_model: SentenceTransformer,
        qdrant_client: QdrantClient,
        reranker: CrossEncoder,
        chunks: list[dict[str, Any]],
        text_preprocessor: IndonesianTextPreprocessor,
    ):
        self.config = config
        self.embedding_model = embedding_model
        self.qdrant_client = qdrant_client
        self.reranker = reranker
        self.chunks = chunks
        self.text_preprocessor = text_preprocessor
        self.bm25_index: Optional[BM25Okapi] = None
        self.rebuild_bm25()

    def rebuild_bm25(self) -> None:
        corpus = [self.text_preprocessor.tokenize(c["text"]) for c in self.chunks]
        self.bm25_index = BM25Okapi(corpus)
        logger.info("BM25 index siap: %d dokumen.", len(self.chunks))

    def semantic_search(self, query: str) -> list[dict[str, Any]]:
        cfg = self.config
        query_vector = self.embedding_model.encode(query, normalize_embeddings=True).tolist()
        response = self.qdrant_client.query_points(
            collection_name=cfg.collection_name,
            query=query_vector,
            limit=cfg.top_k_semantic,
            with_payload=True,
        )
        return [
            {
                "chunk_id": point.payload["chunk_id"],
                "text": point.payload["text"],
                "score": float(point.score),
                "retrieval_type": "semantic",
                "metadata": point.payload,
            }
            for point in response.points
        ]

    def bm25_search(self, query: str) -> list[dict[str, Any]]:
        cfg = self.config
        assert self.bm25_index is not None, "BM25 index belum dibangun."
        scores = self.bm25_index.get_scores(self.text_preprocessor.tokenize(query))

        k = min(cfg.top_k_bm25, len(scores))
        if k == 0:
            return []
        top_indices = np.argpartition(scores, -k)[-k:]
        top_indices = top_indices[np.argsort(scores[top_indices])[::-1]]

        results = []
        for idx in top_indices:
            if scores[idx] <= 0:
                continue
            chunk = self.chunks[idx]
            results.append({
                "chunk_id": chunk["chunk_id"],
                "text": chunk["text"],
                "score": float(scores[idx]),
                "retrieval_type": "bm25",
                "metadata": chunk,
            })
        return results

    @staticmethod
    def rrf_fusion(
        semantic_results: list[dict[str, Any]],
        bm25_results: list[dict[str, Any]],
        rrf_k: int,
        final_top_k: int,
    ) -> list[dict[str, Any]]:
        fused: dict[str, dict[str, Any]] = {}

        def _accumulate(results: list[dict[str, Any]], source: str) -> None:
            for rank, item in enumerate(results, start=1):
                cid = item["chunk_id"]
                entry = fused.setdefault(cid, {
                    "chunk_id": cid, "text": item["text"], "metadata": item["metadata"],
                    "semantic_raw_score": 0.0, "bm25_raw_score": 0.0, "rrf_score": 0.0,
                })
                entry["rrf_score"] += 1.0 / (rrf_k + rank)
                entry[f"{source}_raw_score"] = item["score"]

        _accumulate(semantic_results, "semantic")
        _accumulate(bm25_results, "bm25")

        ranked = sorted(fused.values(), key=lambda x: x["rrf_score"], reverse=True)
        return ranked[:final_top_k]

    def score_candidates(self, query: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Hitung rerank_score untuk SEMUA kandidat."""
        if not candidates:
            return []
        pairs = [[query, item["text"]] for item in candidates]
        with _timed("rerank"):
            scores = self.reranker.predict(pairs)
        for item, score in zip(candidates, scores):
            item["rerank_score"] = float(score)
        return candidates

    def select_final(self, scored_candidates: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
        """Ambil top_k kandidat berdasarkan relevansi (rerank_score) saja.

        CATATAN: versi sebelumnya sempat memberi prioritas mutlak ke
        sumber (koreksi instruktur > dokumen > pengetahuan dasar) di
        atas relevansi. Itu dicabut lagi -- di praktiknya malah bikin
        jawaban makin berantakan/salah, karena 1 chunk koreksi yang
        cuma kebetulan berbagi kata dengan pertanyaan lain (via BM25)
        bisa menyalip chunk yang jauh lebih relevan hanya bermodal
        tier, walau topiknya sama sekali beda. Sekarang urutannya balik
        ke cara biasa/awal: murni berdasarkan rerank_score, seperti
        chunk lainnya -- kalau instruktur menulis koreksi yang memang
        relevan dengan suatu pertanyaan, dia akan menang secara alami
        lewat relevansi, bukan lewat perlakuan khusus."""
        ranked = sorted(scored_candidates, key=lambda c: c.get("rerank_score", 0.0), reverse=True)
        return ranked[:top_k]

    def retrieve(self, query: str) -> list[dict[str, Any]]:
        with _timed("semantic_search"):
            semantic_results = self.semantic_search(query)
        with _timed("bm25_search"):
            bm25_results = self.bm25_search(query)
        with _timed("rrf_fusion"):
            fused = self.rrf_fusion(semantic_results, bm25_results, self.config.rrf_k, self.config.final_top_k)
        # NOTE: timing "rerank" sudah dicatat di dalam score_candidates() itu sendiri --
        # sebelumnya di-wrap _timed("rerank") lagi di sini, jadi ke-log dobel dengan
        # angka identik (bukan rerank jalan 2x, cuma logging-nya yang dobel).
        scored = self.score_candidates(query, [dict(item) for item in fused])
        return self.select_final(scored, self.config.top_k_rerank)

def load_chunks(json_path: str) -> list[dict[str, Any]]:
    import json
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"Knowledge base tidak ditemukan:\n{json_path}")
    with open(json_path, "r", encoding="utf-8") as f:
        chunks = json.load(f)
    logger.info("Total chunks dimuat: %d", len(chunks))
    return chunks


def _select_device() -> str:
    return "cuda" if torch.cuda.is_available() else "cpu"


def load_embedding_model(model_name: str) -> SentenceTransformer:
    device = _select_device()
    logger.info("Loading embedding model %s (device=%s)", model_name, device)
    return SentenceTransformer(model_name, device=device)


def load_reranker(model_name: str) -> CrossEncoder:
    device = _select_device()
    logger.info("Loading reranker %s (backend=onnx, device=%s)", model_name, device,)
    return CrossEncoder(model_name, max_length=512,)

# def load_reranker(model_name: str) -> CrossEncoder:
#     reranker_path = "./data/reranker_base_onnx"
#     device = _select_device()
#     logger.info("Loading reranker %s (backend=onnx, device=%s)", reranker_path,)
#     return CrossEncoder(reranker_path, backend="onnx", max_length=512, model_kwargs={
#             "provider": "CPUExecutionProvider",},
#     )


def initialize_qdrant_client(db_path: str) -> QdrantClient:
    return QdrantClient(path=db_path)


# =====================================================================
# KNOWLEDGE BASE MANAGER -- injeksi koreksi instruktur & dokumen PDF baru
# =====================================================================

class KnowledgeBaseManager:
    """Menyuntikkan chunk baru (koreksi instruktur ATAU dokumen PDF baru)
    ke KB & index Qdrant/BM25 yang sedang berjalan, tanpa re-ingestion
    penuh -- dipanggil live dari endpoint instruktur di FastAPI."""

    def __init__(self, retriever: HybridRetriever, kb_json_path: str, backup_dir: str):
        self.retriever = retriever
        self.kb_json_path = kb_json_path
        self.backup_dir = backup_dir

    @staticmethod
    def _deterministic_chunk_id(prefix: str, seed_text: str) -> str:
        digest = hashlib.sha1(seed_text.encode("utf-8")).hexdigest()[:10]
        return f"{prefix}_{digest}"

    @staticmethod
    def _point_id_for(chunk_id: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk_id))

    def _backup_kb_json(self) -> None:
        if not os.path.exists(self.kb_json_path):
            return
        os.makedirs(self.backup_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(self.backup_dir, f"kb_snapshot_{timestamp}.json")
        shutil.copy2(self.kb_json_path, backup_path)
        logger.info("Snapshot KB disimpan: %s", backup_path)

    def _save_kb_json_atomic(self) -> None:
        tmp_path = self.kb_json_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self.retriever.chunks, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.kb_json_path)

    def _upsert_chunk(self, chunk: dict[str, Any], collection_name: str) -> None:
        """Tambahkan 1 chunk ke KB in-memory + Qdrant + KB JSON, lalu
        rebuild BM25 (wajib supaya BM25 tidak buta terhadap chunk baru)."""
        point_id = self._point_id_for(chunk["chunk_id"])
        vector = self.retriever.embedding_model.encode(chunk["text"], normalize_embeddings=True).tolist()
        self.retriever.qdrant_client.upsert(
            collection_name=collection_name,
            points=[PointStruct(id=point_id, vector=vector, payload=chunk)],
        )
        self.retriever.chunks.append(chunk)
        self._save_kb_json_atomic()
        self.retriever.rebuild_bm25()

    def inject_correction(
        self, question: str, correction_text: str, corrected_by: str, collection_name: str,
    ) -> str:
        """Injeksi 1 koreksi instruktur. Chunk gabungan pertanyaan+jawaban
        (supaya konteksnya tidak hilang, mis. kalau correction_text cuma
        'ya, lainnya'). chunk_id deterministik dari isi -- retry/klik
        ganda tidak akan menghasilkan duplikat."""
        combined_text = f"Permasalahan: {question.strip()}\nSolusi: {correction_text.strip()}"
        chunk_id = self._deterministic_chunk_id("CORR", combined_text)

        existing_ids = {c["chunk_id"] for c in self.retriever.chunks}
        if chunk_id in existing_ids:
            logger.info("SKIP -- koreksi ini sudah pernah diinjeksi (chunk_id=%s).", chunk_id)
            return chunk_id

        self._backup_kb_json()
        chunk = {
            "chunk_id": chunk_id,
            "text": combined_text,
            "document_id": "koreksi_instruktur",
            "source": "human_correction",
            "type": "correction",
            "content_category": "koreksi_instruktur",
            "page_start": None,
            "page_end": None,
            "bab": None,
            "subbab": None,
            "section_path": "Koreksi Manual Instruktur",
            "token_count": len(combined_text.split()),
            "char_count": len(combined_text),
            "created_at": datetime.now().isoformat(),
            "corrected_by": corrected_by,
            "correction_date": datetime.now().strftime("%Y-%m-%d"),
        }
        self._upsert_chunk(chunk, collection_name)
        logger.info("INJECTED koreksi -> chunk_id=%s", chunk_id)
        return chunk_id

    def inject_pdf(
        self, document_id: str, pages: list[str], collection_name: str,
        document_year: Optional[int] = None, chunk_size: int = 800, overlap: int = 100,
    ) -> list[str]:
        """Injeksi dokumen PDF baru: tiap halaman dipecah jadi beberapa
        chunk (chunk_size karakter, overlap antar-chunk supaya konteks
        di batas potongan tidak hilang). `document_year` disimpan
        sebagai metadata (ikut ditampilkan di label sumber lewat
        format_source_label), TIDAK dipakai untuk mengatur urutan
        retrieval -- urutan hasil retrieval murni berdasarkan relevansi
        (rerank_score), sama seperti chunk lainnya. Return list
        chunk_id yang berhasil ditambahkan (chunk kosong/duplikat
        dilewati)."""
        self._backup_kb_json()
        existing_ids = {c["chunk_id"] for c in self.retriever.chunks}
        injected_ids: list[str] = []

        for page_num, page_text in enumerate(pages, start=1):
            page_text = page_text.strip()
            if not page_text:
                continue
            start = 0
            while start < len(page_text):
                piece = page_text[start : start + chunk_size].strip()
                if piece:
                    chunk_id = self._deterministic_chunk_id("PDF", f"{document_id}::{page_num}::{piece[:50]}::{start}")
                    if chunk_id not in existing_ids:
                        chunk = {
                            "chunk_id": chunk_id,
                            "text": piece,
                            "document_id": document_id,
                            "document_year": document_year,
                            "source": "uploaded_pdf",
                            "type": "document",
                            "content_category": "dokumen_unggahan",
                            "page_start": page_num,
                            "page_end": page_num,
                            "bab": None,
                            "subbab": None,
                            "section_path": document_id,
                            "token_count": len(piece.split()),
                            "char_count": len(piece),
                            "created_at": datetime.now().isoformat(),
                        }
                        self._upsert_chunk(chunk, collection_name)
                        existing_ids.add(chunk_id)
                        injected_ids.append(chunk_id)
                start += chunk_size - overlap

        logger.info("PDF '%s' (edisi %s) diinjeksi: %d chunk baru.", document_id, document_year, len(injected_ids))
        return injected_ids

    def delete_chunk(self, chunk_id: str, collection_name: str) -> bool:
        """Cabut 1 chunk dari KB in-memory + kb JSON + Qdrant, lalu rebuild
        BM25. Dipakai saat instruktur mencabut sebuah koreksi yang ternyata
        SALAH dari daftar log koreksi (lihat endpoint DELETE
        /instructor/corrections/{correction_id}). Return False kalau
        chunk_id sudah tidak ada di KB (mis. sudah pernah dihapus)."""
        idx = next((i for i, c in enumerate(self.retriever.chunks) if c["chunk_id"] == chunk_id), None)
        if idx is None:
            logger.info("SKIP hapus -- chunk_id=%s sudah tidak ada di KB.", chunk_id)
            return False

        self._backup_kb_json()
        self.retriever.chunks.pop(idx)
        self._save_kb_json_atomic()
        self.retriever.rebuild_bm25()

        point_id = self._point_id_for(chunk_id)
        self.retriever.qdrant_client.delete(
            collection_name=collection_name,
            points_selector=PointIdsList(points=[point_id]),
        )
        logger.info("DELETED chunk -> chunk_id=%s", chunk_id)
        return True


def extract_pdf_pages(file_bytes: bytes) -> list[str]:
    """Ekstrak teks per halaman dari file PDF (dalam bentuk bytes,
    sesuai yang diterima dari UploadFile.read() di endpoint FastAPI)."""
    import io

    reader = PdfReader(io.BytesIO(file_bytes))
    return [page.extract_text() or "" for page in reader.pages]


# =====================================================================
# CONVERSATION STORE -- log percakapan untuk dashboard instruktur
# =====================================================================

class ConversationStore:
    """Penyimpanan percakapan berbasis SQLite -- perlu persisten &
    dibagi lintas sesi/user, supaya instruktur bisa meninjau pertanyaan
    yang diajukan SEMUA user dari endpoint terpisah."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS interactions (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT,
                    username TEXT,
                    question TEXT,
                    answer TEXT,
                    context TEXT,
                    is_abstained INTEGER,
                    corrected INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS corrections (
                    id TEXT PRIMARY KEY,
                    interaction_id TEXT,
                    correction_text TEXT,
                    corrected_by TEXT,
                    correction_date TEXT,
                    chunk_id TEXT
                )
            """)
            # ROOM PERCAKAPAN -- satu user bisa punya banyak room (mirip
            # ChatGPT/Claude), tiap room adalah satu utas tanya-jawab
            # terpisah. Lihat blok method create_room/list_rooms/dst di
            # bawah untuk detail lengkapnya.
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_rooms (
                    id TEXT PRIMARY KEY,
                    username TEXT,
                    title TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            self._ensure_column(conn, "interactions", "sources_json", "TEXT")
            self._ensure_column(conn, "interactions", "room_id", "TEXT")
            # verified = instruktur menandai jawaban chatbot SUDAH BENAR
            # apa adanya, TANPA menulis koreksi & TANPA injeksi chunk baru
            # ke KB -- beda dari 'corrected' (lihat mark_verified()).
            self._ensure_column(conn, "interactions", "verified", "INTEGER DEFAULT 0")
            self._ensure_column(conn, "interactions", "verified_by", "TEXT")
            self._ensure_column(conn, "interactions", "verified_at", "TEXT")
            # timestamp presisi (bukan cuma tanggal) -- dipakai untuk
            # mengurutkan log koreksi (list_corrections) secara akurat.
            # Baris lama (sebelum kolom ini ada) akan NULL, jadi
            # list_corrections tetap fallback ke rowid untuk baris itu.
            self._ensure_column(conn, "corrections", "correction_at", "TEXT")

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table: str, column: str, col_type: str) -> None:
        existing_cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing_cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")

    # -----------------------------------------------------------------
    # ROOM PERCAKAPAN
    # -----------------------------------------------------------------

    DEFAULT_ROOM_TITLE = "Percakapan Baru"

    def create_room(self, username: str, title: Optional[str] = None) -> dict[str, Any]:
        room_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        final_title = title or self.DEFAULT_ROOM_TITLE
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO chat_rooms (id, username, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (room_id, username, final_title, now, now),
            )
        return {"id": room_id, "title": final_title, "created_at": now, "updated_at": now}

    def list_rooms(self, username: str) -> list[dict[str, Any]]:
        """Daftar room milik satu user, yang paling baru dipakai duluan.

        Migrasi sekali-jalan: baris `interactions` lama dari sebelum
        fitur room ini ada punya `room_id` NULL -- baris seperti itu
        dikumpulkan otomatis ke satu room "Percakapan Lama" supaya
        histori lama tidak hilang begitu fitur ini diaktifkan."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            orphan_count = conn.execute(
                "SELECT COUNT(*) AS n FROM interactions WHERE username = ? AND room_id IS NULL",
                (username,),
            ).fetchone()["n"]

        if orphan_count:
            legacy_room = self.create_room(username, title="Percakapan Lama")
            with self._connect() as conn:
                conn.execute(
                    "UPDATE interactions SET room_id = ? WHERE username = ? AND room_id IS NULL",
                    (legacy_room["id"], username),
                )

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, title, created_at, updated_at FROM chat_rooms WHERE username = ? ORDER BY updated_at DESC",
                (username,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_or_create_active_room(self, username: str) -> dict[str, Any]:
        """Kembalikan SATU room kosong (belum pernah ada pesan) milik
        user kalau ada, atau buat room baru kalau belum ada sama
        sekali. Inilah yang mencegah "Percakapan Baru" kosong menumpuk
        tiap kali user login ulang atau menekan tombol "Percakapan
        Baru" tanpa pernah benar-benar mengirim pesan -- persis
        seperti ChatGPT/Claude: room baru yang tidak dipakai tidak
        pernah benar-benar tersimpan sebagai thread terpisah.

        Dipanggil dari endpoint POST /rooms (lihat api/v1/chat.py) --
        baik saat login baru maupun saat tombol "Percakapan Baru"
        diklik, keduanya lewat jalur yang sama ini."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            empty_rooms = conn.execute(
                """
                SELECT r.id, r.title, r.created_at, r.updated_at
                FROM chat_rooms r
                WHERE r.username = ?
                  AND NOT EXISTS (SELECT 1 FROM interactions i WHERE i.room_id = r.id)
                ORDER BY r.updated_at DESC
                """,
                (username,),
            ).fetchall()

        if empty_rooms:
            keeper = dict(empty_rooms[0])
            # Beres-beres: kalau ternyata ada LEBIH DARI SATU room kosong
            # (peninggalan dari sebelum logic ini ada), sisakan cuma
            # yang paling baru -- baru dipakai user, sisanya dibuang.
            if len(empty_rooms) > 1:
                stale_ids = [(row["id"],) for row in empty_rooms[1:]]
                with self._connect() as conn:
                    conn.executemany("DELETE FROM chat_rooms WHERE id = ?", stale_ids)
            return keeper

        return self.create_room(username)

    def get_room(self, room_id: str, username: str) -> Optional[dict[str, Any]]:
        """Ambil 1 room MILIK `username` tsb -- dipakai sebagai
        pengecekan kepemilikan sebelum /ask, /history, atau delete_room
        memproses sebuah room_id dari request user."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT id, title, created_at, updated_at FROM chat_rooms WHERE id = ? AND username = ?",
                (room_id, username),
            ).fetchone()
        return dict(row) if row else None

    def delete_room(self, room_id: str, username: str) -> bool:
        """Hapus room beserta seluruh interaksi & koreksi di dalamnya.
        Mengembalikan False (tanpa menghapus apa pun) kalau room tidak
        ditemukan atau bukan milik `username` -- supaya user tidak bisa
        menghapus room milik user lain lewat endpoint ini."""
        if not self.get_room(room_id, username):
            return False
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM corrections WHERE interaction_id IN (SELECT id FROM interactions WHERE room_id = ?)",
                (room_id,),
            )
            conn.execute("DELETE FROM interactions WHERE room_id = ?", (room_id,))
            conn.execute("DELETE FROM chat_rooms WHERE id = ?", (room_id,))
        return True

    def _touch_room(self, conn: sqlite3.Connection, room_id: str, first_question: Optional[str] = None) -> None:
        """Update updated_at room setiap ada pesan baru (supaya urutan
        di sidebar mengikuti yang paling baru DIPAKAI, bukan cuma
        dibuat). Kalau room masih berjudul default, judulnya diganti
        otomatis dari pertanyaan pertama -- mirip auto-title ChatGPT --
        supaya sidebar tidak penuh "Percakapan Baru"."""
        now = datetime.now().isoformat()
        row = conn.execute("SELECT title FROM chat_rooms WHERE id = ?", (room_id,)).fetchone()
        current_title = row[0] if row else None
        if first_question and current_title == self.DEFAULT_ROOM_TITLE:
            short_title = first_question.strip().splitlines()[0][:60] or self.DEFAULT_ROOM_TITLE
            conn.execute("UPDATE chat_rooms SET title = ?, updated_at = ? WHERE id = ?", (short_title, now, room_id))
        else:
            conn.execute("UPDATE chat_rooms SET updated_at = ? WHERE id = ?", (now, room_id))

    def log_interaction(
        self, username: str, room_id: str, question: str, answer: str, context: str, is_abstained: bool,
        sources: Optional[list[dict[str, Any]]] = None,
    ) -> str:
        interaction_id = str(uuid.uuid4())
        sources_json = json.dumps(sources or [], ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO interactions (id, timestamp, username, question, answer, context, is_abstained, corrected, sources_json, room_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)",
                (interaction_id, datetime.now().isoformat(), username, question, answer, context, int(is_abstained), sources_json, room_id),
            )
            self._touch_room(conn, room_id, first_question=question)
        return interaction_id

    def list_interactions(self, only_uncorrected: bool = False) -> list[dict[str, Any]]:
        """`only_uncorrected=True` berarti "belum ditindak sama sekali"
        -- yaitu belum dikoreksi MAUPUN belum diverifikasi, supaya
        interaksi yang sudah ditandai selesai lewat jalur mana pun
        hilang dari antrean instruktur."""
        query = "SELECT id, timestamp, username, question, answer, is_abstained, corrected, verified FROM interactions"
        if only_uncorrected:
            query += " WHERE corrected = 0 AND verified = 0"
        query += " ORDER BY timestamp DESC"
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query).fetchall()
        return [{**dict(row), "verified": bool(row["verified"])} for row in rows]

    def list_interactions_for_room(self, room_id: str, username: str) -> list[dict[str, Any]]:
        """Riwayat percakapan MILIK SATU ROOM (dan dipastikan juga milik
        `username` yang sama), urut kronologis (lama -> baru), sudah
        menyertakan correction_text & daftar sumber kalau ada."""
        query = """
            SELECT i.id, i.timestamp, i.username, i.question, i.answer, i.context,
                   i.is_abstained, i.corrected, i.verified, i.verified_by, i.verified_at,
                   i.sources_json,
                   c.correction_text, c.corrected_by, c.correction_date
            FROM interactions i
            LEFT JOIN corrections c ON c.interaction_id = i.id
            WHERE i.room_id = ? AND i.username = ?
            ORDER BY i.timestamp ASC
        """
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, (room_id, username)).fetchall()

        results = []
        for row in rows:
            item = dict(row)
            item["verified"] = bool(item["verified"])
            try:
                item["sources"] = json.loads(item.pop("sources_json") or "[]")
            except (json.JSONDecodeError, TypeError):
                item["sources"] = []  # baris lama dari sebelum kolom ini ada
            results.append(item)
        return results

    def mark_corrected(self, interaction_id: str, correction_text: str, corrected_by: str, chunk_id: str) -> None:
        now = datetime.now()
        with self._connect() as conn:
            conn.execute("UPDATE interactions SET corrected = 1 WHERE id = ?", (interaction_id,))
            conn.execute(
                "INSERT INTO corrections "
                "(id, interaction_id, correction_text, corrected_by, correction_date, chunk_id, correction_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), interaction_id, correction_text, corrected_by,
                 now.strftime("%Y-%m-%d"), chunk_id, now.isoformat()),
            )

    def list_corrections(self) -> list[dict[str, Any]]:
        """Log seluruh koreksi yang pernah diinjeksi ke KB -- untuk endpoint
        GET /instructor/corrections, supaya instruktur bisa meninjau (dan
        kalau perlu mencabut lewat delete_correction()) koreksi yang salah.
        Diurutkan dari yang PALING BARU diinjeksi. `correction_at` (timestamp
        presisi) dipakai kalau ada; baris lama sebelum kolom ini ditambahkan
        akan NULL, jadi fallback ke rowid (urutan insert) supaya tetap
        terurut benar tanpa mematahkan histori lama."""
        query = """
            SELECT c.id AS correction_id, c.interaction_id, c.correction_text,
                   c.corrected_by, c.correction_date, c.correction_at, c.chunk_id,
                   i.username, i.question AS original_question
            FROM corrections c
            JOIN interactions i ON i.id = c.interaction_id
            ORDER BY COALESCE(c.correction_at, '') DESC, c.rowid DESC
        """
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query).fetchall()
        return [dict(row) for row in rows]

    def get_correction(self, correction_id: str) -> Optional[dict[str, Any]]:
        """Ambil 1 baris koreksi lengkap (termasuk `original_question` &
        `chunk_id` LAMA) -- dipakai endpoint PATCH /instructor/corrections/{id}
        sebelum re-injeksi, supaya tahu pertanyaan aslinya dan chunk mana
        yang harus dicabut setelah versi baru berhasil disuntikkan."""
        query = """
            SELECT c.id AS correction_id, c.interaction_id, c.correction_text,
                   c.corrected_by, c.correction_date, c.correction_at, c.chunk_id,
                   i.username, i.question AS original_question
            FROM corrections c
            JOIN interactions i ON i.id = c.interaction_id
            WHERE c.id = ?
        """
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(query, (correction_id,)).fetchone()
        return dict(row) if row else None

    def update_correction(self, correction_id: str, correction_text: str, corrected_by: str, chunk_id: str) -> bool:
        """Perbarui teks sebuah koreksi yang sudah ada + `chunk_id` (hasil
        re-injeksi ke KB dengan isi baru) DAN geser correction_date/
        correction_at ke SEKARANG. Menggeser tanggal ini penting: aturan
        'ambil informasi paling baru' di build_system_prompt membandingkan
        tanggal informasi antar-KONTEKS, jadi versi yang baru diedit harus
        tercatat sebagai yang TERBARU supaya tetap menang dibanding
        konteks lain yang (mungkin) bertentangan dengannya."""
        now = datetime.now()
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE corrections SET correction_text = ?, corrected_by = ?, "
                "correction_date = ?, correction_at = ?, chunk_id = ? WHERE id = ?",
                (correction_text, corrected_by, now.strftime("%Y-%m-%d"), now.isoformat(), chunk_id, correction_id),
            )
        return cur.rowcount > 0

    def delete_correction(self, correction_id: str) -> Optional[str]:
        """Hapus 1 baris di tabel `corrections` & reset interaksi terkait
        (corrected=0) supaya interaksi itu kembali muncul di antrean
        instruktur seperti belum pernah dikoreksi. Return chunk_id yang
        harus ikut dihapus dari KB/Qdrant (lewat KnowledgeBaseManager.
        delete_chunk), atau None kalau correction_id tidak ditemukan."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT interaction_id, chunk_id FROM corrections WHERE id = ?", (correction_id,)
            ).fetchone()
            if row is None:
                return None
            conn.execute("DELETE FROM corrections WHERE id = ?", (correction_id,))
            conn.execute("UPDATE interactions SET corrected = 0 WHERE id = ?", (row["interaction_id"],))
        return row["chunk_id"]

    def mark_verified(self, interaction_id: str, verified_by: str) -> None:
        """Tandai jawaban chatbot SUDAH BENAR apa adanya -- TANPA
        menulis correction_text & TANPA menyuntikkan chunk baru ke KB
        (karena jawabannya memang sudah tepat, tidak ada yang perlu
        ditambahkan ke pengetahuan). Ini yang membedakannya dari
        mark_corrected(): tidak ada baris baru di tabel `corrections`,
        cuma menandai kolom verified di `interactions`."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE interactions SET verified = 1, verified_by = ?, verified_at = ? WHERE id = ?",
                (verified_by, datetime.now().isoformat(), interaction_id),
            )


# =====================================================================
# RAG GENERATION (GEMINI)
# =====================================================================

def _context_date_label(chunk: dict[str, Any]) -> str:
    """Ambil label tanggal/edisi 1 chunk untuk ditampilkan ke LLM, supaya
    LLM punya dasar EKSPLISIT untuk memutuskan mana yang lebih baru kalau
    ada 2+ KONTEKS yang bertentangan (lihat aturan 6 di build_system_prompt).
    Tanpa ini, instruksi "pilih yang terbaru" di prompt tidak ada gunanya
    karena LLM tidak pernah melihat tanggal apa pun di teks konteksnya."""
    meta = chunk.get("metadata") or chunk
    correction_date = meta.get("correction_date")
    if correction_date:
        return f"koreksi instruktur, {correction_date}"
    document_year = meta.get("document_year")
    if document_year:
        return f"dokumen edisi {document_year}"
    return "tidak diketahui"


def build_context_block(retrieved_chunks: list[dict[str, Any]]) -> str:
    blocks = []
    for i, chunk in enumerate(retrieved_chunks, start=1):
        date_label = _context_date_label(chunk)
        blocks.append(f"[Konteks {i} | tanggal informasi: {date_label}]\n{chunk['text']}")
    return "\n\n".join(blocks)


def format_source_label(chunk: dict[str, Any]) -> str:
    """Terjemahkan metadata 1 chunk jadi label sumber yang mudah dibaca
    user (nama dokumen + halaman, atau info koreksi instruktur).
    Menangani KEDUA bentuk: chunk hasil retrieve() (field di
    chunk['metadata']) maupun chunk ringkas dari ConversationStore
    (field sudah di level atas)."""
    meta = chunk.get("metadata") or chunk
    source = meta.get("source", "")

    if source == "human_correction":
        corrected_by = meta.get("corrected_by", "-")
        correction_date = meta.get("correction_date", "-")
        return f"🛠️ Koreksi instruktur ({corrected_by}, {correction_date})"

    document_id = meta.get("document_id") or "Dokumen tidak diketahui"
    document_year = meta.get("document_year")
    page_start = meta.get("page_start")
    page_end = meta.get("page_end")

    label = f"📄 {document_id}"
    if document_year:
        label += f" ({document_year})"
    if page_start and page_end and page_start == page_end:
        label += f" — hal. {page_start}"
    elif page_start and page_end:
        label += f" — hal. {page_start}-{page_end}"
    return label


def extract_source_metadata(chunk: dict[str, Any]) -> dict[str, Any]:
    """Ambil HANYA field yang dibutuhkan format_source_label dari 1
    chunk hasil retrieve(), untuk disimpan ringkas ke ConversationStore."""
    meta = chunk.get("metadata") or chunk
    return {
        "source": meta.get("source"),
        "document_id": meta.get("document_id"),
        "document_year": meta.get("document_year"),
        "page_start": meta.get("page_start"),
        "page_end": meta.get("page_end"),
        "corrected_by": meta.get("corrected_by"),
        "correction_date": meta.get("correction_date"),
    }


def build_system_prompt(gen_config: GenerationConfig) -> str:
    return f"""
Kamu adalah asisten tanya-jawab tentang data Susenas Maret 2025.

Jawab pertanyaan HANYA berdasarkan KONTEKS yang diberikan.

ATURAN PENTING:

1. Jangan mengarang atau menambahkan informasi
   yang tidak ada di KONTEKS.

2. Jika KONTEKS tidak memuat informasi yang cukup
   untuk menjawab pertanyaan, jawab PERSIS:

"{gen_config.not_available_answer}"

Tanpa tambahan apa pun.

3. Jika KONTEKS memuat jawabannya, jawab secara:
   - ringkas
   - jelas
   - langsung menjawab pertanyaan

4. Pertahankan angka, istilah teknis, dan terminologi
   resmi sesuai KONTEKS -- JANGAN mengganti angka atau istilah
   dengan versi yang tidak disebutkan di KONTEKS.

5. PENGECUALIAN untuk aturan 4: kamu BOLEH melakukan konversi
   satuan yang pasti dan tidak ambigu (misalnya "1 tahun" menjadi
   "12 bulan", atau sebaliknya) jika pertanyaan memakai satuan
   yang berbeda dari KONTEKS. Ini BUKAN mengarang -- ini
   menyajikan angka yang SAMA dalam satuan yang ditanyakan.
   Sebutkan satuan asli dari KONTEKS di jawabanmu supaya tetap
   tertelusuri (contoh: "12 bulan (1 tahun) atau lebih").
   Kalau pertanyaan meminta detail yang benar-benar tidak
   disebutkan di KONTEKS (bukan sekadar beda satuan), tetap
   ikuti aturan 2.

6. Setiap KONTEKS diberi label "tanggal informasi" di headernya.
   Jika ada DUA ATAU LEBIH KONTEKS yang membahas HAL YANG SAMA
   tapi isinya BERTENTANGAN satu sama lain, kamu WAJIB:
   - membandingkan tanggal informasi antar-KONTEKS yang bertentangan
     tersebut,
   - menjawab HANYA berdasarkan KONTEKS dengan tanggal informasi
     PALING BARU,
   - mengabaikan KONTEKS yang lebih lama sepenuhnya -- JANGAN
     mencampur/menggabungkan isi dari KONTEKS lama dan baru yang
     saling bertentangan itu ke dalam satu jawaban.
   Aturan ini HANYA berlaku kalau KONTEKS-KONTEKS itu benar-benar
   membahas hal yang sama tapi bertentangan. Kalau isinya cuma
   saling melengkapi (tidak bertentangan), gabungkan seperti biasa.
"""


def generate_answer(
    query: str, retrieved_chunks: list[dict[str, Any]], client: Any, gen_config: GenerationConfig
) -> tuple[str, str]:
    context_block = build_context_block(retrieved_chunks)
    prompt = f"KONTEKS:\n\n{context_block}\n\n\nPERTANYAAN:\n\n{query}\n\n\nJAWABAN:\n"
    response = client.models.generate_content(
        model=gen_config.gemini_model,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            system_instruction=build_system_prompt(gen_config),
            temperature=gen_config.temperature,
            max_output_tokens=gen_config.max_output_tokens,
            thinking_config=genai_types.ThinkingConfig(thinking_level=genai_types.ThinkingLevel.MINIMAL),
        ),
    )
    answer_text = (response.text or "").strip()

    finish_reason = None
    if response.candidates:
        finish_reason = getattr(response.candidates[0], "finish_reason", None)
    if finish_reason is not None and str(finish_reason).upper().endswith("MAX_TOKENS"):
        logger.warning(
            "Jawaban kemungkinan TERPOTONG (finish_reason=MAX_TOKENS) untuk query: %.80s", query,
        )

    return answer_text, context_block


def generate_answer_with_rotation(
    query: str, retrieved_chunks: list[dict[str, Any]], manager: RotatingKeyManager, gen_config: GenerationConfig
) -> tuple[str, str]:
    def _call(client: Any, _attempt: int) -> tuple[str, str]:
        return generate_answer(query, retrieved_chunks, client, gen_config)

    return call_with_key_rotation(_call, manager, gen_config.max_retries_per_key)

def generate_answer_stream(
    query: str, retrieved_chunks: list[dict[str, Any]], client: Any, gen_config: GenerationConfig
):
    """Generator: yield potongan teks jawaban dari Gemini satu per satu,
    begitu tiap chunk datang dari API (bukan menunggu jawaban lengkap)."""
    context_block = build_context_block(retrieved_chunks)
    prompt = f"KONTEKS:\n\n{context_block}\n\n\nPERTANYAAN:\n\n{query}\n\n\nJAWABAN:\n"
    stream = client.models.generate_content_stream(
        model=gen_config.gemini_model,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            system_instruction=build_system_prompt(gen_config),
            temperature=gen_config.temperature,
            max_output_tokens=gen_config.max_output_tokens,
            thinking_config=genai_types.ThinkingConfig(thinking_level=genai_types.ThinkingLevel.MINIMAL),
        ),
    )
    for chunk in stream:
        if chunk.text:
            yield chunk.text


def generate_answer_stream_with_rotation(
    query: str, retrieved_chunks: list[dict[str, Any]], manager: RotatingKeyManager, gen_config: GenerationConfig
):
    """Sama seperti generate_answer_stream, tapi dengan rotasi API key.

    CATATAN PENTING: rotasi HANYA bisa dilakukan kalau gagal SEBELUM
    token pertama terkirim ke user (mis. quota habis saat request
    dibuka). Kalau errornya muncul DI TENGAH stream -- setelah sebagian
    jawaban sudah terlanjur dikirim ke browser -- rotasi tidak mungkin
    dilakukan dengan mulus (user sudah lihat separuh jawaban dari key
    A, tidak masuk akal menyambungnya dengan key B). Untuk kasus itu,
    exception dilempar apa adanya ke endpoint."""
    last_error: Optional[Exception] = None
    for attempt in range(1, gen_config.max_retries_per_key + 1):
        try:
            stream = generate_answer_stream(query, retrieved_chunks, manager.client, gen_config)
            first_chunk = next(stream, None)  # memicu request; error quota muncul di sini
            if first_chunk is not None:
                yield first_chunk
            yield from stream
            return
        except Exception as e:  # noqa: BLE001
            last_error = e
            logger.warning(
                "Key=%s attempt=%d/%d gagal (stream): %s",
                manager.current_name, attempt, gen_config.max_retries_per_key, e,
            )
            if manager.is_quota_error(e):
                if not manager.rotate_key():
                    raise AllKeysExhaustedError("Semua API key sudah habis / exhausted.") from e
                continue
            raise
    raise RuntimeError(f"Gagal streaming setelah beberapa percobaan: {last_error}") from last_error


def answer_question_stream(resources: PipelineResources, question: str):
    """Versi streaming dari answer_question()."""
    
    # 1. Ukur waktu retrieval menggunakan _timed
    with _timed("retrieve_total"):
        retrieved_chunks = resources.retriever.retrieve(question)
        
    context_block = build_context_block(retrieved_chunks)

    answer_parts: list[str] = []
    
    # Variabel untuk melacak waktu awal generate
    start_gen_time = time.perf_counter()
    ttft = None

    # 2. Proses streaming generation & pengukuran TTFT di sini
    for piece in generate_answer_stream_with_rotation(
        question, retrieved_chunks, resources.gemini_manager, resources.gen_config
    ):
        # TTFT dihitung saat chunk/potongan teks PERTAMA kali berhasil di-yield
        if ttft is None:
            ttft = time.perf_counter() - start_gen_time
            # Catat menggunakan logger agar formatnya sama dengan _timed
            logger.info("[TIMING] %-20s %.3f detik", "time_to_first_token", ttft)

        answer_parts.append(piece)
        yield piece

    answer_text = "".join(answer_parts).strip()
    
    # 3. Ukur waktu abstention detection menggunakan _timed
    with _timed("abstention_detect"):
        is_abstained = resources.abstention_detector.detect(answer_text)
        
    sources = [extract_source_metadata(c) for c in retrieved_chunks]

    # Kirim metadata final termasuk nilai ttft-nya
    yield {
        "__final__": True,
        "answer": answer_text,
        "context": context_block,
        "sources": sources,
        "is_abstained": is_abstained,
        "ttft": ttft, # Disimpan juga di metadata jika ingin dikirim ke frontend
    }

# =====================================================================
# ABSTENTION DETECTOR
# =====================================================================

class AbstentionDetector:
    """Deteksi abstain hybrid: rule exact-match + semantic similarity."""

    def __init__(self, config: AbstentionConfig, embedding_model: SentenceTransformer):
        self.config = config
        self.embedding_model = embedding_model
        self._reference_embeddings = embedding_model.encode(
            config.reference_paraphrases, normalize_embeddings=True
        )

    def _exact_match(self, answer_text: str) -> bool:
        text = str(answer_text).strip()
        for quote_char in ('"', "'", "\u201c", "\u201d", "\u2018", "\u2019"):
            text = text.strip(quote_char)
        return text.strip() == self.config.exact_phrase.strip()

    def _semantic_similarity(self, answer_text: str) -> float:
        text = str(answer_text).strip()
        if not text:
            return 0.0
        answer_embedding = self.embedding_model.encode(text, normalize_embeddings=True)
        return float(np.max(self._reference_embeddings @ answer_embedding))

    def detect(self, answer_text: str) -> bool:
        """Return True kalau jawaban terdeteksi sebagai penolakan/abstain."""
        exact = self._exact_match(answer_text)
        similarity = self._semantic_similarity(answer_text)
        semantic_flag = similarity >= self.config.semantic_similarity_threshold
        return exact or semantic_flag


# =====================================================================
# RESOURCE BUNDLE & CACHING
# =====================================================================

@dataclass
class PipelineResources:
    paths: AppPaths
    retrieval_config: RetrievalConfig
    gen_config: GenerationConfig
    abstention_config: AbstentionConfig
    embedding_model: SentenceTransformer
    reranker: CrossEncoder
    qdrant_client: QdrantClient
    text_preprocessor: IndonesianTextPreprocessor
    retriever: HybridRetriever
    gemini_manager: RotatingKeyManager
    abstention_detector: AbstentionDetector
    kb_manager: KnowledgeBaseManager
    conversation_store: ConversationStore


def build_resources(base_dir: str = "./data") -> PipelineResources:
    """Titik masuk tunggal untuk inisialisasi seluruh resource berat.
    Di app/main.py, fungsi ini dipanggil SEKALI di dalam `lifespan`
    (event startup), disimpan di `app.state.resources` -- pengganti
    langsung dari @st.cache_resource di versi Streamlit. Karena
    disimpan di app.state (global untuk seluruh proses uvicorn, dibagi
    oleh semua request), objek `retriever` yang sama dipakai semua
    user -- itu sebabnya injeksi KB dari endpoint instruktur langsung
    terlihat oleh semua user tanpa perlu restart server."""
    torch.set_num_threads(os.cpu_count())  # taruh di awal build_resources()
    paths = AppPaths(base_dir=base_dir)
    retrieval_config = RetrievalConfig(kb_json_path=paths.kb_json, qdrant_db_path=paths.qdrant_db)
    gen_config = GenerationConfig()
    abstention_config = AbstentionConfig(exact_phrase=gen_config.not_available_answer)

    chunks = load_chunks(retrieval_config.kb_json_path)
    embedding_model = load_embedding_model(retrieval_config.embedding_model_name)
    reranker = load_reranker(retrieval_config.reranker_model_name)
    qdrant_client = initialize_qdrant_client(retrieval_config.qdrant_db_path)
    text_preprocessor = IndonesianTextPreprocessor()

    retriever = HybridRetriever(
        config=retrieval_config, embedding_model=embedding_model, qdrant_client=qdrant_client,
        reranker=reranker, chunks=chunks, text_preprocessor=text_preprocessor,
    )

    gemini_manager = RotatingKeyManager(load_api_keys(GEMINI_KEY_NAMES), lambda k: genai.Client(api_key=k))
    abstention_detector = AbstentionDetector(abstention_config, embedding_model)
    kb_manager = KnowledgeBaseManager(retriever, retrieval_config.kb_json_path, paths.kb_backup_dir)
    conversation_store = ConversationStore(paths.conversation_db)

    return PipelineResources(
        paths=paths, retrieval_config=retrieval_config, gen_config=gen_config,
        abstention_config=abstention_config, embedding_model=embedding_model, reranker=reranker,
        qdrant_client=qdrant_client, text_preprocessor=text_preprocessor, retriever=retriever,
        gemini_manager=gemini_manager, abstention_detector=abstention_detector,
        kb_manager=kb_manager, conversation_store=conversation_store,
    )


def authenticate(accounts: list[dict[str, str]], username: str, password: str) -> Optional[dict[str, str]]:
    """Cek username/password terhadap daftar akun. Return dict akun
    (berisi 'role') kalau cocok, None kalau tidak. Di versi FastAPI,
    `accounts` dibaca dari accounts.json (lihat app/core/config.py)
    -- pengganti langsung dari st.secrets['accounts']."""
    for account in accounts:
        if account.get("username") == username and account.get("password") == password:
            return {"username": username, "role": account.get("role", "user")}
    return None


def answer_question(resources: PipelineResources, question: str) -> dict[str, Any]:
    """Fungsi tunggal yang dipanggil endpoint /api/v1/chat/ask untuk 1
    pertanyaan user: retrieve -> generate -> deteksi abstain ->
    kembalikan semua info yang perlu ditampilkan (jawaban, konteks,
    sumber, status abstain)."""
    with _timed("retrieve_total"):
        retrieved_chunks = resources.retriever.retrieve(question)
    with _timed("generate_answer"):
        answer_text, context_block = generate_answer_with_rotation(
            question, retrieved_chunks, resources.gemini_manager, resources.gen_config
        )
    with _timed("abstention_detect"):
        is_abstained = resources.abstention_detector.detect(answer_text)
    sources = [extract_source_metadata(c) for c in retrieved_chunks]
    return {
        "answer": answer_text,
        "context": context_block,
        "retrieved_chunks": retrieved_chunks,
        "sources": sources,
        "is_abstained": is_abstained,
    }