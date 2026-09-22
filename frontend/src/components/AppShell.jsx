import { useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext.jsx";
import { cx } from "../utils/cx.js";
import { useMediaQuery } from "../utils/useMediaQuery.js";
import ChatView from "./ChatView.jsx";
import InstructorView from "./InstructorView.jsx";
import RoomSidebar from "./RoomSidebar.jsx";
import Button from "./ui/Button.jsx";

const SIDEBAR_COLLAPSED_KEY = "susenas_sidebar_collapsed";

// Sama dengan breakpoint `shell` di index.css (901px ke atas = desktop).
const DESKTOP_QUERY = "(min-width: 901px)";

export default function AppShell() {
  const { username, role, logout } = useAuth();
  const isInstructor = role === "instruktur";
  const isDesktop = useMediaQuery(DESKTOP_QUERY);

  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "1");

  // Mode rail (sidebar diciutkan jadi kolom ikon) hanya berlaku di desktop.
  // Di mobile sidebar selalu berupa drawer penuh, jadi pilihan "collapsed"
  // yang tersimpan dari sesi desktop tidak boleh ikut menyembunyikan isinya.
  const rail = collapsed && isDesktop;

  useEffect(() => {
    localStorage.setItem(SIDEBAR_COLLAPSED_KEY, collapsed ? "1" : "0");
  }, [collapsed]);

  // Drawer mobile otomatis tertutup kalau layar dilebarkan sampai desktop.
  useEffect(() => {
    if (isDesktop) setMobileOpen(false);
  }, [isDesktop]);

  function closeMobileSidebarIfNeeded() {
    if (!isDesktop) setMobileOpen(false);
  }

  return (
    <div className="block h-dvh min-h-0 overflow-hidden shell:flex">
      <header className="sticky top-0 z-[25] flex items-center gap-3 border-b border-line bg-surface px-4 py-3 shell:hidden">
        <button
          type="button"
          className="inline-flex size-9 shrink-0 items-center justify-center rounded-sm border border-line-strong bg-surface text-ink hover:bg-support"
          aria-label="Buka menu"
          aria-expanded={mobileOpen}
          aria-controls="app-sidebar"
          onClick={() => setMobileOpen((v) => !v)}
        >
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" aria-hidden="true">
            <path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
        </button>
        <div className="truncate font-display text-[15px] font-semibold text-ink">Susenas Maret</div>
      </header>

      <div
        className={cx(
          "fixed inset-0 z-30 bg-[rgba(15,23,42,0.45)] transition-opacity duration-200 shell:hidden",
          mobileOpen ? "pointer-events-auto opacity-100" : "pointer-events-none opacity-0",
        )}
        onClick={() => setMobileOpen(false)}
      />

      <aside
        id="app-sidebar"
        className={cx(
          // Mobile (default): drawer yang meluncur dari kiri.
          "fixed inset-y-0 left-0 z-40 flex h-dvh flex-col overflow-hidden border-r border-line bg-support pt-[22px] transition-transform duration-[220ms]",
          // Desktop: kolom tetap di sisi kiri, lebarnya dianimasikan saat diciutkan.
          "shell:sticky shell:top-0 shell:shrink-0 shell:translate-x-0 shell:shadow-none shell:transition-[width,padding]",
          mobileOpen ? "translate-x-0 shadow-lg" : "-translate-x-full",
          rail ? "w-[68px] items-center px-3 pb-4" : "w-[min(84vw,320px)] px-[18px] pb-5 shell:w-72",
        )}
      >
        <div className={cx("flex items-center gap-2.5 pb-[18px]", rail ? "flex-col" : "px-0.5")}>
          <span className="flex size-8 shrink-0 items-center justify-center rounded-sm bg-accent font-display text-[15px] font-bold text-white">
            S
          </span>

          {!rail && (
            <>
              <span className="min-w-0 font-display text-[16px] leading-tight font-semibold text-ink">
                Susenas Maret
                <span className="mt-0.5 block font-sans text-[12px] font-normal text-ink-soft">
                  Asisten Tanya-Jawab
                </span>
              </span>

              <button
                type="button"
                className="ml-auto hidden size-[26px] shrink-0 items-center justify-center rounded-sm bg-transparent text-ink-soft transition-colors duration-100 hover:bg-surface hover:text-ink shell:inline-flex"
                aria-label="Tutup sidebar"
                title="Tutup sidebar"
                onClick={() => setCollapsed(true)}
              >
                <svg viewBox="0 0 16 16" width="16" height="16" fill="none" aria-hidden="true">
                  <path
                    d="M10 3.5 5.5 8l4.5 4.5"
                    stroke="currentColor"
                    strokeWidth="1.6"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>
            </>
          )}

          {rail && (
            <button
              type="button"
              className="inline-flex size-[34px] shrink-0 items-center justify-center rounded-sm border border-line bg-surface text-ink-soft transition-colors duration-100 hover:bg-support hover:text-ink"
              aria-label="Buka sidebar"
              title="Buka sidebar"
              onClick={() => setCollapsed(false)}
            >
              <svg viewBox="0 0 16 16" width="16" height="16" fill="none" aria-hidden="true">
                <path
                  d="M6 3.5 10.5 8 6 12.5"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
          )}
        </div>

        {!isInstructor && <RoomSidebar rail={rail} onNavigate={closeMobileSidebarIfNeeded} />}

        <div className={cx("mt-3 pt-4", rail ? "flex justify-center" : "border-t border-line")}>
          {!rail && (
            <div>
              <div className="truncate text-[14px] font-medium text-ink">{username || "-"}</div>
              <span
                className={cx(
                  "mt-1 inline-block rounded-[3px] px-[7px] py-0.5 font-mono text-[11px]",
                  isInstructor ? "bg-action-soft text-action" : "bg-surface text-accent",
                )}
              >
                {role || "-"}
              </span>
            </div>
          )}

          <div className={rail ? undefined : "mt-3.5"}>
            <Button
              variant="ghostDanger"
              size={rail ? "icon" : "sm"}
              block={!rail}
              title="Keluar"
              aria-label="Keluar"
              onClick={() => {
                closeMobileSidebarIfNeeded();
                logout();
              }}
            >
              <svg viewBox="0 0 16 16" width="15" height="15" fill="none" aria-hidden="true">
                <path
                  d="M6 2.5H4a1.5 1.5 0 0 0-1.5 1.5v8A1.5 1.5 0 0 0 4 13.5h2M10.5 11 14 8l-3.5-3M14 8H6"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              {!rail && <span>Keluar</span>}
            </Button>
          </div>
        </div>
      </aside>

      <main className="h-[calc(100dvh-61px)] min-h-0 w-full min-w-0 flex-1 overflow-hidden py-[18px] pl-[18px] max-[480px]:pl-3 tall:py-[clamp(22px,3vw,32px)] shell:h-full shell:pl-[clamp(24px,3.5vw,52px)]">
        {isInstructor ? <InstructorView /> : <ChatView />}
      </main>
    </div>
  );
}
