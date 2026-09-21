import { useSyncExternalStore } from "react";

// Membaca media query sebagai state React. Dipakai untuk hal yang hanya
// berlaku di desktop dan tidak cukup ditangani lewat prefix `shell:`
// (misalnya: mode rail pada sidebar).
export function useMediaQuery(query) {
  return useSyncExternalStore(
    (onChange) => {
      const mql = window.matchMedia(query);
      mql.addEventListener("change", onChange);
      return () => mql.removeEventListener("change", onChange);
    },
    () => window.matchMedia(query).matches,
    () => false,
  );
}
