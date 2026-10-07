import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "../api/client.js";
import { useConfirm } from "../context/ConfirmContext.jsx";
import { useToast } from "../context/ToastContext.jsx";
import { formatTimestamp } from "../utils/format.js";
import Button from "./ui/Button.jsx";
import { TableWrap, Td, Th, Tr } from "./ui/DataTable.jsx";
import { Field, fileInputClass, inputClass } from "./ui/Field.jsx";
import { FormError, ResultNote, SpinnerNote } from "./ui/Notice.jsx";
import Tag from "./ui/Tag.jsx";

const KIND_LABELS = { base: "KB awal", upload: "Unggahan", correction: "Koreksi" };

export default function KnowledgeBaseTab({ active }) {
  return (
    <div className="grid gap-8">
      <UploadSection />
      <DocumentList active={active} />
    </div>
  );
}

function UploadSection() {
  const confirmDialog = useConfirm();
  const [documentId, setDocumentId] = useState("");
  const [documentYear, setDocumentYear] = useState(2026);
  const [file, setFile] = useState(null);
  const [fileInputKey, setFileInputKey] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null); // { ok: boolean, message: string }

  async function handleSubmit(event) {
    event.preventDefault();
    setResult(null);

    if (!documentId.trim() || !file) {
      setResult({ ok: false, message: "Isi nama dokumen dan pilih file PDF terlebih dahulu." });
      return;
    }

    const confirmed = await confirmDialog({
      title: "Unggah dan suntikkan dokumen?",
      body: `Dokumen "${documentId.trim()}" (edisi ${documentYear}) akan diproses dan ditambahkan ke Knowledge Base. Proses ini bisa memakan waktu beberapa saat.`,
      confirmLabel: "Unggah & Injeksi",
    });
    if (!confirmed) return;

    const formData = new FormData();
    formData.append("document_id", documentId.trim());
    formData.append("document_year", documentYear);
    formData.append("file", file);

    setSubmitting(true);
    try {
      const res = await apiFetch("/api/v1/instructor/upload-pdf", { method: "POST", body: formData });
      if (res.chunks_added > 0) {
        setResult({
          ok: true,
          message: `Berhasil menambahkan ${res.chunks_added} potongan teks baru dari "${res.document_id}".`,
        });
        setDocumentId("");
        setDocumentYear(2026);
        setFile(null);
        setFileInputKey((k) => k + 1);
        window.dispatchEvent(new Event("kb-documents-changed"));
      } else {
        setResult({
          ok: true,
          message:
            "Tidak ada potongan teks baru yang ditambahkan. Kemungkinan PDF sudah pernah diunggah, atau tidak ada teks yang bisa diekstrak (PDF hasil scan tanpa OCR?).",
        });
      }
    } catch (err) {
      setResult({ ok: false, message: err.message });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section>
      <h2 className="mb-3 font-display text-[16px] font-bold text-ink">Unggah Dokumen Baru</h2>
      <form className="max-w-[480px] min-w-0" onSubmit={handleSubmit}>
        <Field label="Nama/ID dokumen" htmlFor="doc-id">
          <input
            type="text"
            id="doc-id"
            className={inputClass}
            placeholder="Penegasan_Tambahan_2026"
            required
            value={documentId}
            onChange={(event) => setDocumentId(event.target.value)}
          />
        </Field>

        <Field label="Tahun edisi dokumen" htmlFor="doc-year">
          <input
            type="number"
            id="doc-year"
            className={inputClass}
            min={2000}
            max={2100}
            required
            value={documentYear}
            onChange={(event) => setDocumentYear(event.target.value)}
          />
        </Field>

        <Field label="File PDF" htmlFor="doc-file">
          <input
            key={fileInputKey}
            type="file"
            id="doc-file"
            className={fileInputClass}
            accept="application/pdf"
            required
            onChange={(event) => setFile(event.target.files[0] || null)}
          />
        </Field>

        <Button type="submit" variant="action" disabled={submitting}>
          {submitting ? "Mengekstrak & menyuntikkan..." : "Proses & Injeksi ke Knowledge Base"}
        </Button>
      </form>

      {result && <ResultNote ok={result.ok}>{result.message}</ResultNote>}
    </section>
  );
}

