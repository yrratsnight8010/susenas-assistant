FROM python:3.12-slim

# build-essential kadang dibutuhkan buat compile dependency native (mis. tokenizers,
# rank-bm25, dsb.) kalau tidak ada wheel prebuilt untuk platform image ini.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements dulu (terpisah dari source code) supaya layer cache Docker
# kepake selama requirements.txt tidak berubah -- build ulang jadi jauh lebih cepat.
COPY backend/requirements.txt backend/requirements.txt

# Install torch CPU-only DULU dan eksplisit dari index resminya. Kalau tidak,
# `pip install -r requirements.txt` bisa menarik build torch dengan dependency
# CUDA yang besar & lama, padahal di sini cuma CPU yang tersedia.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r backend/requirements.txt

# --- SESUAIKAN JIKA PERLU ---
# Asumsi struktur repo: folder `backend/` dan `frontend/` sejajar di root repo
# (sesuai referensi FRONTEND_DIR di app/main.py). Kalau ada folder data KB
# (mis. qdrant_db, chunk hasil embedding) yang perlu ikut ke-bundle ke image
# supaya build_resources() tidak mulai dari nol tiap kali container jalan,
# tambahkan baris COPY untuk folder itu juga di sini.
COPY backend backend
COPY frontend frontend

# Hugging Face Spaces menjalankan container sebagai user non-root (UID 1000)
# dan HOME bawaan biasanya tidak writable. Beberapa library (sentence-transformers,
# huggingface_hub, torch) butuh folder cache yang bisa ditulis -- arahkan semua
# ke /app/.cache dan pastikan permission-nya terbuka.
ENV HOME=/app \
    HF_HOME=/app/.cache/huggingface \
    XDG_CACHE_HOME=/app/.cache

RUN mkdir -p /app/.cache && chmod -R 777 /app

# Hugging Face Spaces (Docker SDK) secara default mengekspektasikan app_port
# di README.md. Di sini dipakai port 7860 (default umum Spaces).
EXPOSE 7860

WORKDIR /app/backend
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
