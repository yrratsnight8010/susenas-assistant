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
import re
import shutil
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, PointIdsList
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer
from Sastrawi.Stemmer.StemmerFactory import StemmerFactory
from Sastrawi.StopWordRemover.StopWordRemoverFactory import StopWordRemoverFactory
from pypdf import PdfReader
import torch


from google import genai
from google.genai import types as genai_types

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

# Zona waktu WIB (UTC+7), dipakai untuk tanggal koreksi yang ditampilkan ke
# pengguna & dibaca LLM. Offset tetap dipakai (bukan zoneinfo) supaya tidak
# bergantung pada paket tzdata di mesin tempat backend berjalan (mis. Colab).
WIB = timezone(timedelta(hours=7))


def utc_now_iso() -> str:
    """Timestamp UTC dengan penanda zona (`...+00:00`) -- aman dibaca
    browser di zona waktu mana pun (`new Date(iso)`)."""
    return datetime.now(timezone.utc).isoformat()


def wib_today() -> str:
    """Tanggal hari ini menurut WIB (YYYY-MM-DD)."""
    return datetime.now(WIB).strftime("%Y-%m-%d")


# Nama lengkap sumber yang ditampilkan ke pengguna.
BUKU4_DISPLAY_NAME = "Buku 4 Pedoman Susenas Maret 2025"
PENEGASAN_DISPLAY_NAME = "Rangkuman Penegasan Permasalahan 2025"


def resolve_document_display_name(meta: dict[str, Any]) -> Optional[str]:
    """Kembalikan nama lengkap sumber untuk chunk KB AWAL (Buku 4 /
    Penegasan), atau None kalau chunk bukan dari keduanya. Dokumen
    unggahan instruktur dan koreksi sengaja TIDAK dipetakan, supaya nama
    yang diketik instruktur (mis. "Penegasan_Tambahan_2026") tampil apa
    adanya."""
    source = str(meta.get("source") or "")
    if source in ("uploaded_pdf", "human_correction"):
        return None
    for raw in (meta.get("document_id"), source):
        normalized = re.sub(r"[^a-z0-9]+", " ", str(raw or "").lower()).strip()
        if "penegasan" in normalized:
            return PENEGASAN_DISPLAY_NAME
        if re.search(r"\bbuku\s*4\b", normalized):
            return BUKU4_DISPLAY_NAME
    return None


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
    # Konfigurasi final hasil evaluasi: semantic 5 + BM25 5 -> RRF (k=60)
    # -> 5 kandidat teratas jadi konteks. Tanpa reranker.
    top_k_semantic: int = 5
    top_k_bm25: int = 5
    rrf_k: int = 60
    final_top_k: int = 5


@dataclass
class GenerationConfig:
    gemini_model: str = "gemini-3.6-flash"
    # None = pakai temperature bawaan model (sama dengan run evaluasi).
    # Isi angka (mis. 0.0) kalau ingin dipaksa deterministik.
    temperature: Optional[float] = None
    # Level thinking Gemini: minimal | low | medium | high (sama dengan evaluasi: low).
    thinking_level: str = "low"
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
                "Maaf, saya tidak menemukan informasi terkait pertanyaan ini di dalam database.",
                "Informasi tersebut tidak tersedia dalam sumber data yang diberikan.",
                "Maaf, informasi ini tidak terdapat dalam konteks yang diberikan.",
                "Data mengenai hal ini tidak tersedia dalam knowledge base saat ini.",
                "Pertanyaan ini tidak dapat dijawab berdasarkan konteks yang ada.",
                "Konteks yang diberikan tidak memuat jawaban atas pertanyaan tersebut.",
            ]


