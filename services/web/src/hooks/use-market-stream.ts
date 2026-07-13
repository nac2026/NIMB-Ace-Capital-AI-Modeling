"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { api } from "@/lib/api";

export type LiveTick = {
  scrip: string;
  price: number;
  open: number | null;
  high: number | null;
  low: number | null;
  volume: number;
  turnover: number;
  change_abs: number | null;
  change_pct: number | null;
  prev_close: number | null;
  tick_at: string;
  source: string;
};

type StreamState = {
  prices: Map<string, LiveTick>;
  lastTickAt: number | null;   // Date.now() of most recent tick
  connected: boolean;
};

export function useMarketStream(scrips?: string[]) {
  const [state, setState] = useState<StreamState>({
    prices: new Map(),
    lastTickAt: null,
    connected: false,
  });

  // Batch incoming ticks — flush to state via requestAnimationFrame
  const pendingRef = useRef<LiveTick[]>([]);
  const rafRef = useRef<number | null>(null);

  const flush = useCallback(() => {
    rafRef.current = null;
    const batch = pendingRef.current;
    if (batch.length === 0) return;
    pendingRef.current = [];

    setState((prev) => {
      const next = new Map(prev.prices);
      let lastAt = prev.lastTickAt;
      for (const t of batch) {
        next.set(t.scrip, t);
        const ts = new Date(t.tick_at).getTime();
        if (lastAt === null || ts > lastAt) lastAt = ts;
      }
      return { prices: next, lastTickAt: lastAt, connected: prev.connected };
    });
  }, []);

  useEffect(() => {
    const scripsParam = scrips && scrips.length > 0 ? scrips.join(",") : undefined;
    const url = api.marketStreamUrl(scripsParam);
    const es = new EventSource(url);

    es.onopen = () =>
      setState((prev) => ({ ...prev, connected: true }));

    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data as string);
        if (data.type === "ping") return;
        pendingRef.current.push(data as LiveTick);
        if (rafRef.current === null) {
          rafRef.current = requestAnimationFrame(flush);
        }
      } catch {
        // malformed — skip
      }
    };

    es.onerror = () =>
      setState((prev) => ({ ...prev, connected: false }));

    return () => {
      es.close();
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(scrips)]);

  const isStale =
    state.lastTickAt !== null && Date.now() - state.lastTickAt > 10_000;

  return { ...state, isStale };
}
