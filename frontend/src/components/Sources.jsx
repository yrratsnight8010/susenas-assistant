export default function Sources({ sources, context }) {
  if (!sources || sources.length === 0) {
    return <p className="my-[1em] text-[13px] text-ink-soft">Tidak ada sumber tercatat.</p>;
  }

  return (
    <details className="mt-2.5">
      <summary className="cursor-pointer font-mono text-[12.5px] text-accent">
        Sumber &amp; konteks ({sources.length})
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

      {context && (
        <details className="mt-2.5">
          <summary className="cursor-pointer font-mono text-[12.5px] text-ink-soft">
            Lihat isi konteks yang dikirim ke LLM
          </summary>
          <pre className="scroll-quiet mt-2 max-h-80 overflow-x-hidden overflow-y-auto rounded-sm border border-line bg-surface px-3 py-2.5 font-mono text-[12.5px] leading-normal whitespace-pre-wrap text-ink-soft break-anywhere">
            {context}
          </pre>
        </details>
      )}
    </details>
  );
}
