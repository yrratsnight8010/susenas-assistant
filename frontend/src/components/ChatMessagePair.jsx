import { formatTimestamp } from "../utils/format.js";
import { AnswerCard, AnswerText, QuestionBubble, StatusRow } from "./MessageCards.jsx";
import Sources from "./Sources.jsx";

export default function ChatMessagePair({ item }) {
  let answerBody;

  if (item.corrected && item.correction_text) {
    answerBody = (
      <>
        <AnswerText>{item.correction_text}</AnswerText>
        <StatusRow verified>
          Terverifikasi oleh instruktur ({item.corrected_by || "-"}, {item.correction_date || "-"})
        </StatusRow>
        <details className="mt-2.5">
          <summary className="cursor-pointer font-mono text-[12.5px] text-accent">
            Lihat jawaban chatbot sebelum dikoreksi
          </summary>
          <p className="mt-2 mb-[1em] whitespace-pre-wrap text-ink-soft">{item.answer}</p>
        </details>
      </>
    );
  } else if (item.verified) {
    answerBody = (
      <>
        <AnswerText>{item.answer}</AnswerText>
        <StatusRow verified>
          Terverifikasi oleh instruktur ({item.verified_by || "-"}, {formatTimestamp(item.verified_at)})
        </StatusRow>
      </>
    );
  } else {
    answerBody = (
      <>
        <AnswerText>{item.answer}</AnswerText>
        <StatusRow>Belum diverifikasi instruktur</StatusRow>
      </>
    );
  }

  return (
    <div>
      <QuestionBubble>{item.question}</QuestionBubble>
      <AnswerCard>
        {answerBody}
        <Sources sources={item.sources} context={item.context} />
      </AnswerCard>
    </div>
  );
}
