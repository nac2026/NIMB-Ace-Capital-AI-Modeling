"use client";
// TanStack Query provider — one client for the whole app. staleTime 60s so
// switching tabs doesn't re-fetch immediately; refetch-on-focus is enabled so
// the dashboard freshens when the user returns to the window.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60_000,
            refetchOnWindowFocus: true,
            retry: 1,
          },
        },
      }),
  );
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
