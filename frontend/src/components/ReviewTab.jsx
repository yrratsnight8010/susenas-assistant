import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch } from "../api/client.js";
import { useConfirm } from "../context/ConfirmContext.jsx";
import { useToast } from "../context/ToastContext.jsx";
import { formatTimestamp } from "../utils/format.js";
import Button from "./ui/Button.jsx";
import { InlineActions, TableWrap, Td, Th, Tr } from "./ui/DataTable.jsx";
import { inputClass, textareaClass } from "./ui/Field.jsx";
import { FormError, SpinnerNote } from "./ui/Notice.jsx";
import Tag from "./ui/Tag.jsx";

const STATUS_OPTIONS = [
  { value: "unverified", label: "Unverified" },
  { value: "verified", label: "Verified" },
  { value: "corrected", label: "Corrected" },
  { value: "all", label: "Semua status" },
];

const STATUS_LABELS = { unverified: "Unverified", verified: "Verified", corrected: "Corrected" };

const EMPTY_MESSAGES = {
  unverified: "Tidak ada percakapan berstatus Unverified.",
  verified: "Belum ada percakapan berstatus Verified.",
  corrected: "Belum ada percakapan berstatus Corrected.",
  all: "Belum ada percakapan yang tercatat.",
};

// Kolom yang dicocokkan pencarian di tab ini.
function matchesSearch(item, needle) {
  if (!needle) return true;
  const haystack = `${item.username || ""} ${item.question || ""} ${item.answer || ""} ${
    item.correction_text || ""
  }`.toLowerCase();
  return haystack.includes(needle);
}

export default function ReviewTab({ active }) {
  const showToast = useToast();
  const confirmDialog = useConfirm();
  const [statusFilter, setStatusFilter] = useState("unverified");
  const [interactions, setInteractions] = useState(null);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const data = await apiFetch(`/api/v1/instructor/interactions?status=${statusFilter}`);
      setInteractions(data || []);
    } catch (err) {
      setError(err.message || "Gagal memuat percakapan.");
    }
  }, [statusFilter]);

  useEffect(() => {
    if (active) load();
  }, [active, load]);

  const needle = search.trim().toLowerCase();
  const filtered = useMemo(
    () => (interactions || []).filter((item) => matchesSearch(item, needle)),
    [interactions, needle],
  );

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 text-[13.5px] text-ink-soft">
          <label htmlFor="status-filter">Status:</label>
          <select
            id="status-filter"
            className="rounded-sm border border-line-strong bg-surface px-3 py-2 text-[13.5px] text-ink focus:border-accent focus:outline-none"
            value={statusFilter}
            onChange={(event) => {
              setInteractions(null);
              setStatusFilter(event.target.value);
            }}
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        {interactions !== null && interactions.length > 0 && (
          <input
            type="search"
            className={`${inputClass} ml-auto max-w-[280px]`}
            placeholder="Cari user / pertanyaan / jawaban..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        )}
      </div>

      {error ? (
        <FormError>{error}</FormError>
      ) : interactions === null ? (
        <SpinnerNote>Memuat percakapan...</SpinnerNote>
      ) : interactions.length === 0 ? (
        <SpinnerNote>{EMPTY_MESSAGES[statusFilter]}</SpinnerNote>
      ) : filtered.length === 0 ? (
        <SpinnerNote>Tidak ada hasil untuk pencarian "{search.trim()}".</SpinnerNote>
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
            {filtered.map((item) => (
              <InteractionRow
                key={item.id}
                item={item}
                onChanged={load}
                showToast={showToast}
                confirmDialog={confirmDialog}
              />
            ))}
          </tbody>
        </TableWrap>
      )}
    </div>
  );
}

