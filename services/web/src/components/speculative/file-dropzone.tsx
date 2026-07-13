"use client";

import { useCallback, useState } from "react";
import { Upload, FileSpreadsheet, X } from "lucide-react";

export function FileDropzone({
  onFile,
  disabled = false,
}: {
  onFile: (file: File | null) => void;
  disabled?: boolean;
}) {
  const [isDragging, setIsDragging] = useState(false);
  const [picked, setPicked] = useState<File | null>(null);

  const accept = useCallback((file: File | null) => {
    if (!file) { setPicked(null); onFile(null); return; }
    const ok = /\.(csv|xlsx|xls|pdf|docx|doc|txt)$/i.test(file.name);
    if (!ok) {
      alert("Upload a ticker list (.csv, .xlsx) or a written research report (.pdf, .docx).");
      return;
    }
    setPicked(file);
    onFile(file);
  }, [onFile]);

  if (picked) {
    return (
      <div
        className="flex items-center justify-between rounded-xl border bg-bg-panel p-4"
        style={{ borderColor: "var(--brand)", borderWidth: 1.5 }}
      >
        <div className="flex items-center gap-3 min-w-0">
          <div
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg"
            style={{ background: "var(--brand-soft)", color: "var(--brand)" }}
          >
            <FileSpreadsheet className="h-5 w-5" strokeWidth={1.75} />
          </div>
          <div className="min-w-0">
            <div className="truncate text-[13.5px] font-medium text-fg">{picked.name}</div>
            <div className="mt-0.5 text-[11.5px] text-fg-muted num">{(picked.size / 1024).toFixed(1)} KB</div>
          </div>
        </div>
        <button
          onClick={() => accept(null)}
          disabled={disabled}
          className="flex h-8 w-8 items-center justify-center rounded-md text-fg-muted transition-colors hover:bg-bg-hover hover:text-fg disabled:opacity-40"
          title="Remove file"
        >
          <X className="h-4 w-4" strokeWidth={2} />
        </button>
      </div>
    );
  }

  return (
    <label
      onDragOver={(e) => { e.preventDefault(); if (!disabled) setIsDragging(true); }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setIsDragging(false);
        if (disabled) return;
        accept(e.dataTransfer.files[0] || null);
      }}
      className="flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-12 text-center transition-colors"
      style={{
        borderColor: isDragging ? "var(--brand)" : "var(--border)",
        background: isDragging ? "var(--brand-soft)" : "var(--bg-panel)",
      }}
    >
      <input
        type="file"
        accept=".csv,.xlsx,.xls,.pdf,.docx,.doc,.txt"
        className="hidden"
        disabled={disabled}
        onChange={(e) => accept(e.target.files?.[0] || null)}
      />
      <div
        className="flex h-12 w-12 items-center justify-center rounded-xl"
        style={{ background: "var(--brand-soft)", color: "var(--brand)" }}
      >
        <Upload className="h-6 w-6" strokeWidth={1.75} />
      </div>
      <div className="mt-4 text-[14px] font-medium text-fg">
        Drag and drop, or click to choose
      </div>
      <div className="mt-1.5 text-[12px] text-fg-muted">
        CSV or Excel · column named <code className="rounded bg-bg-subtle px-1 py-0.5 font-mono text-[11px]">scrip</code> or <code className="rounded bg-bg-subtle px-1 py-0.5 font-mono text-[11px]">ticker</code>
      </div>
    </label>
  );
}
