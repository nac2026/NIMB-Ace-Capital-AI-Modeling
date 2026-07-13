"use client";

import { memo } from "react";

type SparklineProps = {
  points: number[];   // price values, oldest first
  positive: boolean;  // true = green, false = red
  width?: number;
  height?: number;
};

export const Sparkline = memo(function Sparkline({
  points,
  positive,
  width = 64,
  height = 24,
}: SparklineProps) {
  if (points.length < 2) {
    return <div style={{ width, height }} />;
  }

  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;

  const xs = points.map((_, i) => (i / (points.length - 1)) * width);
  const ys = points.map((v) => height - ((v - min) / range) * (height - 2) - 1);

  const d = xs.map((x, i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${ys[i].toFixed(1)}`).join(" ");

  const color = positive ? "var(--ok)" : "var(--err)";

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      fill="none"
      aria-hidden
    >
      <path d={d} stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
});
