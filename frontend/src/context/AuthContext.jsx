import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { setApiToken, setUnauthorizedHandler } from "../api/client.js";

const STORAGE_KEYS = {
  token: "susenas_token",
  username: "susenas_username",
  role: "susenas_role",
  currentRoom: "susenas_current_room",
};

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [auth, setAuth] = useState(() => ({
    token: localStorage.getItem(STORAGE_KEYS.token) || null,
    username: localStorage.getItem(STORAGE_KEYS.username) || null,
    role: localStorage.getItem(STORAGE_KEYS.role) || null,
  }));

  // true persis sesudah login() dipanggil (form login disubmit), false lagi
  // kalau sesi dipulihkan dari localStorage saat reload halaman. Dipakai
  // ChatRoomsProvider untuk tahu apakah harus buka room baru (login segar)
  // atau lanjutkan room terakhir (reload/sesi lama) -- sama seperti
  // parameter isFreshLogin di showAppShell() versi vanilla JS.
  const [justLoggedIn, setJustLoggedIn] = useState(false);

  // BUG YANG DIPERBAIKI: sebelumnya sinkronisasi token ke client.js
  // dilakukan lewat useEffect -- tapi React menjalankan useEffect anak
  // LEBIH DULU daripada useEffect induk (AuthProvider ada di paling atas
  // pohon komponen). Akibatnya, begitu AppShell pertama kali dirender
  // (baik dari sesi lama yang dipulihkan localStorage, maupun sesaat
  // sesudah login()), komponen anak yang langsung fetch data di
  // useEffect-nya sendiri (mis. CorrectionsTab di panel instruktur)
  // sempat mengirim request DULUAN, sebelum useEffect AuthProvider ini
  // sempat menaruh token ke client.js -- request itu berangkat TANPA
  // header Authorization sama sekali, dan backend membalas 403 "Not
  // authenticated". Solusinya: panggil setApiToken() LANGSUNG di body
  // komponen (saat render), bukan di useEffect. Ini aman -- cuma
  // assignment ke variabel di luar React, idempoten, tidak mengubah hasil
  // render -- dan dijamin sudah selesai SEBELUM React mulai me-render
  // komponen anak mana pun, apalagi menjalankan efek mereka.
  setApiToken(auth.token);

  const login = useCallback((token, username, role) => {
    localStorage.setItem(STORAGE_KEYS.token, token);
    localStorage.setItem(STORAGE_KEYS.username, username);
    localStorage.setItem(STORAGE_KEYS.role, role);
    setAuth({ token, username, role });
    setJustLoggedIn(true);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(STORAGE_KEYS.token);
    localStorage.removeItem(STORAGE_KEYS.username);
    localStorage.removeItem(STORAGE_KEYS.role);
    localStorage.removeItem(STORAGE_KEYS.currentRoom);
    setAuth({ token: null, username: null, role: null });
    setJustLoggedIn(false);
  }, []);

  const consumeJustLoggedIn = useCallback(() => setJustLoggedIn(false), []);

  // Request manapun yang kena 401 (lewat apiFetch) memicu logout otomatis.
  useEffect(() => {
    setUnauthorizedHandler(logout);
  }, [logout]);

  const value = {
    token: auth.token,
    username: auth.username,
    role: auth.role,
    isAuthenticated: Boolean(auth.token),
    justLoggedIn,
    consumeJustLoggedIn,
    login,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth harus dipakai di dalam <AuthProvider>");
  return ctx;
}
