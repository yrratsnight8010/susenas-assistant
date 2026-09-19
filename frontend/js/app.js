"use strict";

// GANTI ini ke URL ngrok backend kamu kalau frontend di-host terpisah
// (misal di Vercel/Netlify) dari backend (Colab + ngrok). Kalau frontend
// masih di-serve satu origin sama backend (lewat StaticFiles di main.py),
// biarkan saja kosong "".
const API_BASE = "https://gulf-extrude-cobalt.ngrok-free.dev";

// Header ini yang bikin warning page ngrok ("You are about to visit...")
// gak muncul untuk request API (fetch/axios) dari JS -- ngrok skip
// interstitial-nya kalau lihat header ini di request. Tidak berpengaruh
// ke halaman HTML yang dibuka langsung di address bar browser (itu request
// native browser, gak lewat kode kita).
const NGROK_HEADERS = { "ngrok-skip-browser-warning": "true" };

const STORAGE_KEYS = {
  token: "susenas_token",
  username: "susenas_username",
  role: "susenas_role",
  currentRoom: "susenas_current_room",
};

const state = {
  token: localStorage.getItem(STORAGE_KEYS.token) || null,
  username: localStorage.getItem(STORAGE_KEYS.username) || null,
  role: localStorage.getItem(STORAGE_KEYS.role) || null,
  rooms: [],
  currentRoomId: null,
};

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text ?? "";
  return div.innerHTML;
}

function formatTimestamp(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return iso;
  }
}