GEMINI_KEY_NAMES = [
    "GEMINI_API_KEY_TEMP06", "GEMINI_API_KEY_TEMP07", "GEMINI_API_KEY_NAB", "GEMINI_API_KEY", 
    "GEMINI_API_KEY_TEMP04","GEMINI_API_KEY_TEMP01", "GEMINI_API_KEY_TEMP02", 
    "GEMINI_API_KEY_ZEF", "GEMINI_API_KEY_GLO", "GEMINI_API_KEY_TEMP03",
]


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
    """Menggabungkan semantic search (Qdrant) + BM25 + RRF fusion.

    Konfigurasi final hasil evaluasi: semantic 5, BM25 5, RRF k=60, lalu
    5 kandidat teratas hasil RRF langsung menjadi konteks generation --
    TANPA reranker (reranker dibuang karena menambah latensi tanpa
    peningkatan metrik retrieval pada konfigurasi final)."""

    def __init__(
        self,
        config: RetrievalConfig,
        embedding_model: SentenceTransformer,
        qdrant_client: QdrantClient,
        chunks: list[dict[str, Any]],
        text_preprocessor: IndonesianTextPreprocessor,
    ):
        self.config = config
        self.embedding_model = embedding_model
        self.qdrant_client = qdrant_client
        self.chunks = chunks
        self.text_preprocessor = text_preprocessor
        # Cache hasil tokenisasi per chunk_id: stemming Sastrawi mahal, jadi
        # saat BM25 dibangun ulang (tiap injeksi/hapus chunk) hanya chunk
        # BARU yang perlu di-stem, bukan seluruh korpus.
        self._token_cache: dict[str, list[str]] = {}
        # (indeks BM25, salinan daftar chunk saat indeks dibangun) -- disimpan
        # sebagai SATU tuple supaya pencarian BM25 yang berjalan bersamaan
        # dengan injeksi/hapus chunk selalu melihat indeks dan daftar chunk
        # yang konsisten (indeks skor selalu cocok dengan chunk-nya).
        self._bm25_state: tuple[Optional[BM25Okapi], list[dict[str, Any]]] = (None, [])
        self.rebuild_bm25()

    @property
    def bm25_index(self) -> Optional[BM25Okapi]:
        return self._bm25_state[0]

    def _tokens_for(self, chunk: dict[str, Any]) -> list[str]:
        chunk_id = chunk["chunk_id"]
        tokens = self._token_cache.get(chunk_id)
        if tokens is None:
            tokens = self.text_preprocessor.tokenize(chunk["text"])
            self._token_cache[chunk_id] = tokens
        return tokens

    def rebuild_bm25(self) -> None:
        snapshot = list(self.chunks)
        if not snapshot:
            self._bm25_state = (None, [])
            self._token_cache.clear()
            logger.warning("BM25 index kosong: tidak ada chunk di Knowledge Base.")
            return
        corpus = [self._tokens_for(c) for c in snapshot]
        self._bm25_state = (BM25Okapi(corpus), snapshot)
        live_ids = {c["chunk_id"] for c in snapshot}
        for stale_id in [cid for cid in self._token_cache if cid not in live_ids]:
            del self._token_cache[stale_id]
        logger.info("BM25 index siap: %d dokumen.", len(snapshot))

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
        bm25_index, snapshot = self._bm25_state
        if bm25_index is None:
            return []
        scores = bm25_index.get_scores(self.text_preprocessor.tokenize(query))

        k = min(cfg.top_k_bm25, len(scores))
        if k == 0:
            return []
        top_indices = np.argpartition(scores, -k)[-k:]
        top_indices = top_indices[np.argsort(scores[top_indices])[::-1]]

        results = []
        for idx in top_indices:
            if scores[idx] <= 0:
                continue
            chunk = snapshot[idx]
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

    def retrieve(self, query: str) -> list[dict[str, Any]]:
        with _timed("semantic_search"):
            semantic_results = self.semantic_search(query)
        with _timed("bm25_search"):
            bm25_results = self.bm25_search(query)
        with _timed("rrf_fusion"):
            return self.rrf_fusion(
                semantic_results, bm25_results, self.config.rrf_k, self.config.final_top_k
            )


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


def initialize_qdrant_client(db_path: str) -> QdrantClient:
    return QdrantClient(path=db_path)


# =====================================================================
# KNOWLEDGE BASE MANAGER -- injeksi koreksi instruktur & dokumen PDF baru
# =====================================================================

