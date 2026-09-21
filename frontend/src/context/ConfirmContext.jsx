import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import Button from "../components/ui/Button.jsx";

const ConfirmContext = createContext(null);

export function ConfirmProvider({ children }) {
  const [dialog, setDialog] = useState(null);
  const resolverRef = useRef(null);

  // Dipakai persis seperti confirmDialog() di versi vanilla JS:
  // `const ok = await confirmDialog({ title, body, danger: true })`
  const confirmDialog = useCallback((options = {}) => {
    const {
      title = "Konfirmasi",
      body = "Apakah Anda yakin?",
      confirmLabel = "Ya",
      cancelLabel = "Batal",
      danger = false,
    } = options;

    return new Promise((resolve) => {
      resolverRef.current = resolve;
      setDialog({ title, body, confirmLabel, cancelLabel, danger });
    });
  }, []);

  const close = useCallback((result) => {
    if (resolverRef.current) {
      resolverRef.current(result);
      resolverRef.current = null;
    }
    setDialog(null);
  }, []);

  useEffect(() => {
    if (!dialog) return undefined;
    function onKeyDown(event) {
      if (event.key === "Escape") close(false);
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [dialog, close]);

  return (
    <ConfirmContext.Provider value={confirmDialog}>
      {children}
      {dialog && (
        <div
          className="fixed inset-0 z-[100] flex animate-overlay-in items-center justify-center bg-[rgba(15,23,42,0.5)] p-5"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) close(false);
          }}
        >
          <div
            className="w-full max-w-[400px] animate-modal-in rounded-lg bg-surface px-6 pt-6 pb-5 shadow-lg"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="confirm-modal-title"
          >
            <h2 className="mb-2 font-display text-[19px] font-bold text-ink" id="confirm-modal-title">
              {dialog.title}
            </h2>
            <p className="text-[14px] leading-normal text-ink-soft">{dialog.body}</p>
            <div className="mt-5 flex justify-end gap-2.5">
              <Button variant="ghost" onClick={() => close(false)}>
                {dialog.cancelLabel}
              </Button>
              <Button variant={dialog.danger ? "danger" : "action"} onClick={() => close(true)} autoFocus>
                {dialog.confirmLabel}
              </Button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  );
}

export function useConfirm() {
  const ctx = useContext(ConfirmContext);
  if (!ctx) throw new Error("useConfirm harus dipakai di dalam <ConfirmProvider>");
  return ctx;
}
