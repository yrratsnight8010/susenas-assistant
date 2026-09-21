import { useChatRooms } from "../context/ChatRoomsContext.jsx";
import { useConfirm } from "../context/ConfirmContext.jsx";
import { useToast } from "../context/ToastContext.jsx";
import { cx } from "../utils/cx.js";
import { formatRelativeTime } from "../utils/format.js";
import Button from "./ui/Button.jsx";

export default function RoomSidebar({ rail = false, onNavigate }) {
  const { rooms, currentRoomId, setCurrentRoomId, createRoom, deleteRoom } = useChatRooms();
  const confirmDialog = useConfirm();
  const showToast = useToast();

  async function handleNewRoom() {
    try {
      await createRoom();
      onNavigate?.();
    } catch (err) {
      showToast(err.message || "Gagal membuka percakapan baru.", "error");
    }
  }

  function handleSelect(roomId) {
    if (roomId === currentRoomId) return;
    setCurrentRoomId(roomId);
    onNavigate?.();
  }

  async function handleDelete(room, event) {
    event.stopPropagation();
    const confirmed = await confirmDialog({
      title: "Hapus percakapan ini?",
      body: `"${room.title}" akan dihapus permanen beserta seluruh riwayat tanya-jawab di dalamnya. Tindakan ini tidak bisa dibatalkan.`,
      confirmLabel: "Hapus",
      danger: true,
    });
    if (!confirmed) return;
    try {
      await deleteRoom(room.id);
    } catch (err) {
      showToast(err.message || "Gagal menghapus percakapan.", "error");
    }
  }

  return (
    <div
      className={cx(
        "flex min-h-0 flex-1 flex-col border-t pt-4",
        rail ? "items-center border-transparent" : "border-line",
      )}
    >
      <Button
        variant="action"
        size={rail ? "icon" : "nav"}
        block={!rail}
        className={rail ? "shrink-0" : "mb-3"}
        title="Percakapan Baru"
        aria-label="Percakapan Baru"
        onClick={handleNewRoom}
      >
        <svg viewBox="0 0 16 16" width="15" height="15" fill="none" aria-hidden="true">
          <path d="M8 3v10M3 8h10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
        {!rail && <span>Percakapan Baru</span>}
      </Button>

      {!rail && (
        <div className="scroll-quiet -mx-1.5 flex flex-1 flex-col gap-0.5 overflow-x-hidden overflow-y-auto px-1.5">
          {rooms.length === 0 ? (
            <p className="px-1.5 py-2.5 text-[13px] text-ink-soft">Belum ada percakapan.</p>
          ) : (
            rooms.map((room) => {
              const active = room.id === currentRoomId;
              return (
                <div
                  key={room.id}
                  className={cx(
                    "group/room relative flex min-w-0 items-stretch rounded-sm focus-within:bg-surface hover:bg-surface",
                    active && "bg-surface shadow-sm",
                  )}
                >
                  <button
                    type="button"
                    className="flex min-w-0 flex-1 flex-col gap-0.5 rounded-sm bg-transparent px-2 py-[9px] text-left"
                    onClick={() => handleSelect(room.id)}
                  >
                    <span
                      className={cx(
                        "truncate text-[13.5px]",
                        active ? "font-semibold text-accent" : "text-ink",
                      )}
                    >
                      {room.title}
                    </span>
                    <span className="font-mono text-[11px] text-ink-soft">
                      {formatRelativeTime(room.updated_at)}
                    </span>
                  </button>
                  <button
                    type="button"
                    className="flex w-[30px] shrink-0 items-center justify-center rounded-sm bg-transparent text-ink-soft opacity-0 transition duration-100 group-focus-within/room:opacity-100 group-hover/room:opacity-100 hover:bg-danger-soft hover:text-danger focus-visible:opacity-100"
                    title="Hapus percakapan"
                    aria-label={`Hapus percakapan "${room.title}"`}
                    onClick={(event) => handleDelete(room, event)}
                  >
                    <svg viewBox="0 0 16 16" width="15" height="15" fill="none" aria-hidden="true">
                      <path
                        d="M3 4.5h10M6.5 4.5V3a1 1 0 0 1 1-1h1a1 1 0 0 1 1 1v1.5M4.5 4.5 5 13a1 1 0 0 0 1 1h4a1 1 0 0 0 1-1l.5-8.5"
                        stroke="currentColor"
                        strokeWidth="1.4"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </button>
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
