# Asisten Susenas Maret 2025 — FastAPI Edition

Migrasi dari aplikasi Streamlit lama ke arsitektur \*\*backend FastAPI (REST API)

- frontend statis terpisah**. Logika RAG (retrieval hybrid, generation Gemini,
  abstention detector, injeksi koreksi/PDF) **tidak diubah\*\* — hanya dipindahkan
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
└── frontend/                     <- UI React + Vite + Tailwind CSS v4 (BUTUH build step)
    ├── index.html                <- me-load /src/main.jsx, TIDAK bisa dibuka langsung tanpa build
    ├── package.json              <- npm run dev / npm run build / npm run preview
    ├── vite.config.js
    └── src/
        ├── main.jsx, App.jsx
        ├── api/client.js         <- API_BASE, wrapper apiFetch()
        ├── context/              <- AuthContext, ChatRoomsContext, ToastContext, ConfirmContext
        ├── components/           <- ChatView, InstructorView, RoomSidebar, dst.
        └── utils/
```

> Frontend versi lama (HTML/CSS/JS murni tanpa build step) sudah digantikan
> penuh oleh React+Vite di atas — lihat `frontend/README.md` untuk detail
> struktur & konvensi gaya (Tailwind v4). Konsekuensinya: frontend **wajib**
> di-build (`npm run build`) sebelum bisa disajikan sebagai file statis
> biasa oleh FastAPI atau hosting statis mana pun.

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

## 3. Build frontend (WAJIB sebelum menjalankan server satu-proses)

Frontend sekarang React + Vite (lihat `frontend/README.md`), bukan lagi HTML/JS
statis yang bisa langsung dibuka browser — `index.html` me-load `/src/main.jsx`
lewat `<script type="module">`, yang butuh proses build supaya JSX & import
`react`/`react-dom` diterjemahkan jadi JS biasa. Build dulu:

```bash
cd frontend
npm install
npm run build        # hasilnya di frontend/dist/
```

`app/main.py` mem-mount `frontend/dist/` (bukan folder `frontend/` mentah) sebagai
file statis — kalau `dist/` belum ada, server tetap start tapi cuma API yang aktif
(ada warning di log, dan membuka `http://localhost:8000/` akan 404).

## 4. Menjalankan server

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

Frontend hasil build (`frontend/dist/`) **otomatis ikut disajikan** oleh FastAPI lewat static file mount di `app/main.py` — Anda tidak perlu menjalankan server terpisah untuk UI, asalkan sudah menjalankan `npm run build` di langkah 3. Kalau frontend diedit lagi, ulangi `npm run build` supaya `dist/` ikut ter-update.

### Menjalankan frontend secara terpisah (mode development, live-reload)

Kalau Anda sedang mengembangkan tampilan dan ingin live-reload (tanpa build ulang tiap perubahan):

1. Di `frontend/src/api/client.js`, ubah `API_BASE` ke URL backend Anda:
   ```js
   export const API_BASE = "http://localhost:8000";
   ```
2. Di `backend/.env`, isi `APP_CORS_ORIGINS=http://localhost:5173` (port default Vite dev server; lihat `frontend/vite.config.js`).
3. Jalankan backend seperti biasa (`uvicorn ...`), lalu di folder `frontend/`:
   ```bash
   npm install
   npm run dev
   ```
   Vite akan menyajikan UI di `http://localhost:5173` dengan hot-reload, memanggil API ke `API_BASE` di atas.

## 5. Akun & alur penggunaan

Struktur peran **identik** dengan versi Streamlit:

- **role `user`** → melihat halaman Tanya-Jawab (chat), riwayatnya tersimpan di server (bukan `st.session_state`) sehingga tidak hilang saat logout/refresh.
- **role `instruktur`** → melihat panel "Koreksi Jawaban" dan "Tambah Dokumen"; tidak melihat chat. Untuk tiap interaksi yang belum ditindak, instruktur punya 2 pilihan: **"✓ Tandai Sudah Benar"** (kalau jawaban chatbot sudah tepat apa adanya — tidak menulis apa pun, tidak menyuntikkan chunk baru ke KB, cuma menandai status) atau **isi form koreksi** (kalau jawaban perlu diganti — ini yang menyuntikkan chunk baru ke KB seperti dijelaskan di bawah).

Login lewat `/api/v1/auth/login` mengembalikan JWT (`access_token`). Frontend menyimpannya di `localStorage` dan mengirimkannya di header `Authorization: Bearer <token>` pada setiap request berikutnya — inilah pengganti `st.session_state.account`.

---

## 6. Highlight perubahan dibanding Streamlit