class KnowledgeBaseManager:
    """Menyuntikkan / mencabut chunk (koreksi instruktur ATAU dokumen PDF
    unggahan) pada KB & index Qdrant/BM25 yang sedang berjalan, tanpa
    re-ingestion penuh -- dipanggil live dari endpoint instruktur.

    Semua operasi tulis diserialkan dengan satu lock, dan operasi massal
    (unggah PDF, hapus dokumen) bekerja secara BATCH: embedding sekaligus,
    satu kali tulis Qdrant, satu kali simpan JSON, satu kali rebuild BM25."""

    MAX_BACKUPS = 20
    UPSERT_BATCH = 64

    def __init__(self, retriever: HybridRetriever, kb_json_path: str, backup_dir: str):
        self.retriever = retriever
        self.kb_json_path = kb_json_path
        self.backup_dir = backup_dir
        self._lock = threading.RLock()

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
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        backup_path = os.path.join(self.backup_dir, f"kb_snapshot_{timestamp}.json")
        shutil.copy2(self.kb_json_path, backup_path)
        logger.info("Snapshot KB disimpan: %s", backup_path)
        # Batasi jumlah snapshot supaya folder tidak membengkak.
        snapshots = sorted(
            f for f in os.listdir(self.backup_dir) if f.startswith("kb_snapshot_") and f.endswith(".json")
        )
        for old in snapshots[: -self.MAX_BACKUPS]:
            try:
                os.remove(os.path.join(self.backup_dir, old))
            except OSError:
                logger.warning("Gagal menghapus snapshot lama: %s", old)

    def _save_kb_json_atomic(self) -> None:
        tmp_path = self.kb_json_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self.retriever.chunks, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.kb_json_path)

    def _upsert_chunks(self, chunks: list[dict[str, Any]], collection_name: str) -> None:
        """Tambahkan BANYAK chunk sekaligus ke Qdrant + KB in-memory + KB
        JSON, lalu rebuild BM25 SATU kali (wajib supaya BM25 tidak buta
        terhadap chunk baru). Kalau penyimpanan JSON/BM25 gagal setelah
        Qdrant terlanjur ditulis, perubahan dibatalkan supaya ketiga
        penyimpanan tidak saling berbeda."""
        if not chunks:
            return
        vectors = self.retriever.embedding_model.encode(
            [c["text"] for c in chunks], normalize_embeddings=True, batch_size=16
        )
        points = [
            PointStruct(id=self._point_id_for(c["chunk_id"]), vector=vec.tolist(), payload=c)
            for c, vec in zip(chunks, vectors)
        ]
        client = self.retriever.qdrant_client
        for i in range(0, len(points), self.UPSERT_BATCH):
            client.upsert(collection_name=collection_name, points=points[i : i + self.UPSERT_BATCH])

        previous_len = len(self.retriever.chunks)
        try:
            self.retriever.chunks.extend(chunks)
            self._save_kb_json_atomic()
            self.retriever.rebuild_bm25()
        except Exception:
            del self.retriever.chunks[previous_len:]
            client.delete(
                collection_name=collection_name,
                points_selector=PointIdsList(points=[p.id for p in points]),
            )
            raise

    def inject_correction(
        self, interaction_id: str, question: str, correction_text: str, corrected_by: str, collection_name: str,
    ) -> str:
        """Injeksi 1 koreksi instruktur sebagai chunk BARU (bukan mengedit
        chunk lama). Teks chunk = pertanyaan + koreksi (supaya konteksnya
        tidak hilang, mis. kalau correction_text cuma 'ya, lainnya').

        chunk_id = CORR_ + SHA-1(interaction_id + teks koreksi)[:10] --
        sama dengan rancangan pipeline evaluasi (qa_id diganti
        interaction_id). Deterministik, jadi klik ganda/retry tidak
        menghasilkan duplikat; dan karena interaction_id ikut di-hash,
        dua interaksi dengan pertanyaan & koreksi yang sama tidak berbagi
        satu chunk (menghapus koreksi yang satu tidak merusak yang lain)."""
        combined_text = f"Permasalahan: {question.strip()}\nSolusi: {correction_text.strip()}"
        chunk_id = self._deterministic_chunk_id("CORR", f"{interaction_id}\n{correction_text.strip()}")

        with self._lock:
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
                "created_at": utc_now_iso(),
                "corrected_by": corrected_by,
                "correction_date": wib_today(),
                "based_on_interaction_id": interaction_id,
            }
            self._upsert_chunks([chunk], collection_name)
            logger.info("INJECTED koreksi -> chunk_id=%s", chunk_id)
            return chunk_id

    def inject_pdf(
        self, document_id: str, pages: list[str], collection_name: str,
        document_year: Optional[int] = None, chunk_size: int = 800, overlap: int = 100,
    ) -> list[str]:
        """Injeksi dokumen PDF baru: tiap halaman dipecah jadi beberapa
        chunk (chunk_size karakter, overlap antar-chunk supaya konteks di
        batas potongan tidak hilang). `document_year` disimpan sebagai
        metadata (ikut ditampilkan di label sumber dan dipakai LLM untuk
        memilih informasi terbaru bila konteks bertentangan). Return list
        chunk_id yang berhasil ditambahkan (chunk kosong/duplikat
        dilewati). Seluruh chunk ditulis dalam SATU operasi batch."""
        with self._lock:
            existing_ids = {c["chunk_id"] for c in self.retriever.chunks}
            new_chunks: list[dict[str, Any]] = []
            created_at = utc_now_iso()

            for page_num, page_text in enumerate(pages, start=1):
                page_text = page_text.strip()
                if not page_text:
                    continue
                start = 0
                while start < len(page_text):
                    piece = page_text[start : start + chunk_size].strip()
                    if piece:
                        chunk_id = self._deterministic_chunk_id(
                            "PDF", f"{document_id}::{page_num}::{piece[:50]}::{start}"
                        )
                        if chunk_id not in existing_ids:
                            new_chunks.append({
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
                                "created_at": created_at,
                            })
                            existing_ids.add(chunk_id)
                    start += chunk_size - overlap

            if new_chunks:
                self._backup_kb_json()
                self._upsert_chunks(new_chunks, collection_name)

            logger.info("PDF '%s' (edisi %s) diinjeksi: %d chunk baru.", document_id, document_year, len(new_chunks))
            return [c["chunk_id"] for c in new_chunks]

    def delete_chunks(self, chunk_ids: list[str], collection_name: str) -> int:
        """Cabut BANYAK chunk sekaligus dari KB in-memory + KB JSON +
        Qdrant, lalu rebuild BM25 satu kali. Return jumlah chunk yang
        benar-benar dicabut (chunk_id yang sudah tidak ada dilewati)."""
        target = set(chunk_ids)
        with self._lock:
            removed_ids = [c["chunk_id"] for c in self.retriever.chunks if c["chunk_id"] in target]
            if not removed_ids:
                logger.info("SKIP hapus -- tidak ada chunk yang cocok di KB.")
                return 0

            self._backup_kb_json()
            self.retriever.chunks[:] = [c for c in self.retriever.chunks if c["chunk_id"] not in target]
            self._save_kb_json_atomic()
            self.retriever.rebuild_bm25()

            point_ids = [self._point_id_for(cid) for cid in removed_ids]
            for i in range(0, len(point_ids), self.UPSERT_BATCH):
                self.retriever.qdrant_client.delete(
                    collection_name=collection_name,
                    points_selector=PointIdsList(points=point_ids[i : i + self.UPSERT_BATCH]),
                )
            logger.info("DELETED %d chunk dari KB.", len(removed_ids))
            return len(removed_ids)

    def delete_chunk(self, chunk_id: str, collection_name: str) -> bool:
        """Cabut 1 chunk (dipakai saat koreksi dihapus/diedit). Return False
        kalau chunk_id sudah tidak ada di KB."""
        return self.delete_chunks([chunk_id], collection_name) > 0

    # -----------------------------------------------------------------
    # Pengelolaan dokumen untuk tab "Kelola KB"
    # -----------------------------------------------------------------

    @staticmethod
    def _kind_of(chunk: dict[str, Any]) -> str:
        source = chunk.get("source")
        if source == "human_correction":
            return "correction"
        if source == "uploaded_pdf":
            return "upload"
        return "base"

    def list_documents(self) -> list[dict[str, Any]]:
        """Ringkasan isi KB per dokumen. kind: 'base' (KB awal, terkunci),
        'upload' (PDF unggahan instruktur, boleh dihapus), 'correction'
        (seluruh chunk koreksi, dikelola dari tab Tinjau Percakapan)."""
        with self._lock:
            snapshot = list(self.retriever.chunks)

        groups: dict[tuple[str, str], dict[str, Any]] = {}
        for chunk in snapshot:
            kind = self._kind_of(chunk)
            raw_id = chunk.get("document_id") or chunk.get("source") or "-"
            key = (kind, "koreksi_instruktur" if kind == "correction" else str(raw_id))
            entry = groups.get(key)
            if entry is None:
                if kind == "correction":
                    display_name = "Koreksi instruktur"
                else:
                    display_name = (resolve_document_display_name(chunk) if kind == "base" else None) or str(raw_id)
                entry = groups[key] = {
                    "document_id": key[1],
                    "display_name": display_name,
                    "kind": kind,
                    "document_year": chunk.get("document_year"),
                    "chunk_count": 0,
                    "created_at": chunk.get("created_at"),
                    "deletable": kind == "upload",
                }
            entry["chunk_count"] += 1
            created = chunk.get("created_at")
            if created and (not entry["created_at"] or created < entry["created_at"]):
                entry["created_at"] = created

        order = {"base": 0, "upload": 1, "correction": 2}
        return sorted(groups.values(), key=lambda e: (order[e["kind"]], e["display_name"].lower()))

    def is_base_document_id(self, document_id: str) -> bool:
        wanted = document_id.strip().lower()
        with self._lock:
            return any(
                self._kind_of(c) == "base" and str(c.get("document_id") or "").strip().lower() == wanted
                for c in self.retriever.chunks
            )

    def delete_document(self, document_id: str, collection_name: str) -> int:
        """Hapus SEMUA chunk dari satu dokumen UNGGAHAN. KB awal dan chunk
        koreksi tidak pernah ikut terhapus lewat jalur ini. Return jumlah
        chunk yang dicabut (0 = dokumen unggahan tsb tidak ditemukan)."""
        with self._lock:
            ids = [
                c["chunk_id"] for c in self.retriever.chunks
                if self._kind_of(c) == "upload" and c.get("document_id") == document_id
            ]
            return self.delete_chunks(ids, collection_name) if ids else 0


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
    yang diajukan SEMUA user dari endpoint terpisah.

    Semua timestamp disimpan dalam UTC dengan penanda zona waktu
    (`+00:00`), supaya browser menampilkannya benar di zona waktu mana
    pun. Penghapusan room oleh petugas bersifat SOFT DELETE: room
    disembunyikan dari petugas, tetapi interaksi & koreksinya tetap ada
    sehingga instruktur masih bisa meninjau dan mengelolanya."""

    DEFAULT_ROOM_TITLE = "Percakapan Baru"

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
            # apa adanya, TANPA koreksi & TANPA injeksi chunk baru ke KB.
            self._ensure_column(conn, "interactions", "verified", "INTEGER DEFAULT 0")
            self._ensure_column(conn, "interactions", "verified_by", "TEXT")
            self._ensure_column(conn, "interactions", "verified_at", "TEXT")
            self._ensure_column(conn, "corrections", "correction_at", "TEXT")
            # soft delete room (diisi saat petugas menghapus percakapan).
            self._ensure_column(conn, "chat_rooms", "deleted_at", "TEXT")

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table: str, column: str, col_type: str) -> None:
        existing_cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing_cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")

    @staticmethod
    def derive_status(corrected: Any, verified: Any) -> str:
        """Status verifikasi tunggal untuk UI: corrected > verified > unverified."""
        if corrected:
            return "corrected"
        if verified:
            return "verified"
        return "unverified"

    # -----------------------------------------------------------------
    # ROOM PERCAKAPAN
    # -----------------------------------------------------------------

    def create_room(self, username: str, title: Optional[str] = None) -> dict[str, Any]:
        room_id = str(uuid.uuid4())
        now = utc_now_iso()
        final_title = title or self.DEFAULT_ROOM_TITLE
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO chat_rooms (id, username, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (room_id, username, final_title, now, now),
            )
        return {"id": room_id, "title": final_title, "created_at": now, "updated_at": now}

    def list_rooms(self, username: str) -> list[dict[str, Any]]:
        """Daftar room (yang belum dihapus) milik satu user, paling baru
        dipakai duluan. Baris `interactions` lama dengan `room_id` NULL
        dikumpulkan otomatis ke satu room "Percakapan Lama"."""
        with self._connect() as conn:
            orphan_count = conn.execute(
                "SELECT COUNT(*) FROM interactions WHERE username = ? AND room_id IS NULL",
                (username,),
            ).fetchone()[0]

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
                "SELECT id, title, created_at, updated_at FROM chat_rooms "
                "WHERE username = ? AND deleted_at IS NULL ORDER BY updated_at DESC",
                (username,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_or_create_active_room(self, username: str) -> dict[str, Any]:
        """Kembalikan SATU room kosong (belum ada pesan) milik user kalau
        ada, atau buat room baru. Mencegah "Percakapan Baru" kosong
        menumpuk tiap kali login ulang / menekan tombol Percakapan Baru."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            empty_rooms = conn.execute(
                """
                SELECT r.id, r.title, r.created_at, r.updated_at
                FROM chat_rooms r
                WHERE r.username = ?
                  AND r.deleted_at IS NULL
                  AND NOT EXISTS (SELECT 1 FROM interactions i WHERE i.room_id = r.id)
                ORDER BY r.updated_at DESC
                """,
                (username,),
            ).fetchall()

        if empty_rooms:
            keeper = dict(empty_rooms[0])
            if len(empty_rooms) > 1:
                stale_ids = [(row["id"],) for row in empty_rooms[1:]]
                with self._connect() as conn:
                    conn.executemany("DELETE FROM chat_rooms WHERE id = ?", stale_ids)
            return keeper

        return self.create_room(username)

    def get_room(self, room_id: str, username: str) -> Optional[dict[str, Any]]:
        """Ambil 1 room MILIK `username` yang belum dihapus -- dipakai
        sebagai pengecekan kepemilikan sebelum /ask, /history, atau
        delete_room memproses sebuah room_id."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT id, title, created_at, updated_at FROM chat_rooms "
                "WHERE id = ? AND username = ? AND deleted_at IS NULL",
                (room_id, username),
            ).fetchone()
        return dict(row) if row else None

    def delete_room(self, room_id: str, username: str) -> bool:
        """SOFT DELETE: room disembunyikan dari petugas, tetapi interaksi
        dan koreksinya TETAP tersimpan agar instruktur masih bisa
        meninjaunya dan mengelola koreksi yang sudah masuk ke Knowledge
        Base. False kalau room tidak ditemukan / bukan milik `username`."""
        if not self.get_room(room_id, username):
            return False
        with self._connect() as conn:
            conn.execute("UPDATE chat_rooms SET deleted_at = ? WHERE id = ?", (utc_now_iso(), room_id))
        return True

    def _touch_room(self, conn: sqlite3.Connection, room_id: str, first_question: Optional[str] = None) -> None:
        """Update updated_at room setiap ada pesan baru. Kalau room masih
        berjudul default, judulnya diganti otomatis dari pertanyaan
        pertama."""
        now = utc_now_iso()
        row = conn.execute("SELECT title FROM chat_rooms WHERE id = ?", (room_id,)).fetchone()
        current_title = row[0] if row else None
        if first_question and current_title == self.DEFAULT_ROOM_TITLE:
            short_title = first_question.strip().splitlines()[0][:60] or self.DEFAULT_ROOM_TITLE
            conn.execute("UPDATE chat_rooms SET title = ?, updated_at = ? WHERE id = ?", (short_title, now, room_id))
        else:
            conn.execute("UPDATE chat_rooms SET updated_at = ? WHERE id = ?", (now, room_id))

    # -----------------------------------------------------------------
    # INTERAKSI
    # -----------------------------------------------------------------

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
                (interaction_id, utc_now_iso(), username, question, answer, context, int(is_abstained), sources_json, room_id),
            )
            self._touch_room(conn, room_id, first_question=question)
        return interaction_id

    def get_interaction(self, interaction_id: str) -> Optional[dict[str, Any]]:
        """Ambil 1 interaksi (pertanyaan, jawaban, status) -- dipakai
        endpoint instruktur untuk validasi & mengambil pertanyaan ASLI
        dari database (bukan dari kiriman klien)."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT id, question, answer, corrected, verified FROM interactions WHERE id = ?",
                (interaction_id,),
            ).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["status"] = self.derive_status(item["corrected"], item["verified"])
        return item

    def list_interactions(self, status: str = "all") -> list[dict[str, Any]]:
        """Seluruh interaksi (semua user, termasuk room yang sudah
        dihapus petugas) untuk tab Tinjau Percakapan, sudah menyertakan
        data koreksinya bila ada. `status`: all | unverified | verified |
        corrected."""
        query = """
            SELECT i.id, i.timestamp, i.username, i.question, i.answer, i.is_abstained,
                   i.corrected, i.verified, i.verified_by, i.verified_at,
                   c.id AS correction_id, c.correction_text, c.corrected_by,
                   c.correction_date, c.correction_at
            FROM interactions i
            LEFT JOIN corrections c ON c.interaction_id = i.id
        """
        where = {
            "unverified": " WHERE COALESCE(i.corrected, 0) = 0 AND COALESCE(i.verified, 0) = 0",
            "verified": " WHERE COALESCE(i.corrected, 0) = 0 AND COALESCE(i.verified, 0) = 1",
            "corrected": " WHERE COALESCE(i.corrected, 0) = 1",
        }.get(status, "")
        query += where + " ORDER BY i.timestamp DESC"

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query).fetchall()

        results = []
        for row in rows:
            item = dict(row)
            item["is_abstained"] = bool(item["is_abstained"])
            item["status"] = self.derive_status(item["corrected"], item["verified"])
            item["corrected"] = bool(item["corrected"])
            item["verified"] = bool(item["verified"])
            results.append(item)
        return results

    def list_interactions_for_room(self, room_id: str, username: str) -> list[dict[str, Any]]:
        """Riwayat percakapan MILIK SATU ROOM (dan dipastikan milik
        `username`), urut kronologis (lama -> baru), sudah menyertakan
        correction_text & daftar sumber kalau ada."""
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
            item["is_abstained"] = bool(item["is_abstained"])
            item["status"] = self.derive_status(item["corrected"], item["verified"])
            item["corrected"] = bool(item["corrected"])
            item["verified"] = bool(item["verified"])
            try:
                item["sources"] = json.loads(item.pop("sources_json") or "[]")
            except (json.JSONDecodeError, TypeError):
                item["sources"] = []
            results.append(item)
        return results

    # -----------------------------------------------------------------
    # KOREKSI & VERIFIKASI
    # -----------------------------------------------------------------

    def mark_corrected(self, interaction_id: str, correction_text: str, corrected_by: str, chunk_id: str) -> None:
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                "UPDATE interactions SET corrected = 1, verified = 0, verified_by = NULL, verified_at = NULL WHERE id = ?",
                (interaction_id,),
            )
            conn.execute(
                "INSERT INTO corrections "
                "(id, interaction_id, correction_text, corrected_by, correction_date, chunk_id, correction_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), interaction_id, correction_text, corrected_by, wib_today(), chunk_id, now),
            )

    def get_correction(self, correction_id: str) -> Optional[dict[str, Any]]:
        """Ambil 1 baris koreksi lengkap (termasuk `original_question` &
        `chunk_id` LAMA) -- dipakai PATCH /instructor/corrections/{id}."""
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
        """Perbarui teks koreksi + `chunk_id` hasil re-injeksi, dan geser
        correction_date/correction_at ke SEKARANG supaya aturan 'ambil
        informasi paling baru' di system prompt menganggap hasil edit ini
        sebagai versi terbaru."""
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE corrections SET correction_text = ?, corrected_by = ?, "
                "correction_date = ?, correction_at = ?, chunk_id = ? WHERE id = ?",
                (correction_text, corrected_by, wib_today(), utc_now_iso(), chunk_id, correction_id),
            )
        return cur.rowcount > 0

    def delete_correction(self, correction_id: str) -> Optional[str]:
        """Hapus 1 baris `corrections` & reset interaksi terkait
        (corrected=0 -> kembali Unverified). Return chunk_id yang harus
        ikut dihapus dari KB/Qdrant, atau None kalau tidak ditemukan."""
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
        """Tandai jawaban chatbot SUDAH BENAR apa adanya (status Verified)
        -- tanpa correction_text & tanpa chunk baru di KB."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE interactions SET verified = 1, verified_by = ?, verified_at = ? WHERE id = ?",
                (verified_by, utc_now_iso(), interaction_id),
            )

    def mark_unverified(self, interaction_id: str) -> None:
        """Batalkan verifikasi: interaksi kembali Unverified."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE interactions SET verified = 0, verified_by = NULL, verified_at = NULL WHERE id = ?",
                (interaction_id,),
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
    user. Sumber KB awal ditampilkan dengan NAMA LENGKAP (Buku 4 Pedoman
    Susenas Maret 2025 / Rangkuman Penegasan Permasalahan 2025); dokumen
    unggahan instruktur memakai nama dan tahun edisi yang diketik
    instruktur; koreksi menampilkan nama instruktur dan tanggalnya.
    Menangani KEDUA bentuk chunk: hasil retrieve() (field di
    chunk['metadata']) maupun metadata ringkas dari ConversationStore."""
    meta = chunk.get("metadata") or chunk
    source = meta.get("source", "")

    if source == "human_correction":
        corrected_by = meta.get("corrected_by", "-")
        correction_date = meta.get("correction_date", "-")
        return f"🛠️ Koreksi instruktur ({corrected_by}, {correction_date})"

    page_start = meta.get("page_start")
    page_end = meta.get("page_end")

    display_name = resolve_document_display_name(meta)
    if display_name:
        label = f"📄 {display_name}"
    else:
        document_id = meta.get("document_id") or "Dokumen tidak diketahui"
        document_year = meta.get("document_year")
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


def _build_prompt(query: str, retrieved_chunks: list[dict[str, Any]]) -> tuple[str, str]:
    context_block = build_context_block(retrieved_chunks)
    prompt = f"KONTEKS:\n\n{context_block}\n\n\nPERTANYAAN:\n\n{query}\n\n\nJAWABAN:\n"
    return prompt, context_block


def _build_generate_config(gen_config: GenerationConfig) -> genai_types.GenerateContentConfig:
    level = getattr(genai_types.ThinkingLevel, gen_config.thinking_level.strip().upper())
    kwargs: dict[str, Any] = {
        "system_instruction": build_system_prompt(gen_config),
        "max_output_tokens": gen_config.max_output_tokens,
        "thinking_config": genai_types.ThinkingConfig(thinking_level=level),
    }
    if gen_config.temperature is not None:
        kwargs["temperature"] = gen_config.temperature
    return genai_types.GenerateContentConfig(**kwargs)


def generate_answer(
    query: str, retrieved_chunks: list[dict[str, Any]], client: Any, gen_config: GenerationConfig
) -> tuple[str, str]:
    prompt, context_block = _build_prompt(query, retrieved_chunks)
    response = client.models.generate_content(
        model=gen_config.gemini_model,
        contents=prompt,
        config=_build_generate_config(gen_config),
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
    prompt, _context_block = _build_prompt(query, retrieved_chunks)
    stream = client.models.generate_content_stream(
        model=gen_config.gemini_model,
        contents=prompt,
        config=_build_generate_config(gen_config),
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
    qdrant_client = initialize_qdrant_client(retrieval_config.qdrant_db_path)
    text_preprocessor = IndonesianTextPreprocessor()

    retriever = HybridRetriever(
        config=retrieval_config, embedding_model=embedding_model, qdrant_client=qdrant_client,
        chunks=chunks, text_preprocessor=text_preprocessor,
    )

    gemini_manager = RotatingKeyManager(load_api_keys(GEMINI_KEY_NAMES), lambda k: genai.Client(api_key=k))
    abstention_detector = AbstentionDetector(abstention_config, embedding_model)
    kb_manager = KnowledgeBaseManager(retriever, retrieval_config.kb_json_path, paths.kb_backup_dir)
    conversation_store = ConversationStore(paths.conversation_db)

    return PipelineResources(
        paths=paths, retrieval_config=retrieval_config, gen_config=gen_config,
        abstention_config=abstention_config, embedding_model=embedding_model,
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