function formatRelativeTime(iso) {
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

async function apiFetch(path, options = {}) {
  const headers = options.headers ? { ...options.headers, ...NGROK_HEADERS } : { ...NGROK_HEADERS };
  if (state.token) {
    headers["Authorization"] = `Bearer ${state.token}`;
  }
  if (options.body && !(options.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (response.status === 401) {
    logout();
    throw new Error("Sesi berakhir, silakan login ulang.");
  }
  if (response.status === 204) return null;
  let payload = null;
  const text = await response.text();
  if (text) {
    try { payload = JSON.parse(text); } catch { payload = null; }
  }
  if (!response.ok) {
    const detail = payload && payload.detail ? payload.detail : `Permintaan gagal (${response.status}).`;
    throw new Error(detail);
  }
  return payload;
}

function setToken(token, username, role) {
  state.token = token;
  state.username = username;
  state.role = role;
  localStorage.setItem(STORAGE_KEYS.token, token);
  localStorage.setItem(STORAGE_KEYS.username, username);
  localStorage.setItem(STORAGE_KEYS.role, role);
}

function logout() {
  state.token = null;
  state.username = null;
  state.role = null;
  state.rooms = [];
  state.currentRoomId = null;
  localStorage.removeItem(STORAGE_KEYS.token);
  localStorage.removeItem(STORAGE_KEYS.username);
  localStorage.removeItem(STORAGE_KEYS.role);
  localStorage.removeItem(STORAGE_KEYS.currentRoom);
  showLoginScreen();
}

const el = {
  loginScreen: document.getElementById("login-screen"),
  appShell: document.getElementById("app-shell"),
  loginForm: document.getElementById("login-form"),
  loginError: document.getElementById("login-error"),
  loginSubmit: document.getElementById("login-submit"),
  accountUsername: document.getElementById("account-username"),
  accountRole: document.getElementById("account-role"),
  logoutBtn: document.getElementById("logout-btn"),
  chatView: document.getElementById("chat-view"),
  instructorView: document.getElementById("instructor-view"),
  chatLog: document.getElementById("chat-log"),
  chatForm: document.getElementById("chat-form"),
  chatInput: document.getElementById("chat-input"),
  chatSendBtn: document.getElementById("chat-send-btn"),
  chatRoomTitle: document.getElementById("chat-room-title"),
  onlyUncorrected: document.getElementById("only-uncorrected"),
  interactionsList: document.getElementById("interactions-list"),
  uploadForm: document.getElementById("upload-form"),
  uploadResult: document.getElementById("upload-result"),
  uploadSubmit: document.getElementById("upload-submit"),
  roomSidebarSection: document.getElementById("room-sidebar-section"),
  roomList: document.getElementById("room-list"),
  newRoomBtn: document.getElementById("new-room-btn"),
  confirmModal: document.getElementById("confirm-modal"),
  confirmTitle: document.getElementById("confirm-modal-title"),
  confirmBody: document.getElementById("confirm-modal-body"),
  confirmCancelBtn: document.getElementById("confirm-modal-cancel"),
  confirmConfirmBtn: document.getElementById("confirm-modal-confirm"),
  toastContainer: document.getElementById("toast-container"),
};

function showLoginScreen() {
  el.appShell.classList.add("hidden");
  el.loginScreen.classList.remove("hidden");
  el.loginError.classList.add("hidden");
  el.loginForm.reset();
}

function showAppShell({ isFreshLogin = false } = {}) {
  el.loginScreen.classList.add("hidden");
  el.appShell.classList.remove("hidden");
  el.accountUsername.textContent = state.username;
  el.accountRole.textContent = state.role;
  el.accountRole.classList.toggle("sidebar__account-role--instruktur", state.role === "instruktur");
  if (state.role === "instruktur") {
    el.chatView.classList.add("hidden");
    el.instructorView.classList.remove("hidden");
    el.roomSidebarSection.classList.add("hidden");
    loadInteractions();
  } else {
    el.instructorView.classList.add("hidden");
    el.chatView.classList.remove("hidden");
    el.roomSidebarSection.classList.remove("hidden");
    initChatRooms(isFreshLogin);
  }
}

function showToast(message, type = "success", duration = 3800) {
  const toast = document.createElement("div");
  toast.className = `toast toast--${type}`;
  toast.textContent = message;
  el.toastContainer.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add("toast--visible"));
  setTimeout(() => {
    toast.classList.remove("toast--visible");
    setTimeout(() => toast.remove(), 220);
  }, duration);
}

function confirmDialog({
  title = "Konfirmasi",
  body = "Apakah Anda yakin?",
  confirmLabel = "Ya",
  cancelLabel = "Batal",
  danger = false,
}) {
  return new Promise((resolve) => {
    el.confirmTitle.textContent = title;
    el.confirmBody.textContent = body;
    el.confirmConfirmBtn.textContent = confirmLabel;
    el.confirmCancelBtn.textContent = cancelLabel;
    el.confirmConfirmBtn.classList.toggle("btn--danger", danger);
    el.confirmModal.classList.remove("hidden");

    function cleanup(result) {
      el.confirmModal.classList.add("hidden");
      el.confirmConfirmBtn.removeEventListener("click", onConfirm);
      el.confirmCancelBtn.removeEventListener("click", onCancel);
      el.confirmModal.removeEventListener("mousedown", onOverlay);
      document.removeEventListener("keydown", onKey);
      resolve(result);
    }

    function onConfirm() { cleanup(true); }
    function onCancel() { cleanup(false); }
    function onOverlay(event) { if (event.target === el.confirmModal) cleanup(false); }
    function onKey(event) { if (event.key === "Escape") cleanup(false); }

    el.confirmConfirmBtn.addEventListener("click", onConfirm);
    el.confirmCancelBtn.addEventListener("click", onCancel);
    el.confirmModal.addEventListener("mousedown", onOverlay);
    document.addEventListener("keydown", onKey);
    el.confirmConfirmBtn.focus();
  });
}

el.loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  el.loginError.classList.add("hidden");
  el.loginSubmit.disabled = true;
  el.loginSubmit.textContent = "Memproses...";
  const username = document.getElementById("login-username").value.trim();
  const password = document.getElementById("login-password").value;

  try {
    const result = await apiFetch("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    setToken(result.access_token, result.username, result.role);
    showAppShell({ isFreshLogin: true });
  } catch (err) {
    el.loginError.textContent = err.message || "Username atau password salah.";
    el.loginError.classList.remove("hidden");
  } finally {
    el.loginSubmit.disabled = false;
    el.loginSubmit.textContent = "Masuk";
  }
});

el.logoutBtn.addEventListener("click", () => logout());

function setActiveRoomId(roomId) {
  state.currentRoomId = roomId;
  if (roomId) {
    localStorage.setItem(STORAGE_KEYS.currentRoom, roomId);
  } else {
    localStorage.removeItem(STORAGE_KEYS.currentRoom);
  }
}

async function initChatRooms(isFreshLogin) {
  el.roomList.innerHTML = `<p class="room-list-empty">Memuat percakapan...</p>`;
  try {
    let rooms = await apiFetch("/api/v1/chat/rooms");
    if (isFreshLogin || rooms.length === 0) {
      const activeRoom = await apiFetch("/api/v1/chat/rooms", {
        method: "POST",
        body: JSON.stringify({}),
      });
      rooms = await apiFetch("/api/v1/chat/rooms");
      setActiveRoomId(activeRoom.id);
    } else {
      const savedId = localStorage.getItem(STORAGE_KEYS.currentRoom);
      const stillExists = rooms.some((r) => r.id === savedId);
      setActiveRoomId(stillExists ? savedId : rooms[0].id);
    }
    renderRoomList(rooms);
    await loadChatHistory();
  } catch (err) {
    el.roomList.innerHTML = `<p class="room-list-empty">${escapeHtml(err.message)}</p>`;
    showToast(err.message || "Gagal memuat daftar percakapan.", "error");
  }
}

function renderRoomList(rooms) {
  state.rooms = rooms;
  el.roomList.innerHTML = "";
  if (rooms.length === 0) {
    el.roomList.innerHTML = `<p class="room-list-empty">Belum ada percakapan.</p>`;
    return;
  }
  rooms.forEach((room) => {
    el.roomList.appendChild(renderRoomItem(room));
  });
  updateChatRoomTitle();
}

function renderRoomItem(room) {
  const item = document.createElement("div");
  item.className = "room-item" + (room.id === state.currentRoomId ? " room-item--active" : "");

  const selectBtn = document.createElement("button");
  selectBtn.type = "button";
  selectBtn.className = "room-item__select";
  selectBtn.innerHTML = `
    <span class="room-item__title">${escapeHtml(room.title)}</span>
    <span class="room-item__time">${escapeHtml(formatRelativeTime(room.updated_at))}</span>
  `;
  selectBtn.addEventListener("click", () => switchRoom(room.id));

  const deleteBtn = document.createElement("button");
  deleteBtn.type = "button";
  deleteBtn.className = "room-item__delete";
  deleteBtn.title = "Hapus percakapan";
  deleteBtn.setAttribute("aria-label", `Hapus percakapan "${room.title}"`);
  deleteBtn.innerHTML = `
    <svg viewBox="0 0 16 16" width="15" height="15" fill="none" aria-hidden="true">
      <path d="M3 4.5h10M6.5 4.5V3a1 1 0 0 1 1-1h1a1 1 0 0 1 1 1v1.5M4.5 4.5 5 13a1 1 0 0 0 1 1h4a1 1 0 0 0 1-1l.5-8.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
  `;
  deleteBtn.addEventListener("click", async (event) => {
    event.stopPropagation();
    const confirmed = await confirmDialog({
      title: "Hapus percakapan ini?",
      body: `"${room.title}" akan dihapus permanen beserta seluruh riwayat tanya-jawab di dalamnya. Tindakan ini tidak bisa dibatalkan.`,
      confirmLabel: "Hapus",
      danger: true,
    });
    if (confirmed) await deleteRoom(room.id);
  });

  item.appendChild(selectBtn);
  item.appendChild(deleteBtn);
  return item;
}

function updateChatRoomTitle() {
  const room = state.rooms.find((r) => r.id === state.currentRoomId);
  el.chatRoomTitle.textContent = room ? room.title : "Tanya Jawab";
}

async function switchRoom(roomId) {
  if (roomId === state.currentRoomId) return;
  setActiveRoomId(roomId);
  renderRoomList(state.rooms);
  await loadChatHistory();
}

el.newRoomBtn.addEventListener("click", async () => {
  el.newRoomBtn.disabled = true;
  try {
    const activeRoom = await apiFetch("/api/v1/chat/rooms", {
      method: "POST",
      body: JSON.stringify({}),
    });
    state.rooms = await apiFetch("/api/v1/chat/rooms");
    setActiveRoomId(activeRoom.id);
    renderRoomList(state.rooms);
    await loadChatHistory();
  } catch (err) {
    showToast(err.message || "Gagal membuka percakapan baru.", "error");
  } finally {
    el.newRoomBtn.disabled = false;
  }
});

async function deleteRoom(roomId) {
  try {
    await apiFetch(`/api/v1/chat/rooms/${encodeURIComponent(roomId)}`, { method: "DELETE" });
    state.rooms = state.rooms.filter((r) => r.id !== roomId);
    showToast("Percakapan berhasil dihapus.", "success");

    if (roomId === state.currentRoomId) {
      if (state.rooms.length > 0) {
        setActiveRoomId(state.rooms[0].id);
      } else {
        const newRoom = await apiFetch("/api/v1/chat/rooms", {
          method: "POST",
          body: JSON.stringify({}),
        });
        state.rooms = [newRoom];
        setActiveRoomId(newRoom.id);
      }
      await loadChatHistory();
    }
    renderRoomList(state.rooms);
  } catch (err) {
    showToast(err.message || "Gagal menghapus percakapan.", "error");
  }
}

function renderSources(sources, context) {
  if (!sources || sources.length === 0) {
    return `<p style="color: var(--ink-soft); font-size: 13px;">Tidak ada sumber tercatat.</p>`;
  }
  const items = sources
    .map((s, i) => `<li><span class="marker">[${i + 1}]</span><span>${escapeHtml(s.label)}</span></li>`)
    .join("");

  const contextHtml = context
    ? `<details class="sources-context">
        <summary>Lihat isi konteks yang dikirim ke LLM</summary>
        <pre class="sources-context__text">${escapeHtml(context)}</pre>
      </details>`
    : "";

  return `
    <details class="sources">
      <summary>Sumber &amp; konteks (${sources.length})</summary>
      <ul class="sources-list">${items}</ul>
      ${contextHtml}
    </details>
  `;
}

function renderChatItem(item) {
  const wrapper = document.createElement("div");
  wrapper.className = "msg-pair";

  const questionHtml = `
    <div class="msg msg--question">
      <div class="msg__bubble">${escapeHtml(item.question)}</div>
    </div>
  `;

  let answerBodyHtml;

  if (item.corrected && item.correction_text) {
    answerBodyHtml = `
      <div class="msg__answer-text">${escapeHtml(item.correction_text)}</div>
      <div class="msg__status-row">
        <span class="status-dot status-dot--verified"></span>
        <span class="status-verified-text">
          Terverifikasi oleh instruktur (${escapeHtml(item.corrected_by || "-")}, ${escapeHtml(item.correction_date || "-")})
        </span>
      </div>
      <details class="sources">
        <summary>Lihat jawaban chatbot sebelum dikoreksi</summary>
        <p style="margin-top:8px; color: var(--ink-soft); white-space: pre-wrap;">${escapeHtml(item.answer)}</p>
      </details>
    `;
  } else if (item.verified) {
    answerBodyHtml = `
      <div class="msg__answer-text">${escapeHtml(item.answer)}</div>
      <div class="msg__status-row">
        <span class="status-dot status-dot--verified"></span>
        <span class="status-verified-text">
          Terverifikasi oleh instruktur (${escapeHtml(item.verified_by || "-")}, ${escapeHtml(formatTimestamp(item.verified_at))})
        </span>
      </div>
    `;
  } else {
    answerBodyHtml = `
      <div class="msg__answer-text">${escapeHtml(item.answer)}</div>
      <div class="msg__status-row">
        <span class="status-dot"></span>
        <span>Belum diverifikasi instruktur</span>
      </div>
    `;
  }

  const answerHtml = `
    <div class="msg msg--answer">
      ${answerBodyHtml}
      ${renderSources(item.sources, item.context)}
    </div>
  `;

  wrapper.innerHTML = questionHtml + answerHtml;
  return wrapper;
}

function renderPendingPair(question) {
  const wrapper = document.createElement("div");
  wrapper.className = "msg-pair msg-pair--pending";
  wrapper.innerHTML = `
    <div class="msg msg--question">
      <div class="msg__bubble">${escapeHtml(question)}</div>
    </div>
    <div class="msg msg--pending">
      <span class="typing-dots" aria-hidden="true">
        <span></span><span></span><span></span>
      </span>
      <span>Mencari jawaban...</span>
    </div>
  `;
  return wrapper;
}

async function loadChatHistory() {
  updateChatRoomTitle();
  if (!state.currentRoomId) return;

  try {
    const history = await apiFetch(`/api/v1/chat/history?room_id=${encodeURIComponent(state.currentRoomId)}`);
    el.chatLog.innerHTML = "";

    if (!history || history.length === 0) {
      el.chatLog.innerHTML = `<div class="chat-empty">Belum ada percakapan. Coba tanyakan sesuatu tentang Susenas Maret 2025.</div>`;
      return;
    }

    history.forEach((item) => el.chatLog.appendChild(renderChatItem(item)));
    el.chatLog.scrollTop = el.chatLog.scrollHeight;
  } catch (err) {
    el.chatLog.innerHTML = `<div class="form-error">${escapeHtml(err.message)}</div>`;
  }
}

el.chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = el.chatInput.value.trim();
  if (!question || !state.currentRoomId) return;

  el.chatInput.value = "";
  const emptyMessage = el.chatLog.querySelector(".chat-empty");
  if (emptyMessage) emptyMessage.remove();

  const pendingPair = renderPendingPair(question);
  el.chatLog.appendChild(pendingPair);
  const pendingAnswerEl = pendingPair.querySelector(".msg--pending");

  requestAnimationFrame(() => {
    pendingPair.scrollIntoView({ behavior: "smooth", block: "start" });
  });

  el.chatSendBtn.disabled = true;
  el.chatSendBtn.textContent = "Mencari...";
  el.chatInput.disabled = true;

  let streamedText = "";
  let sawFirstToken = false;
  let errorDetail = null;

  try {
    const headers = { "Content-Type": "application/json", ...NGROK_HEADERS };
    if (state.token) headers["Authorization"] = `Bearer ${state.token}`;

    const response = await fetch(`${API_BASE}/api/v1/chat/ask/stream`, {
      method: "POST",
      headers,
      body: JSON.stringify({ room_id: state.currentRoomId, question }),
    });

    if (response.status === 401) {
      logout();
      throw new Error("Sesi berakhir, silakan login ulang.");
    }
    if (!response.ok || !response.body) {
      throw new Error(`Permintaan gagal (${response.status}).`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let newlineIndex;
      while ((newlineIndex = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, newlineIndex).trim();
        buffer = buffer.slice(newlineIndex + 1);
        if (!line) continue;

        const evt = JSON.parse(line);
        if (evt.type === "token") {
          if (!sawFirstToken) {
            sawFirstToken = true;
            pendingAnswerEl.innerHTML = `<div class="msg__answer-text"></div>`;
          }
          streamedText += evt.text;
          pendingAnswerEl.querySelector(".msg__answer-text").textContent = streamedText;
          el.chatLog.scrollTop = el.chatLog.scrollHeight;
        } else if (evt.type === "error") {
          errorDetail = evt.detail;
        }
        // evt.type === "done" -> tidak perlu diproses di sini,
        // loadChatHistory() di bawah yang akan render versi final
        // (lengkap dengan sumber & status verifikasi).
      }
    }

    if (errorDetail) throw new Error(errorDetail);

    await loadChatHistory();
    const rooms = await apiFetch("/api/v1/chat/rooms");
    renderRoomList(rooms);
  } catch (err) {
    if (pendingPair && pendingPair.isConnected) pendingPair.remove();
    showToast(err.message || "Terjadi kesalahan saat memproses pertanyaan Anda.", "error");
  } finally {
    el.chatSendBtn.disabled = false;
    el.chatSendBtn.textContent = "Kirim";
    el.chatInput.disabled = false;
    el.chatInput.focus();
  }
});

