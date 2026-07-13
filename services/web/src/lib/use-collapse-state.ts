"use client";

import { useCallback, useEffect, useState } from "react";

// Boolean state backed by localStorage. Defers reading until after mount so
// the first SSR paint matches the client, then swaps in the stored value.
export function useCollapseState(key: string, initial = false): [boolean, (next: boolean | ((p: boolean) => boolean)) => void, boolean] {
  const [value, setValue] = useState(initial);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(key);
      if (raw !== null) setValue(raw === "1");
    } catch {}
    setHydrated(true);
  }, [key]);

  const set = useCallback((next: boolean | ((p: boolean) => boolean)) => {
    setValue((prev) => {
      const v = typeof next === "function" ? (next as (p: boolean) => boolean)(prev) : next;
      try { localStorage.setItem(key, v ? "1" : "0"); } catch {}
      return v;
    });
  }, [key]);

  return [value, set, hydrated];
}
