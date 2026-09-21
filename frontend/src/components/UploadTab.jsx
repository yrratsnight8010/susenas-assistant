import { useState } from "react";
import { apiFetch } from "../api/client.js";
import Button from "./ui/Button.jsx";
import { Field, fileInputClass, inputClass } from "./ui/Field.jsx";
import { ResultNote } from "./ui/Notice.jsx";

export default function UploadTab() {
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
      } else {
        setResult({
          ok: true,
          message:
            "Tidak ada potongan teks baru yang ditambahkan -- kemungkinan PDF sudah pernah diunggah, atau tidak ada teks yang bisa diekstrak (PDF hasil scan tanpa OCR?).",
        });
      }
    } catch (err) {
      setResult({ ok: false, message: err.message });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
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
    </div>
  );
}