document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    const tab = btn.dataset.tab;
    document.getElementById("tab-correction").classList.toggle("hidden", tab !== "correction");
    document.getElementById("tab-log").classList.toggle("hidden", tab !== "log");
    document.getElementById("tab-upload").classList.toggle("hidden", tab !== "upload");
    if (tab === "correction") loadInteractions();
    if (tab === "log") loadCorrectionsLog();
  });
});

function renderCorrectionLogCard(item) {
  const card = document.createElement("div");
  card.className = "interaction-card";

  card.innerHTML = `
    <div class="interaction-card__meta">
      <span>${formatTimestamp(item.correction_at || item.correction_date)} &middot; oleh ${escapeHtml(item.corrected_by)}</span>
      <span class="tag tag--done">Terinjeksi ke KB</span>
    </div>
    <div class="interaction-card__question">Pertanyaan asli (${escapeHtml(item.username)}): ${escapeHtml(item.original_question)}</div>
    <div class="interaction-card__answer">${escapeHtml(item.correction_text)}</div>
  `;

  const deleteBtn = document.createElement("button");
  deleteBtn.className = "btn btn--small btn--danger";
  deleteBtn.textContent = "Hapus koreksi ini";

  deleteBtn.addEventListener("click", async () => {
    const confirmed = await confirmDialog({
      title: "Hapus koreksi?",
      body: "Koreksi ini akan dicabut permanen dari log, KB JSON, dan Qdrant. Interaksi terkait akan muncul lagi di antrean instruktur.",
      confirmLabel: "Hapus",
      danger: true,
    });
    if (!confirmed) return;

    deleteBtn.disabled = true;
    deleteBtn.textContent = "Menghapus...";
    try {
      await apiFetch(`/api/v1/instructor/corrections/${item.correction_id}`, { method: "DELETE" });
      showToast("Koreksi dihapus dari KB.", "success");
      await loadCorrectionsLog();
    } catch (err) {
      showToast(err.message || "Gagal menghapus koreksi.", "error");
      deleteBtn.disabled = false;
      deleteBtn.textContent = "Hapus koreksi ini";
    }
  });

  card.appendChild(deleteBtn);
  return card;
}

