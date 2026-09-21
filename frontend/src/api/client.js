// GANTI ini ke URL ngrok backend kamu kalau frontend di-host terpisah
// (misal di Vercel/Netlify) dari backend (Colab + ngrok). Kalau frontend
// masih di-serve satu origin sama backend (lewat StaticFiles di main.py),
// biarkan saja kosong "".
export const API_BASE = "https://gulf-extrude-cobalt.ngrok-free.dev";

// Header ini yang bikin warning page ngrok ("You are about to visit...")
// gak muncul untuk request API (fetch) dari JS -- ngrok skip
// interstitial-nya kalau lihat header ini di request. Tidak berpengaruh
// ke halaman HTML yang dibuka langsung di address bar browser (itu request
// native browser, gak lewat kode kita).
const NGROK_HEADERS = { "ngrok-skip-browser-warning": "true" };

// Token disimpan di module-level variable (bukan langsung baca localStorage
// tiap request) supaya AuthContext yang jadi satu-satunya sumber kebenaran
// untuk state auth di sisi React, dan module ini cuma "dikabari" lewat
// setApiToken() setiap kali token berubah (login/logout/restore sesi).
let currentToken = null;
let onUnauthorized = () => {};

export function setApiToken(token) {
  currentToken = token;
}

// Dipanggil sekali oleh AuthProvider supaya request yang kena 401 (sesi
// kadaluarsa/token invalid) otomatis memicu logout, sama seperti versi
// vanilla JS yang manggil logout() langsung di dalam apiFetch().
export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

export function getAuthHeaders(extra = {}) {
  const headers = { ...NGROK_HEADERS, ...extra };
  if (currentToken) headers["Authorization"] = `Bearer ${currentToken}`;
  return headers;
}

export async function apiFetch(path, options = {}) {
  const headers = options.headers ? { ...options.headers, ...NGROK_HEADERS } : { ...NGROK_HEADERS };
  if (currentToken) {
    headers["Authorization"] = `Bearer ${currentToken}`;
  }
  if (options.body && !(options.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (response.status === 401) {
    onUnauthorized();
    throw new Error("Sesi berakhir, silakan login ulang.");
  }
  if (response.status === 204) return null;

  let payload = null;
  const text = await response.text();
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }

  if (!response.ok) {
    const detail = payload && payload.detail ? payload.detail : `Permintaan gagal (${response.status}).`;
    throw new Error(detail);
  }

  return payload;
}
