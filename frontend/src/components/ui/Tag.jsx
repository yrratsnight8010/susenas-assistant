import { cx } from "../../utils/cx.js";

// Nada status verifikasi: unverified (abu-abu), verified (hijau),
// corrected (oranye). `warn` dipakai untuk penanda Abstain.
const TONES = {
  default: "bg-support text-accent",
  unverified: "bg-support text-ink-soft",
  verified: "bg-success-soft text-success",
  corrected: "bg-action-soft text-action",
  warn: "bg-danger-soft text-danger",
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
