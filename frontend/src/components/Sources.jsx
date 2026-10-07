// Daftar sumber di bawah jawaban. Isi konteks yang dikirim ke LLM tidak
// pernah ditampilkan (dan memang tidak lagi dikirim backend ke petugas).
// Tidak menampilkan apa pun kalau tidak ada sumber (mis. jawaban abstain).
export default function Sources({ sources }) {
  if (!sources || sources.length === 0) return null;

  return (
    <details className="mt-2.5">
      <summary className="cursor-pointer font-mono text-[12.5px] text-accent">
        Sumber ({sources.length})
      </summary>
      <ul className="mt-2 list-none p-0 text-[13px] text-ink-soft break-anywhere">
        {sources.map((source, index) => (
          <li
            key={index}
            className="flex gap-2 border-b border-dashed border-line py-[5px] break-anywhere last:border-b-0"
          >
            <span className="shrink-0 font-mono text-accent">[{index + 1}]</span>
            <span>{source.label}</span>
          </li>
        ))}
      </ul>
    </details>
  );
}
