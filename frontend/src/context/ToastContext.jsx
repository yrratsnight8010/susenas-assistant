import { createContext, useCallback, useContext, useRef, useState } from "react";
import { cx } from "../utils/cx.js";

const ToastContext = createContext(null);

// Warna garis kiri toast menurut jenisnya (jenis lain memakai oranye).
const TOAST_BORDER = {
  error: "border-danger",
  success: "border-success",
};

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const idRef = useRef(0);

  const showToast = useCallback((message, type = "success", duration = 3800) => {
    const id = ++idRef.current;
    setToasts((prev) => [...prev, { id, message, type, visible: false }]);

    // Sengaja dua langkah (tambah dulu dengan visible:false, baru
    // di-set true) supaya transisi opacity/translate sempat terpicu.
    requestAnimationFrame(() => {
      setToasts((prev) => prev.map((t) => (t.id === id ? { ...t, visible: true } : t)));
    });

    setTimeout(() => {
      setToasts((prev) => prev.map((t) => (t.id === id ? { ...t, visible: false } : t)));
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, 220);
    }, duration);
  }, []);

  return (
    <ToastContext.Provider value={showToast}>
      {children}
      <div
        className="fixed inset-x-4 bottom-[22px] z-[200] flex flex-col gap-2.5 shell:inset-x-auto shell:right-[22px] shell:max-w-[340px]"
        aria-live="polite"
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            className={cx(
              "rounded-md border-l-[3px] bg-ink px-4 py-3 text-[13.5px] leading-[1.4] text-white shadow-md transition duration-[180ms]",
              TOAST_BORDER[t.type] ?? "border-action",
              t.visible ? "translate-y-0 opacity-100" : "translate-y-2 opacity-0",
            )}
          >
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast harus dipakai di dalam <ToastProvider>");
  return ctx;
}
