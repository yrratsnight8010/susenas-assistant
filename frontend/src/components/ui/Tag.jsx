import { cx } from "../../utils/cx.js";

const TONES = {
  default: "bg-support text-accent",
  verified: "bg-support text-accent",
  warn: "bg-danger-soft text-danger",
  done: "bg-action-soft text-action",
};

export default function Tag({ tone = "default", children }) {
  return (
    <span
      className={cx(
        "rounded-[3px] px-[7px] py-px font-mono text-[11px] whitespace-nowrap",
        TONES[tone],
      )}
    >
      {children}
    </span>
  );
}
