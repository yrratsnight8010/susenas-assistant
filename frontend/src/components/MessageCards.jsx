import { cx } from "../utils/cx.js";

// Gelembung pertanyaan pengguna (rata kanan).
export function QuestionBubble({ children }) {
  return (
    <div className="mb-4 flex min-w-0 animate-msg-in justify-end tall:mb-2.5">
      <div className="max-w-[92%] rounded-[16px_16px_4px_16px] bg-ink px-4 py-2.5 text-[14.5px] text-white break-anywhere shell:max-w-[min(82%,820px)]">
        {children}
      </div>
    </div>
  );
}

// Kartu jawaban chatbot.
export function AnswerCard({ children }) {
  return (
    <div className="mb-4 min-w-0 animate-msg-in rounded-lg border border-line bg-surface px-[15px] py-3.5 tall:mb-[22px] shell:px-5 shell:py-[18px]">
      {children}
    </div>
  );
}

export function AnswerText({ children }) {
  return <div className="text-[15px] whitespace-pre-wrap break-anywhere">{children}</div>;
}

// Baris status di bawah jawaban: titik kecil + keterangan.
export function StatusRow({ verified = false, children }) {
  return (
    <div className="mt-[9px] flex flex-wrap items-center gap-2 text-[12.5px] text-ink-soft">
      <span
        className={cx(
          "inline-block size-[7px] shrink-0 rounded-full border-[1.5px]",
          verified ? "border-action bg-action" : "border-ink-soft",
        )}
      />
      <span className={verified ? "text-action" : undefined}>{children}</span>
    </div>
  );
}

const DOT_DELAYS = ["", "[animation-delay:0.15s]", "[animation-delay:0.3s]"];

// Indikator "sedang mencari jawaban" sebelum token pertama datang.
export function PendingCard({ children }) {
  return (
    <div className="mb-4 flex min-w-0 animate-msg-in items-center gap-2.5 rounded-lg border border-line bg-support px-[18px] py-3.5 text-[13.5px] text-ink-soft tall:mb-[22px]">
      <span className="inline-flex shrink-0 gap-1" aria-hidden="true">
        {DOT_DELAYS.map((delay, index) => (
          <span
            key={index}
            className={cx("size-1.5 animate-typing rounded-full bg-action opacity-[.35]", delay)}
          />
        ))}
      </span>
      <span>{children}</span>
    </div>
  );
}
