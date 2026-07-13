"use client";

// 8px stacked bar showing green/amber/red distribution per analysis.

export function FlagDistributionBar({
  green,
  amber,
  red,
  unknown = 0,
  height = 8,
}: {
  green: number;
  amber: number;
  red: number;
  unknown?: number;
  height?: number;
}) {
  const total = green + amber + red + unknown;
  if (total === 0) {
    return (
      <div
        className="rounded-full"
        style={{ height, background: "var(--bg-hover)" }}
      />
    );
  }
  const segments: Array<{ key: string; n: number; bg: string }> = [
    { key: "g", n: green,   bg: "var(--ok)"   },
    { key: "a", n: amber,   bg: "var(--warn)" },
    { key: "r", n: red,     bg: "var(--err)"  },
    { key: "u", n: unknown, bg: "var(--fg-dim)" },
  ].filter(s => s.n > 0);

  return (
    <div className="flex w-full overflow-hidden rounded-full" style={{ height }}>
      {segments.map((s) => (
        <div
          key={s.key}
          style={{
            width: `${(s.n / total) * 100}%`,
            background: s.bg,
            minWidth: 2,
          }}
        />
      ))}
    </div>
  );
}
