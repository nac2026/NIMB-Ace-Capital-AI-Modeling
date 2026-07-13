"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { BarChart2, History, X } from "lucide-react";
import { VisualBlock, InlineChart } from "./message-bubble";

type VisualPanelProps = {
  visuals: VisualBlock[];
  width: number;
  isHistorical?: boolean;
  onClose: () => void;
};

export function VisualPanel({ visuals, width, isHistorical, onClose }: VisualPanelProps) {
  return (
    <div
      className="shrink-0 flex flex-col overflow-hidden panel-enter"
      style={{
        width: `${width}px`,
        minWidth: `${width}px`,
        borderLeft: "1px solid var(--border-subtle)",
        background: "var(--bg)",
      }}
    >
      {/* Header */}
      <div
        className="flex items-center gap-2 px-4 py-3 shrink-0"
        style={{ borderBottom: "1px solid var(--border-subtle)", background: "var(--bg-panel)" }}
      >
        <BarChart2 className="h-3.5 w-3.5 text-fg-dim" />
        <span className="text-[11px] font-semibold uppercase tracking-widest text-fg-dim">
          Charts &amp; Data
        </span>

        {isHistorical && (
          <span
            className="flex items-center gap-1 text-[10px] rounded-full px-2 py-0.5"
            style={{
              background: "var(--bg-subtle)",
              color: "var(--fg-dim)",
              border: "1px solid var(--border-subtle)",
            }}
          >
            <History size={9} />
            Historical
          </span>
        )}

        {/* Close button */}
        <button
          onClick={onClose}
          className="ml-auto flex h-6 w-6 items-center justify-center rounded-md transition-colors hover:bg-bg-hover"
          style={{ color: "var(--fg-dim)" }}
          title="Close panel"
        >
          <X size={14} />
        </button>
      </div>

      {/* Visuals — vertically scrollable */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {visuals.map((v, i) =>
          v.type === "chart" ? (
            <InlineChart key={i} raw={v.raw} />
          ) : (
            <div
              key={i}
              className="rounded-xl overflow-hidden"
              style={{
                background: "var(--bg-panel)",
                border: "1px solid var(--border-subtle)",
                boxShadow: "var(--shadow-sm)",
              }}
            >
              {/* Horizontally scrollable so wide tables aren't squashed */}
              <div className="overflow-x-auto">
                <div className="markdown text-[13px] px-3 py-2 panel-table">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{v.raw}</ReactMarkdown>
                </div>
              </div>
            </div>
          )
        )}
      </div>
    </div>
  );
}
