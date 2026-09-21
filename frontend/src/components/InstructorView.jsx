import { useState } from "react";
import { cx } from "../utils/cx.js";
import CorrectionsLogTab from "./CorrectionsLogTab.jsx";
import CorrectionsTab from "./CorrectionsTab.jsx";
import UploadTab from "./UploadTab.jsx";

const TABS = [
  { id: "correction", label: "Koreksi Jawaban" },
  { id: "log", label: "Log Koreksi" },
  { id: "upload", label: "Tambah Dokumen" },
];

export default function InstructorView() {
  const [activeTab, setActiveTab] = useState("correction");

  return (
    // Hanya panel ini yang scroll (main tidak), sehingga scrollbar berada di tepi kanan viewport.
    <section className="scroll-quiet h-full min-h-0 min-w-0 overflow-x-hidden overflow-y-auto pr-[18px] pb-8 max-[480px]:pr-3 shell:pr-[clamp(24px,3.5vw,52px)]">
      <div className="w-full shell:max-w-[1280px]">
        <h1 className="font-display text-[clamp(19px,3vw,23px)] font-bold text-ink">Panel Instruktur</h1>

        <div className="mb-[22px] flex gap-[22px] overflow-x-auto border-b border-line">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              className={cx(
                "-mb-px border-b-2 bg-transparent px-0 pt-2 pb-3 text-[14.5px] whitespace-nowrap",
                activeTab === tab.id
                  ? "border-action font-semibold text-ink"
                  : "border-transparent text-ink-soft",
              )}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Setiap tab tetap mounted (bukan unmount/remount) supaya state-nya
            (mis. checkbox filter, baris yang sedang di-expand) tidak hilang
            waktu pindah tab. Tab yang tidak aktif cukup disembunyikan. */}
        <div className={activeTab === "correction" ? undefined : "hidden"}>
          <CorrectionsTab active={activeTab === "correction"} />
        </div>
        <div className={activeTab === "log" ? undefined : "hidden"}>
          <CorrectionsLogTab active={activeTab === "log"} />
        </div>
        <div className={activeTab === "upload" ? undefined : "hidden"}>
          <UploadTab />
        </div>
      </div>
    </section>
  );
}
