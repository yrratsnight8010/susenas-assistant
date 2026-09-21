export function formatTimestamp(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return iso;
  }
}

export function formatRelativeTime(iso) {
  try {
    const then = new Date(iso).getTime();
    if (Number.isNaN(then)) return "";
    const diffSec = Math.floor((Date.now() - then) / 1000);
    if (diffSec < 45) return "Baru saja";
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin} menit lalu`;
    const diffHour = Math.floor(diffMin / 60);
    if (diffHour < 24) return `${diffHour} jam lalu`;
    const diffDay = Math.floor(diffHour / 24);
    if (diffDay === 1) return "Kemarin";
    if (diffDay < 7) return `${diffDay} hari lalu`;
    return new Date(iso).toLocaleDateString("id-ID", { day: "numeric", month: "short" });
  } catch {
    return "";
  }
}

export function timeOfDaySalutation() {
  const hour = new Date().getHours();
  if (hour >= 4 && hour < 11) return "Selamat pagi";
  if (hour >= 11 && hour < 15) return "Selamat siang";
  if (hour >= 15 && hour < 19) return "Selamat sore";
  return "Selamat malam";
}

const OPENING_LINES = [
  "Ada yang mau ditanyakan seputar Susenas Maret 2025?",
  "Mau tanya soal pengeluaran, kemiskinan, ketenagakerjaan, atau topik Susenas lain?",
  "Aku siap bantu telusuri data Susenas Maret 2025 -- tanyakan apa saja.",
  "Coba tanyakan definisi, metodologi, atau angka tertentu dari Susenas Maret 2025.",
  "Silakan mulai dengan pertanyaanmu -- jawabannya akan disertai sumber yang tertelusuri.",
];

export function randomOpeningLine() {
  return OPENING_LINES[Math.floor(Math.random() * OPENING_LINES.length)];
}
