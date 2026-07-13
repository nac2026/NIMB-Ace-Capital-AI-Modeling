"use client";

const SUGGESTIONS = [
  "Which banks are being accumulated this week?",
  "Summarize today's market-moving news",
  "Compare NABIL vs NICA conviction",
  "Any manipulation patterns in hydropower?",
  "Which hydropower scrips look overvalued?",
  "Show the top conviction longs across all sectors",
];

export function Suggestions({ onPick }: { onPick: (q: string) => void }) {
  return (
    <div className="space-y-10 text-center">
      {/* Heading */}
      <div className="space-y-3">
        <div className="flex justify-center">
          <div
            className="flex h-12 w-12 items-center justify-center rounded-2xl"
            style={{ background: "color-mix(in oklab, var(--accent) 18%, var(--panel-3))", color: "var(--accent)" }}
          >
            <span className="text-[20px] font-bold" style={{ fontFamily: "var(--font-display)" }}>N</span>
          </div>
        </div>
        <div>
          <h1 className="serif" style={{ fontSize: 28, fontWeight: 600, letterSpacing: "-.01em" }}>
            Research Copilot
          </h1>
          <p className="mt-1.5 text-[14px] text-fg-muted">
            Cited · unbiased · NEPSE-aware — ask about any scrip, sector flow, broker behaviour, or news impact
          </p>
        </div>
      </div>

      {/* Suggestion cards */}
      <div className="grid grid-cols-2 gap-2.5 text-left sm:grid-cols-3">
        {SUGGESTIONS.map((q) => (
          <button
            key={q}
            onClick={() => onPick(q)}
            className="group rounded-2xl px-4 py-3.5 text-left text-[13px] font-medium text-fg-muted transition-all duration-200 hover:-translate-y-0.5 hover:text-fg"
            style={{
              background: "var(--panel-2)",
              border: "1px solid var(--line-soft)",
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLButtonElement).style.borderColor = "color-mix(in oklab, var(--accent) 40%, transparent)";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--line-soft)";
            }}
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}
