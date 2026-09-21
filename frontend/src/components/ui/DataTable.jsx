import { cx } from "../../utils/cx.js";

export function TableWrap({ children }) {
  return (
    <div className="overflow-x-auto rounded-md border border-line bg-surface shadow-sm">
      <table className="w-full min-w-[720px] border-collapse text-[13.5px]">{children}</table>
    </div>
  );
}

export function Th({ children }) {
  return (
    <th className="border-b border-line bg-support px-3.5 py-[11px] text-left align-top font-mono text-[11px] font-bold tracking-[0.04em] whitespace-nowrap text-ink-soft uppercase">
      {children}
    </th>
  );
}

// Baris isi tabel: hover abu-abu lembut, dan sel di baris terakhir tanpa garis bawah.
export function Tr({ children }) {
  return <tr className="hover:bg-support [&:last-child>td]:border-b-0">{children}</tr>;
}

const CELL_VARIANTS = {
  base: "",
  question: "min-w-[200px] font-semibold break-anywhere",
  answer: "min-w-[220px] whitespace-pre-wrap text-ink-soft break-anywhere",
  meta: "font-mono text-[11.5px] whitespace-nowrap text-ink-soft",
  actions: "whitespace-nowrap",
  // Sel yang membentang penuh untuk panel yang dibuka di bawah satu baris.
  expand: "bg-canvas",
};

export function Td({ variant = "base", children, ...props }) {
  return (
    <td
      className={cx("border-b border-line px-3.5 py-[11px] text-left align-top", CELL_VARIANTS[variant])}
      {...props}
    >
      {children}
    </td>
  );
}

// Deretan tombol di dalam sel tabel.
export function InlineActions({ children }) {
  return <div className="mt-2 flex flex-wrap gap-2">{children}</div>;
}
