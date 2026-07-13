"use client";
// Live backend-reachability indicator in the sidebar footer. Polls /ready
// every 20s so the user sees if the orchestrator goes down.

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

export function HealthDot() {
  const { data, isError } = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 20_000,
    staleTime: 10_000,
  });

  const ok = !!data && !isError && data.status === "ok";
  return (
    <div className="flex items-center gap-2">
      <span
        className={cn("statusdot", ok ? "bg-ok" : "bg-err")}
        title={ok ? "Backend reachable" : "Backend unreachable"}
      />
      <span className="label">{ok ? "Online" : "Offline"}</span>
    </div>
  );
}
