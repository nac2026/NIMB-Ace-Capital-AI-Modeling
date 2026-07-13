"use client";

import { usePathname, useSearchParams } from "next/navigation";
import { useMemo } from "react";
import type { PageContext } from "./api";

// Derives PageContext from the current URL so chat requests from the drawer
// carry "User is viewing NABIL" style hints. Agent appends these to its
// system prompt — returning null short-circuits that prepend on neutral pages.
export function usePageContext(): PageContext | null {
  const pathname = usePathname();
  const params = useSearchParams();

  return useMemo(() => {
    if (!pathname) return null;

    const scripMatch = pathname.match(/^\/scrip\/([^\/]+)/);
    if (scripMatch) {
      return { current_scrip: decodeURIComponent(scripMatch[1]).toUpperCase() };
    }

    if (pathname.startsWith("/compare")) {
      const raw = params.get("scrips");
      if (!raw) return null;
      const scrips = raw
        .split(",")
        .map((s) => s.trim().toUpperCase())
        .filter(Boolean);
      return scrips.length > 0 ? { current_scrips: scrips } : null;
    }

    const screenMatch = pathname.match(/^\/screen\/([^\/]+)/);
    if (screenMatch) {
      return { current_screen: screenMatch[1] };
    }

    return null;
  }, [pathname, params]);
}