function DocumentList({ active }) {
  const showToast = useToast();
  const confirmDialog = useConfirm();
  const [documents, setDocuments] = useState(null);
  const [error, setError] = useState("");
  const [deletingId, setDeletingId] = useState(null);

  const load = useCallback(async () => {
    setError("");
    try {
      const data = await apiFetch("/api/v1/instructor/kb/documents");
      setDocuments(data || []);
    } catch (err) {
      setError(err.message || "Gagal memuat daftar dokumen.");
    }
  }, []);

  useEffect(() => {
    if (active) load();
  }, [active, load]);

  // Daftar ikut diperbarui begitu unggahan baru berhasil.
  useEffect(() => {
    window.addEventListener("kb-documents-changed", load);
    return () => window.removeEventListener("kb-documents-changed", load);
  }, [load]);

  async function handleDelete(doc) {
    const confirmed = await confirmDialog({
      title: "Hapus dokumen dari Knowledge Base?",
      body: `"${doc.display_name}" beserta ${doc.chunk_count} potongan teksnya akan dicabut permanen dari Knowledge Base. Chatbot tidak akan bisa lagi memakai isi dokumen ini.`,
      confirmLabel: "Hapus",
      danger: true,
    });
    if (!confirmed) return;

    setDeletingId(doc.document_id);
    try {
      await apiFetch(`/api/v1/instructor/kb/documents?document_id=${encodeURIComponent(doc.document_id)}`, {
        method: "DELETE",
      });
      showToast(`Dokumen "${doc.display_name}" dihapus dari Knowledge Base.`, "success");
      await load();
    } catch (err) {
      showToast(err.message || "Gagal menghapus dokumen.", "error");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <section>
      <h2 className="mb-3 font-display text-[16px] font-bold text-ink">Dokumen di Knowledge Base</h2>

      {error ? (
        <FormError>{error}</FormError>
      ) : documents === null ? (
        <SpinnerNote>Memuat daftar dokumen...</SpinnerNote>
      ) : documents.length === 0 ? (
        <SpinnerNote>Knowledge Base masih kosong.</SpinnerNote>
      ) : (
        <TableWrap>
          <thead>
            <tr>
              <Th>Nama Dokumen</Th>
              <Th>Jenis</Th>
              <Th>Tahun</Th>
              <Th>Potongan Teks</Th>
              <Th>Ditambahkan</Th>
              <Th>Aksi</Th>
            </tr>
          </thead>
          <tbody>
            {documents.map((doc) => (
              <Tr key={`${doc.kind}:${doc.document_id}`}>
                <Td variant="question">{doc.display_name}</Td>
                <Td>
                  <Tag tone={doc.kind === "upload" ? "corrected" : "default"}>{KIND_LABELS[doc.kind] || doc.kind}</Tag>
                </Td>
                <Td variant="meta">{doc.document_year || "-"}</Td>
                <Td variant="meta">{doc.chunk_count}</Td>
                <Td variant="meta">{doc.kind === "upload" && doc.created_at ? formatTimestamp(doc.created_at) : "-"}</Td>
                <Td variant="actions">
                  {doc.deletable ? (
                    <Button
                      size="sm"
                      variant="danger"
                      disabled={deletingId === doc.document_id}
                      onClick={() => handleDelete(doc)}
                    >
                      {deletingId === doc.document_id ? "Menghapus..." : "Hapus"}
                    </Button>
                  ) : (
                    <span className="text-[12.5px] text-ink-soft">
                      {doc.kind === "correction" ? "Kelola di Tinjau Percakapan" : "Terkunci"}
                    </span>
                  )}
                </Td>
              </Tr>
            ))}
          </tbody>
        </TableWrap>
      )}
    </section>
  );
}
