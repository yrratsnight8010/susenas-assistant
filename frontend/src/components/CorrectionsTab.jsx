import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "../api/client.js";
import { useToast } from "../context/ToastContext.jsx";
import { formatTimestamp } from "../utils/format.js";
import Button from "./ui/Button.jsx";
import { InlineActions, TableWrap, Td, Th, Tr } from "./ui/DataTable.jsx";
import { textareaClass } from "./ui/Field.jsx";
import { FormError, SpinnerNote } from "./ui/Notice.jsx";
import Tag from "./ui/Tag.jsx";

export default function CorrectionsTab({ active }) {
  const showToast = useToast();
  const [onlyUncorrected, setOnlyUncorrected] = useState(true);
  const [interactions, setInteractions] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const data = await apiFetch(`/api/v1/instructor/interactions?only_uncorrected=${onlyUncorrected}`);
      setInteractions(data || []);
    } catch (err) {
      setError(err.message || "Gagal memuat interaksi.");
    }
  }, [onlyUncorrected]);

  useEffect(() => {
    if (active) load();
  }, [active, load]);

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2 text-[13.5px] text-ink-soft">
        <input
          type="checkbox"
          id="only-uncorrected"
          checked={onlyUncorrected}
          onChange={(event) => setOnlyUncorrected(event.target.checked)}
        />
        <label htmlFor="only-uncorrected">Hanya tampilkan yang belum dikoreksi</label>
      </div>

      {error ? (
        <FormError>{error}</FormError>
      ) : interactions === null ? (
        <SpinnerNote>Memuat percakapan...</SpinnerNote>
      ) : interactions.length === 0 ? (
        <SpinnerNote>Belum ada percakapan yang tercatat.</SpinnerNote>
      ) : (
        <TableWrap>
          <thead>
            <tr>
              <Th>Waktu</Th>
              <Th>User</Th>
              <Th>Status</Th>
              <Th>Pertanyaan</Th>
              <Th>Jawaban Chatbot</Th>
              <Th>Aksi</Th>
            </tr>
          </thead>
          <tbody>
            {interactions.map((item) => (
              <InteractionRow key={item.id} item={item} onChanged={load} showToast={showToast} />
            ))}
          </tbody>
        </TableWrap>
      )}
    </div>
  );
}

function InteractionRow({ item, onChanged, showToast }) {
  const [expanded, setExpanded] = useState(false);
  const [correctionText, setCorrectionText] = useState("");
  const [verifying, setVerifying] = useState(false);
  const [saving, setSaving] = useState(false);

  let statusTag = <Tag>Terjawab</Tag>;
  if (item.corrected) statusTag = <Tag tone="done">Sudah dikoreksi</Tag>;
  else if (item.verified) statusTag = <Tag tone="verified">Terverifikasi</Tag>;
  else if (item.is_abstained) statusTag = <Tag tone="warn">Abstain</Tag>;

  const resolved = item.corrected || item.verified;

  async function handleVerify() {
    setVerifying(true);
    try {
      await apiFetch("/api/v1/instructor/verify", {
        method: "POST",
        body: JSON.stringify({ interaction_id: item.id }),
      });
      showToast("Interaksi ditandai terverifikasi.", "success");
      await onChanged();
    } catch (err) {
      showToast(err.message || "Gagal menandai sebagai terverifikasi.", "error");
      setVerifying(false);
    }
  }

  async function handleSubmitCorrection() {
    const text = correctionText.trim();
    if (!text) {
      showToast("Isi dulu koreksinya sebelum disimpan.", "error");
      return;
    }
    setSaving(true);
    try {
      await apiFetch("/api/v1/instructor/correct", {
        method: "POST",
        body: JSON.stringify({ interaction_id: item.id, question: item.question, correction_text: text }),
      });
      showToast("Koreksi tersimpan & tersuntik ke Knowledge Base.", "success");
      await onChanged();
    } catch (err) {
      showToast(err.message || "Gagal menyimpan koreksi.", "error");
      setSaving(false);
    }
  }

  return (
    <>
      <Tr>
        <Td variant="meta">{formatTimestamp(item.timestamp)}</Td>
        <Td variant="meta">{item.username}</Td>
        <Td>{statusTag}</Td>
        <Td variant="question">{item.question}</Td>
        <Td variant="answer">{item.answer}</Td>
        <Td variant="actions">
          {resolved ? (
            <span className="text-[12.5px] text-ink-soft">
              {item.corrected ? "Sudah dikoreksi" : "Sudah diverifikasi"}
            </span>
          ) : (
            <Button size="sm" variant="ghost" onClick={() => setExpanded((v) => !v)}>
              {expanded ? "Tutup" : "Tinjau"}
            </Button>
          )}
        </Td>
      </Tr>

      {!resolved && expanded && (
        <Tr>
          <Td variant="expand" colSpan={6}>
            <InlineActions>
              <Button size="sm" variant="ghost" disabled={verifying} onClick={handleVerify}>
                {verifying ? "Menandai..." : "✓ Tandai Sudah Benar (tanpa koreksi)"}
              </Button>
            </InlineActions>

            <textarea
              className={textareaClass}
              placeholder="...atau isi jawaban yang benar / koreksi di sini kalau jawaban chatbot perlu diganti"
              value={correctionText}
              onChange={(event) => setCorrectionText(event.target.value)}
            />

            <InlineActions>
              <Button size="sm" disabled={saving} onClick={handleSubmitCorrection}>
                {saving ? "Menyuntikkan ke Knowledge Base..." : "Simpan & Injeksi ke Knowledge Base"}
              </Button>
            </InlineActions>
          </Td>
        </Tr>
      )}
    </>
  );
}