async function loadCorrectionsLog() {
  const container = document.getElementById("corrections-log-list");
  container.innerHTML = `<p class="spinner-note">Memuat log koreksi...</p>`;
  try {
    const corrections = await apiFetch("/api/v1/instructor/corrections");
    container.innerHTML = "";
    if (!corrections || corrections.length === 0) {
      container.innerHTML = `<p class="spinner-note">Belum ada koreksi yang tercatat.</p>`;
      return;
    }
    corrections.forEach((item) => container.appendChild(renderCorrectionLogCard(item)));
  } catch (err) {
    container.innerHTML = `<div class="form-error">${escapeHtml(err.message)}</div>`;
  }
}

function renderInteractionCard(item) {
  const card = document.createElement("div");
  card.className = "interaction-card";

  let statusTag = `<span class="tag">Terjawab</span>`;
  if (item.corrected) {
    statusTag = `<span class="tag tag--done">Sudah dikoreksi</span>`;
  } else if (item.verified) {
    statusTag = `<span class="tag tag--verified">Terverifikasi</span>`;
  } else if (item.is_abstained) {
    statusTag = `<span class="tag tag--warn">Abstain</span>`;
  }

  card.innerHTML = `
    <div class="interaction-card__meta">
      <span>${formatTimestamp(item.timestamp)} &middot; ${escapeHtml(item.username)}</span>
      ${statusTag}
    </div>
    <div class="interaction-card__question">${escapeHtml(item.question)}</div>
    <div class="interaction-card__answer">${escapeHtml(item.answer)}</div>
  `;

  if (item.corrected || item.verified) {
    const note = document.createElement("div");
    note.className = "interaction-card__done-note";
    note.textContent = item.corrected
      ? "Interaksi ini sudah pernah dikoreksi."
      : "Interaksi ini sudah ditandai terverifikasi (jawaban chatbot sudah benar).";
    card.appendChild(note);
    return card;
  }

  const verifyRow = document.createElement("div");
  verifyRow.className = "interaction-card__verify-row";

  const verifyBtn = document.createElement("button");
  verifyBtn.className = "btn btn--small btn--ghost";
  verifyBtn.textContent = "✓ Tandai Sudah Benar (tanpa koreksi)";

  verifyBtn.addEventListener("click", async () => {
    verifyBtn.disabled = true;
    verifyBtn.textContent = "Menandai...";
    try {
      await apiFetch("/api/v1/instructor/verify", {
        method: "POST",
        body: JSON.stringify({ interaction_id: item.id }),
      });
      showToast("Interaksi ditandai terverifikasi.", "success");
      await loadInteractions();
    } catch (err) {
      showToast(err.message || "Gagal menandai sebagai terverifikasi.", "error");
      verifyBtn.disabled = false;
      verifyBtn.textContent = "✓ Tandai Sudah Benar (tanpa koreksi)";
    }
  });

  verifyRow.appendChild(verifyBtn);
  card.appendChild(verifyRow);

  const textarea = document.createElement("textarea");
  textarea.placeholder = "...atau isi jawaban yang benar / koreksi di sini kalau jawaban chatbot perlu diganti";

  const submitBtn = document.createElement("button");
  submitBtn.className = "btn btn--small";
  submitBtn.textContent = "Simpan & Injeksi ke Knowledge Base";

  submitBtn.addEventListener("click", async () => {
    const correctionText = textarea.value.trim();
    if (!correctionText) {
      showToast("Isi dulu koreksinya sebelum disimpan.", "error");
      return;
    }
    submitBtn.disabled = true;
    submitBtn.textContent = "Menyuntikkan ke Knowledge Base...";
    try {
      await apiFetch("/api/v1/instructor/correct", {
        method: "POST",
        body: JSON.stringify({
          interaction_id: item.id,
          question: item.question,
          correction_text: correctionText,
        }),
      });
      showToast("Koreksi tersimpan & tersuntik ke Knowledge Base.", "success");
      await loadInteractions();
    } catch (err) {
      showToast(err.message || "Gagal menyimpan koreksi.", "error");
      submitBtn.disabled = false;
      submitBtn.textContent = "Simpan & Injeksi ke Knowledge Base";
    }
  });

  card.appendChild(textarea);
  card.appendChild(submitBtn);
  return card;
}

