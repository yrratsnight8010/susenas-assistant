import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch } from "../api/client.js";
import { useConfirm } from "../context/ConfirmContext.jsx";
import { useToast } from "../context/ToastContext.jsx";
import { formatTimestamp } from "../utils/format.js";
import Button from "./ui/Button.jsx";
import { InlineActions, TableWrap, Td, Th, Tr } from "./ui/DataTable.jsx";
import { inputClass, textareaClass } from "./ui/Field.jsx";
import { FormError, SpinnerNote } from "./ui/Notice.jsx";

// Kolom yang dicocokkan pencarian di tab ini.
function matchesSearch(item, needle) {
  if (!needle) return true;
  const haystack = `${item.corrected_by || ""} ${item.username || ""} ${item.original_question || ""} ${
    item.correction_text || ""
  }`.toLowerCase();
  return haystack.includes(needle);
}

export default function CorrectionsLogTab({ active }) {
  const showToast = useToast();
  const confirmDialog = useConfirm();
  const [corrections, setCorrections] = useState(null);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const data = await apiFetch("/api/v1/instructor/corrections");
      setCorrections(data || []);
    } catch (err) {
      setError(err.message || "Gagal memuat log koreksi.");
    }
  }, []);

  useEffect(() => {
    if (active) load();
  }, [active, load]);

  const needle = search.trim().toLowerCase();
  const filtered = useMemo(
    () => (corrections || []).filter((item) => matchesSearch(item, needle)),
    [corrections, needle],
  );

  return (
    <div>
      {corrections !== null && corrections.length > 0 && (
        <div className="mb-4 flex justify-end">
          <input
            type="search"
            className={`${inputClass} max-w-[280px]`}
            placeholder="Cari oleh / user / pertanyaan / koreksi..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
      )}

      {error ? (
        <FormError>{error}</FormError>
      ) : corrections === null ? (
        <SpinnerNote>Memuat log koreksi...</SpinnerNote>
      ) : corrections.length === 0 ? (
        <SpinnerNote>Belum ada koreksi yang tercatat.</SpinnerNote>
      ) : filtered.length === 0 ? (
        <SpinnerNote>Tidak ada hasil untuk pencarian "{search.trim()}".</SpinnerNote>
      ) : (
        <TableWrap>
          <thead>
            <tr>
              <Th>Waktu</Th>
              <Th>Oleh</Th>
              <Th>User Asal</Th>
              <Th>Pertanyaan Asli</Th>
              <Th>Isi Koreksi</Th>
              <Th>Aksi</Th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((item) => (
              <CorrectionRow
                key={item.correction_id}
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

function CorrectionRow({ item, onChanged, showToast, confirmDialog }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(item.correction_text);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);

  async function handleSave() {
    const newText = text.trim();
    if (!newText) {
      showToast("Isi koreksi tidak boleh kosong.", "error");
      return;
    }
    setSaving(true);
    try {
      await apiFetch(`/api/v1/instructor/corrections/${item.correction_id}`, {
        method: "PATCH",
        body: JSON.stringify({ correction_text: newText }),
      });
      showToast("Koreksi berhasil diperbarui & disuntik ulang ke KB.", "success");
      setEditing(false);
      await onChanged();
    } catch (err) {
      showToast(err.message || "Gagal memperbarui koreksi.", "error");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    const confirmed = await confirmDialog({
      title: "Hapus koreksi?",
      body: "Koreksi ini akan dicabut permanen dari log, KB JSON, dan Qdrant. Interaksi terkait akan muncul lagi di antrean instruktur.",
      confirmLabel: "Hapus",
      danger: true,
    });
    if (!confirmed) return;
    setDeleting(true);
    try {
      await apiFetch(`/api/v1/instructor/corrections/${item.correction_id}`, { method: "DELETE" });
      showToast("Koreksi dihapus dari KB.", "success");
      await onChanged();
    } catch (err) {
      showToast(err.message || "Gagal menghapus koreksi.", "error");
      setDeleting(false);
    }
  }

  return (
    <Tr>
      <Td variant="meta">{formatTimestamp(item.correction_at || item.correction_date)}</Td>
      <Td variant="meta">{item.corrected_by}</Td>
      <Td variant="meta">{item.username}</Td>
      <Td variant="question">{item.original_question}</Td>
      <Td variant="answer">
        {editing ? (
          <>
            <textarea
              className={textareaClass}
              value={text}
              onChange={(event) => setText(event.target.value)}
              autoFocus
            />
            <InlineActions>
              <Button size="sm" disabled={saving} onClick={handleSave}>
                {saving ? "Menyimpan..." : "Simpan"}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                disabled={saving}
                onClick={() => {
                  setText(item.correction_text);
                  setEditing(false);
                }}
              >
                Batal
              </Button>
            </InlineActions>
          </>
        ) : (
          text
        )}
      </Td>
      <Td variant="actions">
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="ghost" disabled={editing || deleting} onClick={() => setEditing(true)}>
            Edit
          </Button>
          <Button size="sm" variant="danger" disabled={editing || deleting} onClick={handleDelete}>
            {deleting ? "Menghapus..." : "Hapus"}
          </Button>
        </div>
      </Td>
    </Tr>
  );
}
