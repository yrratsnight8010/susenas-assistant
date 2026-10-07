import { formatTimestamp } from "../utils/format.js";
import { AnswerCard, AnswerText, QuestionBubble, StatusRow } from "./MessageCards.jsx";
import Sources from "./Sources.jsx";

// Status verifikasi dari backend: unverified | verified | corrected.
function resolveStatus(item) {
  if (item.status) return item.status;
  if (item.corrected) return "corrected";
  return item.verified ? "verified" : "unverified";
}

export default function ChatMessagePair({ item }) {
  const status = resolveStatus(item);
  let answerBody;

  if (status === "corrected" && item.correction_text) {
    answerBody = (
      <>
        <AnswerText>{item.correction_text}</AnswerText>
        <StatusRow tone="corrected">
          Corrected ({item.corrected_by || "-"}, {formatTimestamp(item.correction_date)})
        </StatusRow>
        <details className="mt-2.5">
          <summary className="cursor-pointer font-mono text-[12.5px] text-accent">
            Lihat jawaban chatbot sebelum dikoreksi
          </summary>
          <p className="mt-2 mb-[1em] whitespace-pre-wrap text-ink-soft">{item.answer}</p>
        </details>
      </>
    );
  } else if (status === "verified") {
    answerBody = (
      <>
        <AnswerText>{item.answer}</AnswerText>
        <StatusRow tone="verified">
          Verified ({item.verified_by || "-"}, {formatTimestamp(item.verified_at)})
        </StatusRow>
      </>
    );
  } else {
    answerBody = (
      <>
        <AnswerText>{item.answer}</AnswerText>
        <StatusRow tone="unverified">Unverified</StatusRow>
      </>
    );
  }

  // Jawaban abstain tidak punya sumber; backend juga sudah mengosongkannya.
  const showSources = !(item.is_abstained && status !== "corrected");

  return (
    <div>
      <QuestionBubble>{item.question}</QuestionBubble>
      <AnswerCard>
        {answerBody}
        {showSources && <Sources sources={item.sources} />}
      </AnswerCard>
    </div>
  );
}
