import { cx } from "../../utils/cx.js";

const BASE =
  "inline-flex items-center gap-[7px] border font-medium transition duration-100 " +
  "enabled:active:translate-y-px disabled:cursor-not-allowed disabled:opacity-50";

const VARIANTS = {
  // Navy: aksi biasa.
  primary: "border-accent bg-accent text-white enabled:hover:opacity-[.92]",
  // Oranye: aksi paling penting di satu layar (Masuk, Kirim, Percakapan Baru).
  action:
    "border-action bg-action text-white enabled:hover:border-action-hover enabled:hover:bg-action-hover",
  ghost: "border-line-strong bg-transparent text-ink enabled:hover:bg-support",
  // Ghost yang berubah merah saat di-hover (Keluar).
  ghostDanger:
    "border-line-strong bg-transparent text-ink enabled:hover:border-danger enabled:hover:bg-danger-soft enabled:hover:text-danger",
  danger: "border-danger bg-danger text-white enabled:hover:opacity-[.92]",
};

const SIZES = {
  md: "justify-center rounded-full px-[18px] py-2.5 text-[14px]",
  sm: "justify-center rounded-full px-3 py-1.5 text-[13px]",
  // Item navigasi di sidebar: rata kiri.
  nav: "justify-start rounded-full px-3 py-[9px] text-[14px]",
  // Tombol ikon persegi (sidebar dalam mode rail).
  icon: "size-[38px] justify-center rounded-sm p-0 text-[14px]",
};

export default function Button({
  variant = "primary",
  size = "md",
  block = false,
  type = "button",
  className,
  ...props
}) {
  return (
    <button
      type={type}
      className={cx(BASE, VARIANTS[variant], SIZES[size], block && "w-full", className)}
      {...props}
    />
  );
}
