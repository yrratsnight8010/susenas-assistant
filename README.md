# Asisten Susenas Maret 2025 — FastAPI Edition

Migrasi dari aplikasi Streamlit lama ke arsitektur **backend FastAPI (REST API)
+ frontend statis terpisah**. Logika RAG (retrieval hybrid, generation Gemini,
abstention detector, injeksi koreksi/PDF) **tidak diubah** — hanya dipindahkan
ke lapisan service yang dipanggil lewat endpoint API, bukan lagi lewat widget
Streamlit.

```
susenas-fastapi/
├── README.md                     <- Anda di sini
├── .gitignore
│
├── backend/                      <- Server FastAPI
│   ├── requirements.txt
│   ├── .env.example              <- salin -> .env
│   ├── accounts.json.example     <- salin -> accounts.json
│   ├── data/                     <- letakkan kb_susenas_maret2025.json & qdrant_db/ di sini
│   │   └── README.md
│   └── app/
│       ├── main.py               <- entry point (uvicorn app.main:app)
│       ├── dependencies.py       <- dependency bersama (akses resource RAG)
│       ├── core/
│       │   ├── config.py         <- Settings + loader accounts.json
│       │   └── security.py       <- JWT auth (login, get_current_user, require_role)
│       ├── schemas/
│       │   ├── auth.py           <- Pydantic: LoginRequest, TokenResponse, ...
│       │   └── chat.py           <- Pydantic: AskRequest, AskResponse, ...
│       ├── api/v1/
│       │   ├── auth.py           <- POST /api/v1/auth/login, GET /me
│       │   ├── chat.py           <- POST /api/v1/chat/ask, GET /history (role: user)
│       │   └── instructor.py     <- GET/POST koreksi & upload PDF (role: instruktur)
│       └── services/
│           └── rag_pipeline.py   <- PORTING LANGSUNG dari rag_pipeline.py Streamlit
│
└── frontend/                     <- UI statis (HTML/CSS/JS murni, tanpa build step)
    ├── index.html
    ├── css/styles.css
    └── js/app.js
```

---

## 1. Prasyarat

- Python 3.10+
- Data yang **sudah Anda punya** dari proyek Streamlit: `kb_susenas_maret2025.json` dan folder `qdrant_db/`
- API key Gemini (dan Groq jika dipakai)

## 2. Setup backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

Salin & isi file konfigurasi:

```bash
cp .env.example .env                       # isi GEMINI_API_KEY dan JWT secret
cp accounts.json.example accounts.json     # isi username/password/role akun Anda
```

Letakkan data Anda:

```
backend/data/kb_susenas_maret2025.json
backend/data/qdrant_db/
```

(`conversations.db` dan `kb_backups/` akan dibuat otomatis saat server pertama kali jalan.)

## 3. Menjalankan server

Jalankan dari dalam folder `backend/` (penting — path data & accounts bersifat relatif terhadap folder ini, sama seperti kebiasaan `streamlit run app.py` sebelumnya):

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

Proses pertama akan lebih lama karena memuat model embedding & reranker (sama seperti loading spinner "menyiapkan sistem" di versi Streamlit) — cukup terjadi sekali, bukan setiap request.

Setelah server aktif:

- **Aplikasi (frontend + API dalam satu proses)**: http://localhost:8000
- **Dokumentasi API interaktif (Swagger UI)**: http://localhost:8000/docs
- **Health check**: http://localhost:8000/api/health

Frontend di `frontend/` **otomatis ikut disajikan** oleh FastAPI lewat static file mount di `app/main.py` — Anda tidak perlu menjalankan server terpisah untuk UI. Cukup satu perintah `uvicorn` di atas.

### Menjalankan frontend secara terpisah (opsional)

Kalau Anda ingin men-develop frontend dengan live-reload sendiri (mis. ekstensi "Live Server" VS Code di port 5500):

1. Di `frontend/js/app.js`, ubah baris paling atas:
   ```js
   const API_BASE = "http://localhost:8000";
   ```
2. Di `backend/.env`, isi `APP_CORS_ORIGINS=http://localhost:5500` (atau origin server statis Anda).
3. Jalankan backend seperti biasa (`uvicorn ...`), dan buka `frontend/index.html` lewat server statis pilihan Anda (`python -m http.server` juga bisa).

## 4. Akun & alur penggunaan

Struktur peran **identik** dengan versi Streamlit:

- **role `user`** → melihat halaman Tanya-Jawab (chat), riwayatnya tersimpan di server (bukan `st.session_state`) sehingga tidak hilang saat logout/refresh.
- **role `instruktur`** → melihat panel "Koreksi Jawaban" dan "Tambah Dokumen"; tidak melihat chat. Untuk tiap interaksi yang belum ditindak, instruktur punya 2 pilihan: **"✓ Tandai Sudah Benar"** (kalau jawaban chatbot sudah tepat apa adanya — tidak menulis apa pun, tidak menyuntikkan chunk baru ke KB, cuma menandai status) atau **isi form koreksi** (kalau jawaban perlu diganti — ini yang menyuntikkan chunk baru ke KB seperti dijelaskan di bawah).

