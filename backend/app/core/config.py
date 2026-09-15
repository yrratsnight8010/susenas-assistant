"""
Konfigurasi aplikasi.

Di versi Streamlit, konfigurasi (API key & daftar akun) dibaca dari
`.streamlit/secrets.toml`. Di versi FastAPI ini kita pisah jadi dua:

1. API key (Gemini/Groq)  -> tetap lewat environment variable, sekarang
   diisi dari file `.env` (lihat .env.example) yang dimuat dengan
   python-dotenv di app/main.py sebelum resource RAG dibangun.
   `rag_pipeline.py` TIDAK berubah cara bacanya (os.environ.get(...)).

2. Konfigurasi aplikasi (JWT secret, path data, dsb.) & daftar akun
   login -> lewat Settings (pydantic-settings) + accounts.json, supaya
   gampang di-mount sebagai secret terpisah kalau nanti di-deploy.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Root folder `backend/` (folder yang berisi folder `app/` ini sendiri),
# dihitung dari LOKASI FILE ini -- BUKAN dari current working directory.
#
# BUG YANG DIPERBAIKI: sebelumnya default di bawah pakai path relatif
# ("./data", "./accounts.json"), yang di Python selalu relatif terhadap
# CWD proses Python saat dijalankan. Di Streamlit ini aman karena
# `streamlit run app.py` SELALU dijalankan dari folder yang berisi
# app.py. Tapi `uvicorn` bisa dijalankan dari CWD mana saja (root
# proyek, lewat tombol Run di editor, Docker WORKDIR, systemd service,
# dsb.) -- kalau CWD-nya bukan persis folder `backend/`, "./data" diam-
# diam mengarah ke folder lain yang mungkin tidak ada/kosong/basi.
# Yang paling berbahaya: KALAU folder itu somehow ada (walau isinya
# beda dari yang dipakai Streamlit), server TETAP start tanpa error --
# cuma jawaban chatbot jadi tidak ketemu, karena KB/index yang termuat
# sebenarnya bukan yang lengkap. Menjangkarkan ke lokasi file ini
# membuat path selalu benar terlepas dari CWD saat start.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    # -- Keamanan / JWT --
    jwt_secret_key: str = "GANTI_DENGAN_SECRET_ACAK_YANG_PANJANG"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 480  # 8 jam

    # -- Path data (setara AppPaths.base_dir di rag_pipeline.py) --
    # Absolut & dijangkarkan ke folder backend/ -- lihat catatan _BACKEND_ROOT.
    data_dir: str = str(_BACKEND_ROOT / "data")

    # -- Akun login (pengganti st.secrets["accounts"]) --
    accounts_file: str = str(_BACKEND_ROOT / "accounts.json")

    # -- CORS (kalau frontend dijalankan terpisah dari backend) --
    cors_origins: str = "*"

    model_config = SettingsConfigDict(env_file=".env", env_prefix="APP_", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


def load_accounts(path: str) -> list[dict]:
    """Baca daftar akun dari accounts.json. Formatnya persis meniru
    struktur [[accounts]] di secrets.toml versi Streamlit:

        [
          {"username": "budi", "password": "rahasia123", "role": "user"},
          {"username": "bu_dosen", "password": "rahasia456", "role": "instruktur"}
        ]
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(
            f"File akun tidak ditemukan: {path}. Salin accounts.json.example "
            "menjadi accounts.json lalu isi username/password/role."
        )
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)
