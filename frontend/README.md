# Susenas Assistant: Frontend (React + Vite + Tailwind CSS v4)

Frontend React dengan seluruh gaya ditulis memakai Tailwind CSS v4 (utility
class langsung di JSX). File `index.css` lama (1.794 baris) sudah dihapus dan
diganti `src/index.css` yang hanya berisi token desain, animasi, dan beberapa
aturan dasar. Backend FastAPI tidak berubah.

## Menjalankan

```bash
npm install
npm run dev
```

Build produksi:

```bash
npm run build
```

Hasilnya ada di `dist/`. Di Vercel, framework preset "Vite" akan mengenali
perintah build dan folder output (`dist`) secara otomatis.

## Konfigurasi backend

Ganti `API_BASE` di `src/api/client.js` ke URL backend (ngrok atau domain
lain). Bagian ini tidak diubah dari versi sebelumnya.

## Struktur gaya

Tailwind v4 tidak memakai `tailwind.config.js`. Semua konfigurasi ada di
`src/index.css`:

| Bagian | Isi |
| --- | --- |
| `@theme static` | Warna (`canvas`, `surface`, `support`, `ink`, `ink-soft`, `line`, `line-strong`, `accent`, `action`, `action-soft`, `success`, `danger`, dst.), font, radius, bayangan, animasi, dan breakpoint `shell` |
| `@custom-variant tall` | Desktop dengan tinggi layar lebih dari 800 px |
| `@utility scroll-quiet` | Scrollbar tipis |
| `@utility break-anywhere` | Pemutus baris untuk token panjang tanpa spasi |
| `@layer base` | `line-height` kontrol form, kursor tombol, outline fokus |

Contoh pemakaian token: `bg-action`, `text-ink-soft`, `border-line`,
`rounded-lg`, `shadow-md`, `font-mono`, `animate-msg-in`.

### Breakpoint

- Default = mobile (drawer sidebar + topbar hamburger).
- `shell:` = layar 901 px ke atas (sidebar tetap di kiri). Ini pengganti
  `@media (max-width: 900px)` di CSS lama.
- `tall:` = desktop dengan tinggi layar lebih dari 800 px (spasi lebih lega).
  Mobile dan laptop pendek memakai spasi yang lebih rapat.
- `max-[480px]:` = layar sangat sempit.

### Komponen UI bersama (`src/components/ui/`)

| File | Fungsi |
| --- | --- |
| `Button.jsx` | `variant`: `primary`, `action` (oranye), `ghost`, `ghostDanger`, `danger`. `size`: `md`, `sm`, `nav`, `icon`. Prop `block` untuk lebar penuh |
| `Field.jsx` | `Field` (label + input), plus `inputClass`, `fileInputClass`, `textareaClass` |
| `Notice.jsx` | `FormError`, `ResultNote`, `SpinnerNote` |
| `Tag.jsx` | Label status kecil di tabel |
| `DataTable.jsx` | `TableWrap`, `Th`, `Tr`, `Td`, `InlineActions` |

Kartu pesan chat ada di `src/components/MessageCards.jsx`.

## Aturan menulis class Tailwind

- Tulis nama class secara utuh. Jangan merakit dari potongan, misalnya
  `` `bg-${warna}-500` ``, karena tidak akan terdeteksi saat build. Pakai
  pemetaan objek seperti `VARIANTS` di `Button.jsx`.
- Jangan menaruh dua utility yang mengatur properti yang sama di satu elemen
  (misalnya `px-3 px-5`). Urutan penulisan tidak menentukan pemenangnya.
  Pisahkan lewat kondisi (`cond ? "a" : "b"`) atau lewat varian
  (`shell:px-5`).

## Perbedaan yang disengaja dari tampilan lama

1. **Tombol aksi utama kembali oranye**: Masuk, Percakapan Baru, Kirim, dan
   Proses & Injeksi. CSS lama sebenarnya mengatur warna ini lewat selektor
   `#login-submit`, `#new-room-btn`, dan sejenisnya, tetapi id itu tidak ada
   di komponen React, jadi tombolnya jatuh ke navy. Untuk mengembalikan navy,
   ubah `variant="action"` menjadi `variant="primary"`.
2. **Sidebar mode rail (diciutkan)**: logo "S" dan tombol buka ditumpuk
   vertikal. Sebelumnya keduanya sebaris dan lebarnya melebihi rail (68 px),
   sehingga terpotong.
3. **Drawer mobile**: pilihan "diciutkan" dari sesi desktop tidak lagi
   menyembunyikan isi drawer di layar sempit. Sebelumnya daftar percakapan
   dan label bisa hilang di mobile.
4. **Bayangan drawer** hanya muncul saat drawer terbuka.
5. Font Plus Jakarta Sans dihapus dari pemuatan font karena tidak dipakai
   (`--font-display` memang Inter). Font sekarang dimuat lewat `<link>` di
   `index.html`.

## Hal-hal yang perlu dicek/disesuaikan

- **Endpoint & kontrak API**: tidak diubah. Cek `src/api/client.js` dan
  `ChatView.jsx` kalau backend berubah.
- **CORS**: backend sudah mengaktifkan `CORSMiddleware`.
- **Tab instruktur tetap "mounted"** saat pindah tab (disembunyikan lewat
  class `hidden`), supaya state form tidak hilang.
- **`isFreshLogin`**: dipertahankan lewat `justLoggedIn` di `AuthContext`.
- **Browser**: Tailwind v4 membutuhkan browser modern (Safari 16.4+,
  Chrome 111+, Firefox 128+).
