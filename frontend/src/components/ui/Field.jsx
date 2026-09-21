// Kelas untuk <input>/<textarea> di form. Sengaja berupa string konstan
// (bukan dirakit dari potongan) supaya terdeteksi Tailwind saat build.
export const inputClass =
  "w-full rounded-sm border border-line-strong bg-surface px-3 py-2.5 transition duration-100 " +
  "placeholder:text-slate-400 focus:border-accent focus:shadow-[0_0_0_3px_rgba(30,41,59,0.12)] focus:outline-none";

export const fileInputClass =
  "w-full rounded-sm border border-dashed border-line-strong bg-support px-3 py-4 text-center transition duration-100 " +
  "focus:border-accent focus:shadow-[0_0_0_3px_rgba(30,41,59,0.12)] focus:outline-none";

export const textareaClass =
  "block min-h-[76px] w-full min-w-[260px] resize-y rounded-sm border border-line-strong bg-surface px-3 py-[9px] " +
  "text-[13.5px] text-ink";

export function Field({ label, htmlFor, children }) {
  return (
    <div className="mb-[15px]">
      <label htmlFor={htmlFor} className="mb-[5px] block text-[12.5px] font-medium text-ink-soft">
        {label}
      </label>
      {children}
    </div>
  );
}
