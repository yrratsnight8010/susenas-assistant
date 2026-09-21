// Gabungkan nama class secara kondisional. Semua nama class Tailwind harus
// tertulis utuh di sumber (jangan disusun dari potongan string), supaya
// terdeteksi saat build.
export function cx(...parts) {
  return parts.filter(Boolean).join(" ");
}