async function loadInteractions() {
  el.interactionsList.innerHTML = `<p class="spinner-note">Memuat percakapan...</p>`;
  const onlyUncorrected = el.onlyUncorrected.checked;
  try {
    const interactions = await apiFetch(`/api/v1/instructor/interactions?only_uncorrected=${onlyUncorrected}`);
    el.interactionsList.innerHTML = "";
    if (!interactions || interactions.length === 0) {
      el.interactionsList.innerHTML = `<p class="spinner-note">Belum ada percakapan yang tercatat.</p>`;
      return;
    }
    interactions.forEach((item) => el.interactionsList.appendChild(renderInteractionCard(item)));
  } catch (err) {
    el.interactionsList.innerHTML = `<div class="form-error">${escapeHtml(err.message)}</div>`;
  }
}

el.onlyUncorrected.addEventListener("change", () => loadInteractions());

// ---------------------------------------------------------------------
// Instruktur -- Tambah Dokumen (upload PDF)
// ---------------------------------------------------------------------

el.uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  el.uploadResult.innerHTML = "";

  const documentId = document.getElementById("doc-id").value.trim();
  const documentYear = document.getElementById("doc-year").value;
  const file = document.getElementById("doc-file").files[0];

  if (!documentId || !file) {
    el.uploadResult.innerHTML = `<div class="result-note result-note--error">Isi nama dokumen dan pilih file PDF terlebih dahulu.</div>`;
    return;
  }

  const formData = new FormData();
  formData.append("document_id", documentId);
  formData.append("document_year", documentYear);
  formData.append("file", file);

  el.uploadSubmit.disabled = true;
  el.uploadSubmit.textContent = "Mengekstrak & menyuntikkan...";

  try {
    const result = await apiFetch("/api/v1/instructor/upload-pdf", {
      method: "POST",
      body: formData,
    });
    if (result.chunks_added > 0) {
      el.uploadResult.innerHTML = `<div class="result-note result-note--ok">Berhasil menambahkan ${result.chunks_added} potongan teks baru dari "${escapeHtml(result.document_id)}".</div>`;
      el.uploadForm.reset();
      document.getElementById("doc-year").value = 2026;
    } else {
      el.uploadResult.innerHTML = `<div class="result-note result-note--ok">Tidak ada potongan teks baru yang ditambahkan -- kemungkinan PDF sudah pernah diunggah, atau tidak ada teks yang bisa diekstrak (PDF hasil scan tanpa OCR?).</div>`;
    }
  } catch (err) {
    el.uploadResult.innerHTML = `<div class="result-note result-note--error">${escapeHtml(err.message)}</div>`;
  } finally {
    el.uploadSubmit.disabled = false;
    el.uploadSubmit.textContent = "Proses & Injeksi ke Knowledge Base";
  }
});

// ---------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------

if (state.token && state.username && state.role) {
  // Sesi dipulihkan dari localStorage (reload halaman) -- BUKAN login
  // baru, jadi lanjutkan room terakhir, jangan buka room baru.
  showAppShell({ isFreshLogin: false });
} else {
  showLoginScreen();
}