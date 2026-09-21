import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE, apiFetch, getAuthHeaders } from "../api/client.js";
import { useAuth } from "../context/AuthContext.jsx";
import { useChatRooms } from "../context/ChatRoomsContext.jsx";
import { useToast } from "../context/ToastContext.jsx";
import ChatMessagePair from "./ChatMessagePair.jsx";
import { AnswerCard, AnswerText, PendingCard, QuestionBubble } from "./MessageCards.jsx";
import Button from "./ui/Button.jsx";
import { FormError } from "./ui/Notice.jsx";
import { randomOpeningLine, timeOfDaySalutation } from "../utils/format.js";

export default function ChatView() {
  const { username } = useAuth();
  const { rooms, currentRoomId, refreshRooms } = useChatRooms();
  const showToast = useToast();

  const [history, setHistory] = useState([]);
  const [historyError, setHistoryError] = useState("");
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  // pending: { question, streamedText, started } selama satu ronde tanya-
  // jawab streaming sedang berlangsung; null kalau tidak ada yang berjalan.
  const [pending, setPending] = useState(null);

  const chatLogRef = useRef(null);
  const textareaRef = useRef(null);
  const openingLineRef = useRef(randomOpeningLine());

  const currentRoom = rooms.find((r) => r.id === currentRoomId);
  const roomTitle = currentRoom ? currentRoom.title : "Tanya Jawab";

  const loadHistory = useCallback(async () => {
    if (!currentRoomId) return;
    setHistoryError("");
    try {
      const data = await apiFetch(`/api/v1/chat/history?room_id=${encodeURIComponent(currentRoomId)}`);
      setHistory(data || []);
      openingLineRef.current = randomOpeningLine();
    } catch (err) {
      setHistoryError(err.message || "Gagal memuat riwayat percakapan.");
    }
  }, [currentRoomId]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  useEffect(() => {
    if (chatLogRef.current) chatLogRef.current.scrollTop = chatLogRef.current.scrollHeight;
  }, [history, pending?.streamedText]);

  // Textarea tumbuh otomatis mengikuti isi, dibatasi tinggi maksimum --
  // sama seperti resizeInput() di <script> inline index.html.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 132)}px`;
  }, [input]);

  async function handleSubmit(event) {
    event.preventDefault();
    const question = input.trim();
    if (!question || !currentRoomId) return;

    setInput("");
    setPending({ question, streamedText: "", started: false });
    setSending(true);

    let streamedText = "";
    let errorDetail = null;

    try {
      const response = await fetch(`${API_BASE}/api/v1/chat/ask/stream`, {
        method: "POST",
        headers: getAuthHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ room_id: currentRoomId, question }),
      });

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
            streamedText += evt.text;
            setPending({ question, streamedText, started: true });
          } else if (evt.type === "error") {
            errorDetail = evt.detail;
          }
          // evt.type === "done" tidak perlu ditangani di sini -- loadHistory()
          // di bawah yang akan render versi final (lengkap dengan sumber &
          // status verifikasi), sama seperti versi vanilla JS.
        }
      }

      if (errorDetail) throw new Error(errorDetail);

      await loadHistory();
      await refreshRooms();
    } catch (err) {
      showToast(err.message || "Terjadi kesalahan saat memproses pertanyaan Anda.", "error");
    } finally {
      setPending(null);
      setSending(false);
    }
  }

  function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  const showEmptyGreeting = !historyError && history.length === 0 && !pending;

  return (
    <section className="flex h-full min-h-0 min-w-0 flex-col pr-[18px] max-[480px]:pr-3 shell:pr-[clamp(24px,3.5vw,52px)]">
      <div className="mb-3 border-b border-line pb-2.5 tall:mb-3.5 tall:pb-3.5">
        <h1 className="font-display text-[clamp(19px,3vw,23px)] font-bold text-ink">{roomTitle}</h1>
      </div>

      <div
        className="scroll-quiet -mr-2 mb-4 min-h-0 min-w-0 flex-1 overflow-x-hidden overflow-y-auto pr-2"
        ref={chatLogRef}
      >
        {historyError && <FormError>{historyError}</FormError>}

        {showEmptyGreeting && (
          <div className="px-5 py-10 text-center text-[14px] text-ink-soft">
            <div className="mb-1.5 text-[16px] font-semibold text-ink">
              {timeOfDaySalutation()}
              {username ? `, ${username}` : ""} 👋
            </div>
            <div className="mx-auto max-w-[440px] text-ink-soft">{openingLineRef.current}</div>
          </div>
        )}

        {!historyError && history.map((item, index) => <ChatMessagePair key={index} item={item} />)}

        {pending && (
          <div>
            <QuestionBubble>{pending.question}</QuestionBubble>
            {pending.started ? (
              <AnswerCard>
                <AnswerText>{pending.streamedText}</AnswerText>
              </AnswerCard>
            ) : (
              <PendingCard>Mencari jawaban...</PendingCard>
            )}
          </div>
        )}
      </div>

      <form
        className="flex w-full min-w-0 items-end gap-2 rounded-[18px] border border-line-strong bg-surface py-1.5 pr-[7px] pl-[18px] shadow-sm transition duration-100 focus-within:border-action focus-within:shadow-[0_0_0_3px_var(--color-action-soft)] max-[480px]:pr-[5px] max-[480px]:pl-[13px]"
        onSubmit={handleSubmit}
      >
        <textarea
          ref={textareaRef}
          rows={1}
          className="scroll-quiet block max-h-[132px] min-h-[22px] w-0 min-w-0 flex-1 resize-none overflow-x-hidden overflow-y-auto bg-transparent py-2 leading-[1.45] break-anywhere outline-none placeholder:text-slate-400"
          placeholder="Tanyakan sesuatu tentang Susenas Maret 2025..."
          autoComplete="off"
          required
          aria-label="Pertanyaan tentang Susenas Maret 2025"
          value={input}
          disabled={sending}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={handleKeyDown}
        />
        <Button
          type="submit"
          variant="action"
          className="min-w-[70px] shrink-0 self-end max-[480px]:min-w-[62px] max-[480px]:px-[13px]"
          disabled={sending}
        >
          {sending ? "Mencari..." : "Kirim"}
        </Button>
      </form>
    </section>
  );
}
