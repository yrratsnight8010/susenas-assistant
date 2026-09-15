---
title: Asisten Susenas Maret 2025
emoji: 📊
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# Asisten Susenas Maret 2025 -- API + UI

Backend RAG (hybrid retrieval + reranker + Gemini) untuk chatbot tanya-jawab
data Susenas Maret 2025, di-deploy sebagai satu Docker image (API + frontend
statis dalam satu proses/port) di Hugging Face Spaces (CPU Basic, gratis).

## Catatan deploy

- **Isi environment variable lewat Settings -> Variables and secrets di Space
  ini** (JANGAN commit file `.env` ke repo). Minimal yang kemungkinan
  dibutuhkan berdasarkan `requirements.txt`: `GEMINI_API_KEY` (dan/atau
  `GROQ_API_KEY` kalau dipakai), `CORS_ORIGINS`, serta env var untuk
  `data_dir` kalau ada. Cek `app/core/config.py` untuk daftar pastinya.
- Space gratis (CPU Basic) bisa idle setelah tidak ada trafik dalam
  beberapa waktu -- buka link Space ini beberapa menit sebelum sesi
  usability testing / demo sidang supaya sudah "panas" (model sudah ke-load)
  saat orang lain mengakses.
- Disk di Space ini TIDAK persisten lintas rebuild/restart. Data index
  (Qdrant/BM25) sebaiknya di-generate ulang dari sumber data setiap startup
  (seperti alur lokal). Untuk data yang wajib tidak hilang (akun user, riwayat
  chat, koreksi instruktur), sebaiknya jangan hanya disimpan sebagai file
  lokal di container -- pertimbangkan DB eksternal gratis (mis. Neon atau
  Supabase Postgres) kalau saat ini masih pakai SQLite/JSON lokal.