| Aspek                             | Streamlit (lama)                                                                                             | FastAPI (baru)                                                                                                                                                                               |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Sesi login**                    | `st.session_state.account`, hidup selama tab browser terbuka & terikat proses server Streamlit               | JWT stateless (`access_token`) tersimpan di `localStorage` browser; server tidak menyimpan sesi apa pun → lebih mudah di-scale ke banyak instance backend                                    |
| **Resource berat (model, index)** | `@st.cache_resource` — dibangun sekali per proses Streamlit                                                  | `lifespan` FastAPI membangun `PipelineResources` sekali saat server start, disimpan di `app.state.resources`, dipakai bersama semua request (`app/main.py`)                                  |
| **Validasi input**                | Manual (`if not correction_text.strip(): st.warning(...)`)                                                   | **Pydantic** memvalidasi tipe & keharusan field secara otomatis di setiap endpoint (`schemas/auth.py`, `schemas/chat.py`) — request tidak valid ditolak sebelum menyentuh logika bisnis      |
| **Pemisahan UI vs logika**        | UI (`st.write`, `st.chat_message`, dst.) bercampur dengan pemanggilan pipeline langsung di `app.py`          | Backend **hanya** mengembalikan JSON; semua tampilan (bubble chat, badge verifikasi, tab instruktur) ada di `frontend/` — bisa diganti ke React/Vue/mobile kapan pun tanpa menyentuh backend |
| **Dokumentasi API**               | Tidak ada (harus baca kode)                                                                                  | Otomatis tersedia di **`/docs`** (Swagger UI) & **`/redoc`**, dihasilkan dari signature endpoint + schema Pydantic                                                                           |
| **Konkurensi / performa**         | Streamlit pada dasarnya single-flow per rerun, kurang cocok untuk banyak user bersamaan                      | FastAPI (ASGI) menangani request secara asynchronous; endpoint I/O-bound (mis. upload PDF) bisa `async def`                                                                                  |
| **Reaktivitas halaman**           | Setiap interaksi (kirim pertanyaan, submit koreksi) memicu **`st.rerun()`** — seluruh halaman digambar ulang | Frontend hanya mem-fetch & merender ulang bagian yang relevan (daftar chat / daftar interaksi), tanpa reload halaman                                                                         |
| **Struktur kode**                 | 2 file besar (`app.py` UI + `rag_pipeline.py` logika)                                                        | Struktur berlapis: `api/` (routing) → `schemas/` (kontrak data) → `services/` (logika RAG, nyaris tidak berubah) → `core/` (config & auth)                                                   |
| **Konfigurasi rahasia**           | `.streamlit/secrets.toml` (API key + akun jadi satu)                                                         | Dipisah: `.env` untuk API key & JWT secret, `accounts.json` untuk daftar akun — lebih rapi untuk deployment (mis. secret manager)                                                            |
| **Sumber jawaban (citation)**     | `st.expander` berisi daftar sumber & konteks mentah                                                          | Endpoint mengembalikan `sources` sebagai array terstruktur (Pydantic `SourceItem`); frontend menampilkannya sebagai catatan kaki `[1] [2] [3]` yang bisa dibuka/tutup                        |

**Yang TIDAK berubah** (sengaja dipertahankan apa adanya karena sudah benar secara desain):

- Seluruh isi `rag_pipeline.py` (hybrid retrieval RRF + reranker, prioritas sumber koreksi > dokumen > KB dasar, rotasi API key, abstention detector, `ConversationStore` berbasis SQLite) — dipindah ke `app/services/rag_pipeline.py` **tanpa perubahan logika**, karena file itu memang sudah tidak bergantung pada Streamlit sama sekali di versi lama Anda.
- Aturan prompt sistem Gemini (`build_system_prompt`) dan strategi chunking PDF (`inject_pdf`).

---

## 7. Catatan keamanan (untuk dikembangkan lebih lanjut)

- Password akun di `accounts.json` masih disimpan **plain text**, persis seperti `secrets.toml` sebelumnya. Untuk produksi, pertimbangkan hashing (mis. `passlib[bcrypt]`) sebelum dibandingkan di `authenticate()`.
- Ganti `APP_JWT_SECRET_KEY` di `.env` dengan string acak yang panjang sebelum deploy — jangan pernah commit file `.env` atau `accounts.json` ke repo publik (sudah dimasukkan ke `.gitignore`).
- `APP_CORS_ORIGINS=*` cocok untuk pengembangan lokal; batasi ke domain frontend Anda saat sudah live. Autentikasi di sini pakai JWT lewat header `Authorization: Bearer <token>` (bukan cookie), jadi `CORSMiddleware` diset `allow_credentials=False` — kombinasi origin wildcard (`*`) dengan `allow_credentials=True` sebenarnya melanggar spesifikasi CORS browser dan tidak diperlukan di sini.