Login lewat `/api/v1/auth/login` mengembalikan JWT (`access_token`). Frontend menyimpannya di `localStorage` dan mengirimkannya di header `Authorization: Bearer <token>` pada setiap request berikutnya — inilah pengganti `st.session_state.account`.

---

## 5. Highlight perubahan dibanding Streamlit

| Aspek | Streamlit (lama) | FastAPI (baru) |
|---|---|---|
| **Sesi login** | `st.session_state.account`, hidup selama tab browser terbuka & terikat proses server Streamlit | JWT stateless (`access_token`) tersimpan di `localStorage` browser; server tidak menyimpan sesi apa pun → lebih mudah di-scale ke banyak instance backend |
| **Resource berat (model, index)** | `@st.cache_resource` — dibangun sekali per proses Streamlit | `lifespan` FastAPI membangun `PipelineResources` sekali saat server start, disimpan di `app.state.resources`, dipakai bersama semua request (`app/main.py`) |
| **Validasi input** | Manual (`if not correction_text.strip(): st.warning(...)`) | **Pydantic** memvalidasi tipe & keharusan field secara otomatis di setiap endpoint (`schemas/auth.py`, `schemas/chat.py`) — request tidak valid ditolak sebelum menyentuh logika bisnis |
| **Pemisahan UI vs logika** | UI (`st.write`, `st.chat_message`, dst.) bercampur dengan pemanggilan pipeline langsung di `app.py` | Backend **hanya** mengembalikan JSON; semua tampilan (bubble chat, badge verifikasi, tab instruktur) ada di `frontend/` — bisa diganti ke React/Vue/mobile kapan pun tanpa menyentuh backend |
| **Dokumentasi API** | Tidak ada (harus baca kode) | Otomatis tersedia di **`/docs`** (Swagger UI) & **`/redoc`**, dihasilkan dari signature endpoint + schema Pydantic |
| **Konkurensi / performa** | Streamlit pada dasarnya single-flow per rerun, kurang cocok untuk banyak user bersamaan | FastAPI (ASGI) menangani request secara asynchronous; endpoint I/O-bound (mis. upload PDF) bisa `async def` |
| **Reaktivitas halaman** | Setiap interaksi (kirim pertanyaan, submit koreksi) memicu **`st.rerun()`** — seluruh halaman digambar ulang | Frontend hanya mem-fetch & merender ulang bagian yang relevan (daftar chat / daftar interaksi), tanpa reload halaman |
| **Struktur kode** | 2 file besar (`app.py` UI + `rag_pipeline.py` logika) | Struktur berlapis: `api/` (routing) → `schemas/` (kontrak data) → `services/` (logika RAG, nyaris tidak berubah) → `core/` (config & auth) |
| **Konfigurasi rahasia** | `.streamlit/secrets.toml` (API key + akun jadi satu) | Dipisah: `.env` untuk API key & JWT secret, `accounts.json` untuk daftar akun — lebih rapi untuk deployment (mis. secret manager) |
| **Sumber jawaban (citation)** | `st.expander` berisi daftar sumber & konteks mentah | Endpoint mengembalikan `sources` sebagai array terstruktur (Pydantic `SourceItem`); frontend menampilkannya sebagai catatan kaki `[1] [2] [3]` yang bisa dibuka/tutup |

**Yang TIDAK berubah** (sengaja dipertahankan apa adanya karena sudah benar secara desain):

- Seluruh isi `rag_pipeline.py` (hybrid retrieval RRF + reranker, prioritas sumber koreksi > dokumen > KB dasar, rotasi API key, abstention detector, `ConversationStore` berbasis SQLite) — dipindah ke `app/services/rag_pipeline.py` **tanpa perubahan logika**, karena file itu memang sudah tidak bergantung pada Streamlit sama sekali di versi lama Anda.
- Aturan prompt sistem Gemini (`build_system_prompt`) dan strategi chunking PDF (`inject_pdf`).

---

## 6. Catatan keamanan (untuk dikembangkan lebih lanjut)

- Password akun di `accounts.json` masih disimpan **plain text**, persis seperti `secrets.toml` sebelumnya. Untuk produksi, pertimbangkan hashing (mis. `passlib[bcrypt]`) sebelum dibandingkan di `authenticate()`.
- Ganti `APP_JWT_SECRET_KEY` di `.env` dengan string acak yang panjang sebelum deploy — jangan pernah commit file `.env` atau `accounts.json` ke repo publik (sudah dimasukkan ke `.gitignore`).
- `APP_CORS_ORIGINS=*` cocok untuk pengembangan lokal; batasi ke domain frontend Anda saat sudah live.
