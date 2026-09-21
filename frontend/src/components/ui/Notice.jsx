import { cx } from "../../utils/cx.js";

export function FormError({ children }) {
  return (
    <div className="mt-3 rounded-sm bg-danger-soft px-3 py-[9px] text-[13.5px] text-danger">{children}</div>
  );
}

export function ResultNote({ ok, children }) {
  return (
    <div
      className={cx(
        "mt-3.5 rounded-sm px-3 py-2.5 text-[13.5px]",
        ok ? "bg-success-soft text-success" : "bg-danger-soft text-danger",
      )}
    >
      {children}
    </div>
  );
}

export function SpinnerNote({ children }) {
  return <p className="text-[13.5px] text-ink-soft italic">{children}</p>;
}
