import { useAuth } from "./context/AuthContext.jsx";
import { ChatRoomsProvider } from "./context/ChatRoomsContext.jsx";
import LoginScreen from "./components/LoginScreen.jsx";
import AppShell from "./components/AppShell.jsx";

export default function App() {
  const { isAuthenticated } = useAuth();

  if (!isAuthenticated) {
    return <LoginScreen />;
  }

  // ChatRoomsProvider hanya relevan untuk role "user" (percakapan/room),
  // tapi tidak masalah dipasang untuk instruktur juga -- dia cuma tidak
  // pernah dipakai (lihat AppShell: instruktur tidak me-render RoomSidebar
  // ataupun ChatView).
  return (
    <ChatRoomsProvider>
      <AppShell />
    </ChatRoomsProvider>
  );
}