function InteractionRow({ item, onChanged, showToast, confirmDialog }) {
  const [expanded, setExpanded] = useState(false);
  const [correctionText, setCorrectionText] = useState("");
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState("");
  // Aksi yang sedang berjalan: verify | unverify | submit | save | delete | null
  const [busy, setBusy] = useState(null);

  const status = item.status || "unverified";
  const isBusy = busy !== null;

  // Satu pembungkus untuk semua aksi: konfirmasi -> panggil API -> toast -> muat ulang.
  async function runAction({ key, confirm, request, successMessage, failMessage, onSuccess }) {
    const confirmed = await confirmDialog(confirm);
    if (!confirmed) return;
    setBusy(key);
    try {
      await request();
      showToast(successMessage, "success");
      onSuccess?.();
      await onChanged();
    } catch (err) {
      showToast(err.message || failMessage, "error");
    } finally {
      setBusy(null);
    }
  }

  function handleVerify() {
    return runAction({
      key: "verify",
      confirm: {
        title: "Tandai sebagai Verified?",
        body: "Jawaban chatbot ini ditandai sudah benar apa adanya. Tidak ada koreksi yang disuntikkan ke Knowledge Base.",
        confirmLabel: "Tandai Verified",
      },
      request: () =>
        apiFetch("/api/v1/instructor/verify", {
          method: "POST",
          body: JSON.stringify({ interaction_id: item.id }),
        }),
      successMessage: "Percakapan ditandai Verified.",
      failMessage: "Gagal menandai sebagai Verified.",
    });
  }

  function handleUnverify() {
    return runAction({
      key: "unverify",
      confirm: {
        title: "Batalkan verifikasi?",
        body: "Percakapan ini akan kembali berstatus Unverified.",
        confirmLabel: "Batalkan Verifikasi",
      },
      request: () =>
        apiFetch("/api/v1/instructor/unverify", {
          method: "POST",
          body: JSON.stringify({ interaction_id: item.id }),
        }),
      successMessage: "Verifikasi dibatalkan.",
      failMessage: "Gagal membatalkan verifikasi.",
    });
  }

  function handleSubmitCorrection() {
    const text = correctionText.trim();
    if (!text) {
      showToast("Isi dulu koreksinya sebelum disimpan.", "error");
      return Promise.resolve();
    }
    return runAction({
      key: "submit",
      confirm: {
        title: "Simpan koreksi ke Knowledge Base?",
        body: "Koreksi akan disimpan dan disuntikkan sebagai pengetahuan baru, sehingga memengaruhi jawaban chatbot untuk semua pengguna. Anda masih bisa mengedit atau menghapusnya nanti.",
        confirmLabel: "Simpan & Injeksi",
      },
      request: () =>
        apiFetch("/api/v1/instructor/correct", {
          method: "POST",
          body: JSON.stringify({ interaction_id: item.id, correction_text: text }),
        }),
      successMessage: "Koreksi tersimpan & tersuntik ke Knowledge Base.",
      failMessage: "Gagal menyimpan koreksi.",
    });
  }

  function handleSaveEdit() {
    const text = editText.trim();
    if (!text) {
      showToast("Isi koreksi tidak boleh kosong.", "error");
      return Promise.resolve();
    }
    return runAction({
      key: "save",
      confirm: {
        title: "Simpan perubahan koreksi?",
        body: "Versi lama koreksi akan dicabut dari Knowledge Base dan diganti dengan versi baru.",
        confirmLabel: "Simpan Perubahan",
      },
      request: () =>
        apiFetch(`/api/v1/instructor/corrections/${item.correction_id}`, {
          method: "PATCH",
          body: JSON.stringify({ correction_text: text }),
        }),
      successMessage: "Koreksi diperbarui & disuntik ulang ke Knowledge Base.",
      failMessage: "Gagal memperbarui koreksi.",
      onSuccess: () => setEditing(false),
    });
  }

  function handleDeleteCorrection() {
    return runAction({
      key: "delete",
      confirm: {
        title: "Hapus koreksi?",
        body: "Koreksi akan dicabut permanen dari Knowledge Base. Percakapan ini kembali berstatus Unverified.",
        confirmLabel: "Hapus",
        danger: true,
      },
      request: () => apiFetch(`/api/v1/instructor/corrections/${item.correction_id}`, { method: "DELETE" }),
      successMessage: "Koreksi dihapus dari Knowledge Base.",
      failMessage: "Gagal menghapus koreksi.",
    });
  }

  function startEdit() {
    setEditText(item.correction_text || "");
    setEditing(true);
  }

  return (
    <>
      <Tr>
        <Td variant="meta">{formatTimestamp(item.timestamp)}</Td>
        <Td variant="meta">{item.username}</Td>
        <Td>
          <div className="flex flex-wrap gap-1.5">
            <Tag tone={status}>{STATUS_LABELS[status] || status}</Tag>
            {item.is_abstained && <Tag tone="warn">Abstain</Tag>}
          </div>
        </Td>
        <Td variant="question">{item.question}</Td>
        <Td variant="answer">
          {item.answer}

          {status === "verified" && (
            <div className="mt-2 font-mono text-[11.5px] text-success">
              Verified oleh {item.verified_by || "-"}, {formatTimestamp(item.verified_at)}
            </div>
          )}

          {status === "corrected" && (
            <div className="mt-2.5 rounded-sm border border-line bg-canvas px-3 py-2.5">
              <div className="mb-1.5 font-mono text-[11.5px] text-action">
                Koreksi oleh {item.corrected_by || "-"}, {formatTimestamp(item.correction_at || item.correction_date)}
              </div>
              {editing ? (
                <>
                  <textarea
                    className={textareaClass}
                    value={editText}
                    onChange={(event) => setEditText(event.target.value)}
                    autoFocus
                  />
                  <InlineActions>
                    <Button size="sm" disabled={isBusy} onClick={handleSaveEdit}>
                      {busy === "save" ? "Menyimpan..." : "Simpan"}
                    </Button>
                    <Button size="sm" variant="ghost" disabled={isBusy} onClick={() => setEditing(false)}>
                      Batal
                    </Button>
                  </InlineActions>
                </>
              ) : (
                <div className="whitespace-pre-wrap text-ink">{item.correction_text}</div>
              )}
            </div>
          )}
        </Td>
        <Td variant="actions">
          {status === "unverified" && (
            <Button size="sm" variant="ghost" onClick={() => setExpanded((v) => !v)}>
              {expanded ? "Tutup" : "Tinjau"}
            </Button>
          )}

          {status === "verified" && (
            <Button size="sm" variant="ghost" disabled={isBusy} onClick={handleUnverify}>
              {busy === "unverify" ? "Membatalkan..." : "Batalkan Verifikasi"}
            </Button>
          )}

          {status === "corrected" && (
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="ghost" disabled={isBusy || editing} onClick={startEdit}>
                Edit
              </Button>
              <Button size="sm" variant="danger" disabled={isBusy || editing} onClick={handleDeleteCorrection}>
                {busy === "delete" ? "Menghapus..." : "Hapus"}
              </Button>
            </div>
          )}
        </Td>
      </Tr>

      {status === "unverified" && expanded && (
        <Tr>
          <Td variant="expand" colSpan={6}>
            <InlineActions>
              <Button size="sm" variant="ghost" disabled={isBusy} onClick={handleVerify}>
                {busy === "verify" ? "Menandai..." : "✓ Tandai Verified (tanpa koreksi)"}
              </Button>
            </InlineActions>

            <textarea
              className={textareaClass}
              placeholder="...atau isi jawaban yang benar / koreksi di sini kalau jawaban chatbot perlu diganti"
              value={correctionText}
              onChange={(event) => setCorrectionText(event.target.value)}
            />

            <InlineActions>
              <Button size="sm" disabled={isBusy} onClick={handleSubmitCorrection}>
                {busy === "submit" ? "Menyuntikkan ke Knowledge Base..." : "Simpan & Injeksi ke Knowledge Base"}
              </Button>
            </InlineActions>
          </Td>
        </Tr>
      )}
    </>
  );
}
