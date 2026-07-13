"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { User, BarChart2, Sparkles } from "lucide-react";
import {
  ResponsiveContainer,
  LineChart, BarChart,
  Line, Bar,
  XAxis, YAxis,
  CartesianGrid, Tooltip, Legend,
} from "recharts";

export type Message = {
  role: "user" | "assistant";
  content: string;
  meta?: unknown;
};

export type VisualBlock =
  | { type: "chart"; raw: string }
  | { type: "table"; raw: string };

const COLORS = ["#1c1917", "#b45309", "#065f46", "#1e3a8a", "#6d28d9", "#9f1239"];

type ChartConfig = {
  type: "line" | "bar";
  title?: string;
  xKey: string;
  yLabel?: string;
  series: { key: string; label?: string }[];
  data: Record<string, string | number>[];
};

export function InlineChart({ raw }: { raw: string }) {
  let cfg: ChartConfig;
  try {
    cfg = JSON.parse(raw) as ChartConfig;
  } catch {
    return (
      <pre className="mono mt-2 overflow-x-auto rounded-xl bg-bg-subtle p-3 text-[12px] text-fg-muted">
        {raw}
      </pre>
    );
  }

  const { type, title, xKey, yLabel, series, data } = cfg;
  const isMulti = series.length > 1;
  const ChartComponent = type === "bar" ? BarChart : LineChart;

  return (
    <div
      className="my-3 rounded-2xl p-4"
      style={{
        background: "var(--bg-panel)",
        border: "1px solid var(--border-subtle)",
        boxShadow: "var(--shadow-sm)",
      }}
    >
      {title && <p className="mb-4 text-[13px] font-semibold text-fg">{title}</p>}
      <ResponsiveContainer width="100%" height={220}>
        <ChartComponent data={data} margin={{ top: 4, right: 12, left: -12, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" vertical={false} />
          <XAxis dataKey={xKey} tick={{ fontSize: 11, fill: "var(--fg-dim)" }} tickLine={false} axisLine={{ stroke: "var(--border-subtle)" }} />
          <YAxis
            tick={{ fontSize: 11, fill: "var(--fg-dim)" }}
            tickLine={false}
            axisLine={false}
            label={yLabel ? { value: yLabel, angle: -90, position: "insideLeft", fontSize: 11, fill: "var(--fg-muted)", dx: -4 } : undefined}
          />
          <Tooltip
            contentStyle={{ background: "var(--bg-panel)", border: "1px solid var(--border-subtle)", borderRadius: 10, fontSize: 12, boxShadow: "var(--shadow-md)", padding: "8px 12px" }}
            itemStyle={{ color: "var(--fg)", fontWeight: 500 }}
            labelStyle={{ color: "var(--fg-muted)", fontWeight: 600, marginBottom: 4 }}
            cursor={{ fill: "var(--bg-hover)", opacity: 0.5 }}
          />
          {isMulti && <Legend wrapperStyle={{ fontSize: 12, color: "var(--fg-muted)", paddingTop: 8 }} />}
          {series.map((s, i) =>
            type === "bar" ? (
              <Bar key={s.key} dataKey={s.key} name={s.label ?? s.key} fill={COLORS[i % COLORS.length]} radius={[4, 4, 0, 0]} maxBarSize={40} />
            ) : (
              <Line key={s.key} type="monotone" dataKey={s.key} name={s.label ?? s.key} stroke={COLORS[i % COLORS.length]} strokeWidth={2} dot={{ r: 3, fill: COLORS[i % COLORS.length], strokeWidth: 0 }} activeDot={{ r: 5, strokeWidth: 0 }} />
            ),
          )}
        </ChartComponent>
      </ResponsiveContainer>
    </div>
  );
}

export function extractVisuals(content: string): { text: string; visuals: VisualBlock[] } {
  const visuals: VisualBlock[] = [];

  let text = content.replace(/```chart\n([\s\S]*?)```/g, (_, raw) => {
    visuals.push({ type: "chart", raw: raw.trim() });
    return "";
  });

  text = text.replace(/```chart\n[\s\S]*$/, "");

  const lines = text.split("\n");
  const textLines: string[] = [];
  let buf: string[] = [];

  const flushBuf = () => {
    if (buf.length >= 2) {
      visuals.push({ type: "table", raw: buf.join("\n") });
      textLines.push("");
    } else {
      textLines.push(...buf);
    }
    buf = [];
  };

  for (const line of lines) {
    if (line.trimStart().startsWith("|")) {
      buf.push(line);
    } else {
      flushBuf();
      textLines.push(line);
    }
  }
  flushBuf();

  text = textLines.join("\n").replace(/\n{3,}/g, "\n\n").trim();
  return { text, visuals };
}

// ── Avatars ────────────────────────────────────────────────────────────
function AgentAvatar() {
  return (
    <div
      className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg mt-0.5"
      style={{ background: "color-mix(in oklab, var(--accent) 18%, var(--panel-3))", color: "var(--accent)" }}
    >
      <Sparkles className="h-4 w-4" strokeWidth={2.2} />
    </div>
  );
}

function UserAvatar() {
  return (
    <div
      className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg mt-0.5"
      style={{ background: "var(--panel-2)", border: "1px solid var(--line)" }}
    >
      <User className="h-4 w-4 text-fg-muted" />
    </div>
  );
}

// ── Message bubbles ────────────────────────────────────────────────────
type MessageBubbleProps = {
  message: Message;
  // visualsActive = panel is open AND showing this message's snapshot
  visualsActive?: boolean;
  onShowVisuals?: () => void;
};

export function MessageBubble({ message, visualsActive, onShowVisuals }: MessageBubbleProps) {
  if (message.role === "user") {
    return (
      <div className="msg-enter flex justify-end items-start gap-2.5 py-1">
        <div
          className="max-w-[72%] rounded-2xl rounded-tr-md px-4 py-2.5 text-[14px] leading-relaxed whitespace-pre-wrap"
          style={{
            background: "color-mix(in oklab, var(--accent) 16%, var(--panel-2))",
            border: "1px solid color-mix(in oklab, var(--accent) 30%, transparent)",
            color: "var(--ink)",
          }}
        >
          {message.content}
        </div>
        <UserAvatar />
      </div>
    );
  }

  const { text, visuals: msgVisuals } = extractVisuals(message.content);
  const hasVisuals = msgVisuals.length > 0;

  return (
    <div className="msg-enter flex justify-start items-start gap-2.5 py-1">
      <AgentAvatar />
      <div className="min-w-0 flex-1 rounded-2xl rounded-tl-sm px-4 py-3"
           style={{ background: "var(--panel-3)", border: "1px solid var(--line)" }}>
        <div className="markdown">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              code({ className, children }) {
                const lang = /language-(\w+)/.exec(className ?? "")?.[1];
                if (lang === "chart") return null;
                return <code className={className}>{children}</code>;
              },
            }}
          >
            {text}
          </ReactMarkdown>
        </div>

        {/* Charts & Data button — opens / closes the right panel for this snapshot */}
        {hasVisuals && (
          <button
            onClick={onShowVisuals}
            className="mt-3 inline-flex items-center gap-2 rounded-xl text-[12px] font-semibold transition-all cursor-pointer"
            style={
              visualsActive
                ? { background: "var(--fg)", color: "var(--bg)", padding: "6px 14px" }
                : {
                    background: "var(--bg-panel)",
                    color: "var(--fg)",
                    padding: "6px 14px",
                    border: "1px solid var(--border)",
                    boxShadow: "var(--shadow-sm)",
                  }
            }
          >
            <BarChart2 size={13} />
            <span>Charts &amp; Data</span>
            {/* Count badge */}
            <span
              className="rounded-full text-[10px] px-1.5 py-0.5 min-w-[18px] text-center tabular-nums font-bold"
              style={
                visualsActive
                  ? { background: "rgba(255,255,255,0.18)", color: "var(--bg)" }
                  : { background: "var(--bg-subtle)", color: "var(--fg-muted)" }
              }
            >
              {msgVisuals.length}
            </span>
          </button>
        )}
      </div>
    </div>
  );
}
