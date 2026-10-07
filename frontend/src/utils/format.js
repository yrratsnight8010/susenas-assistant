// Timestamp dari server berformat ISO UTC (`...+00:00`). Baris lama yang
// tersimpan tanpa penanda zona juga berasal dari server UTC, jadi dianggap
// UTC (ditambah "Z") -- bukan waktu lokal browser.
export function parseServerDate(value) {
  if (!value) return null;
  const text = String(value);
  const isDateOnly = /^\d{4}-\d{2}-\d{2}$/.test(text);
  const hasZone = /([zZ]|[+-]\d{2}:?\d{2})$/.test(text);
  const date = new Date(isDateOnly || hasZone ? text : `${text}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatTimestamp(value) {
  const date = parseServerDate(value);
  if (!date) return value ? String(value) : "-";
  if (/^\d{4}-\d{2}-\d{2}$/.test(String(value))) {
    return date.toLocaleDateString("id-ID", { dateStyle: "medium", timeZone: "UTC" });
  }
  return date.toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" });
}

export function formatRelativeTime(value) {
  const date = parseServerDate(value);
  if (!date) return "";
  const diffSec = Math.floor((Date.now() - date.getTime()) / 1000);
  if (diffSec < 45) return "Baru saja";
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin} menit lalu`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour} jam lalu`;
  const diffDay = Math.floor(diffHour / 24);
  if (diffDay === 1) return "Kemarin";
  if (diffDay < 7) return `${diffDay} hari lalu`;
  return date.toLocaleDateString("id-ID", { day: "numeric", month: "short" });
}

export function timeOfDaySalutation() {
  const hour = new Date().getHours();
  if (hour >= 4 && hour < 11) return "Selamat pagi";
  if (hour >= 11 && hour < 15) return "Selamat siang";
  if (hour >= 15 && hour < 19) return "Selamat sore";
  return "Selamat malam";
}

const OPENING_LINES = [
  "Ada yang mau ditanyakan seputar Susenas Maret?",
  "Aku siap bantu telusuri tentang Susenas Maret -- tanyakan apa saja.",
  "Coba tanyakan definisi atau topik tertentu dari Susenas Maret.",
  "Silakan mulai dengan pertanyaanmu -- jawabannya akan disertai sumber yang tertelusuri.",
];

export function randomOpeningLine() {
  return OPENING_LINES[Math.floor(Math.random() * OPENING_LINES.length)];
}
