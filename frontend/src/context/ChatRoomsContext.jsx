import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { apiFetch } from "../api/client.js";
import { useAuth } from "./AuthContext.jsx";
import { useToast } from "./ToastContext.jsx";

const CURRENT_ROOM_KEY = "susenas_current_room";

const ChatRoomsContext = createContext(null);

export function ChatRoomsProvider({ children }) {
  const { isAuthenticated, role, justLoggedIn, consumeJustLoggedIn } = useAuth();
  const showToast = useToast();

  const [rooms, setRooms] = useState([]);
  const [currentRoomId, setCurrentRoomIdState] = useState(null);
  const [loadingRooms, setLoadingRooms] = useState(false);
  const initializedRef = useRef(false);

  const setCurrentRoomId = useCallback((roomId) => {
    setCurrentRoomIdState(roomId);
    if (roomId) localStorage.setItem(CURRENT_ROOM_KEY, roomId);
    else localStorage.removeItem(CURRENT_ROOM_KEY);
  }, []);

  const refreshRooms = useCallback(async () => {
    const list = await apiFetch("/api/v1/chat/rooms");
    setRooms(list);
    return list;
  }, []);

  const initChatRooms = useCallback(
    async (isFreshLogin) => {
      setLoadingRooms(true);
      try {
        let list = await apiFetch("/api/v1/chat/rooms");
        if (isFreshLogin || list.length === 0) {
          const activeRoom = await apiFetch("/api/v1/chat/rooms", {
            method: "POST",
            body: JSON.stringify({}),
          });
          list = await apiFetch("/api/v1/chat/rooms");
          setCurrentRoomId(activeRoom.id);
        } else {
          const savedId = localStorage.getItem(CURRENT_ROOM_KEY);
          const stillExists = list.some((r) => r.id === savedId);
          setCurrentRoomId(stillExists ? savedId : list[0].id);
        }
        setRooms(list);
      } catch (err) {
        showToast(err.message || "Gagal memuat daftar percakapan.", "error");
      } finally {
        setLoadingRooms(false);
      }
    },
    [setCurrentRoomId, showToast],
  );

  const createRoom = useCallback(async () => {
    const activeRoom = await apiFetch("/api/v1/chat/rooms", {
      method: "POST",
      body: JSON.stringify({}),
    });
    const list = await apiFetch("/api/v1/chat/rooms");
    setRooms(list);
    setCurrentRoomId(activeRoom.id);
    return activeRoom;
  }, [setCurrentRoomId]);

  const deleteRoom = useCallback(
    async (roomId) => {
      await apiFetch(`/api/v1/chat/rooms/${encodeURIComponent(roomId)}`, { method: "DELETE" });
      let list = rooms.filter((r) => r.id !== roomId);
      showToast("Percakapan berhasil dihapus.", "success");

      if (roomId === currentRoomId) {
        if (list.length > 0) {
          setCurrentRoomId(list[0].id);
        } else {
          const newRoom = await apiFetch("/api/v1/chat/rooms", {
            method: "POST",
            body: JSON.stringify({}),
          });
          list = [newRoom];
          setCurrentRoomId(newRoom.id);
        }
      }
      setRooms(list);
    },
    [rooms, currentRoomId, setCurrentRoomId, showToast],
  );

  // Inisialisasi sekali per sesi login, hanya untuk role "user" (instruktur
  // tidak punya konsep room).
  useEffect(() => {
    if (isAuthenticated && role !== "instruktur" && !initializedRef.current) {
      initializedRef.current = true;
      initChatRooms(justLoggedIn);
      if (justLoggedIn) consumeJustLoggedIn();
    }
    if (!isAuthenticated) {
      initializedRef.current = false;
      setRooms([]);
      setCurrentRoomIdState(null);
    }
  }, [isAuthenticated, role, justLoggedIn, consumeJustLoggedIn, initChatRooms]);

  const value = {
    rooms,
    currentRoomId,
    loadingRooms,
    setCurrentRoomId,
    refreshRooms,
    createRoom,
    deleteRoom,
  };

  return <ChatRoomsContext.Provider value={value}>{children}</ChatRoomsContext.Provider>;
}

export function useChatRooms() {
  const ctx = useContext(ChatRoomsContext);
  if (!ctx) throw new Error("useChatRooms harus dipakai di dalam <ChatRoomsProvider>");
  return ctx;
}
