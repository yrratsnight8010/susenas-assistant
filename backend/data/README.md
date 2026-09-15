# Folder `data/`

Folder ini harus berisi (sama persis seperti kebutuhan versi Streamlit):

1. `kb_susenas_maret2025.json` -- Knowledge Base hasil ingestion.
2. `qdrant_db/` -- folder index vektor Qdrant (mode lokal/embedded).

Salin dua item ini dari proyek Streamlit Anda yang sudah berjalan
(lihat README.md proyek riset Anda untuk cara mendapatkannya dari
Google Drive, kalau ada).

File `conversations.db` (riwayat percakapan) dan folder `kb_backups/`
akan **dibuat otomatis** oleh aplikasi saat pertama kali dijalankan --
tidak perlu dibuat manual.
