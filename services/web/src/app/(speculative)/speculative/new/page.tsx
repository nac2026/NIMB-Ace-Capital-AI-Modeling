"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ChevronLeft, Loader2, Play, AlertTriangle, Download } from "lucide-react";
import { api, type SpeculativeUploadResponse } from "@/lib/api";
import { FileDropzone } from "@/components/speculative/file-dropzone";

export default function NewSpeculativeAnalysisPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [notes, setNotes] = useState("");
  const [uploadResp, setUploadResp] = useState<SpeculativeUploadResponse | null>(null);
  const [uploading, setUploading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleUpload() {
    if (!file) return;
    setError(null);
    setUploading(true);
    try {
      const resp = await api.speculative.upload(file, title.trim() || undefined, notes.trim() || undefined);
      setUploadResp(resp);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setUploading(false);
    }
  }

  async function handleAnalyze() {
    if (!uploadResp) return;
    setError(null);
    setAnalyzing(true);
    try {
      await api.speculative.analyze(uploadResp.session_id);
      router.push(`/speculative/analysis/${uploadResp.session_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setAnalyzing(false);
    }
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-[820px] px-8 py-10">
        <Link
          href="/speculative"
          className="inline-flex items-center gap-1 text-[12px] text-fg-muted transition-colors hover:text-fg"
        >
          <ChevronLeft className="h-3.5 w-3.5" strokeWidth={1.75} />
          Back to all analyses
        </Link>

        <h1 className="mt-4 text-[26px] font-semibold tracking-tight text-fg">
          New speculative analysis
        </h1>
        <p className="mt-1.5 text-[13.5px] text-fg-muted">
          Upload a <span className="text-fg">written research report</span> (.pdf / .docx) to validate its thesis
          claim-by-claim and get an independent RED/AMBER/GREEN verdict — or a <span className="text-fg">ticker
          shortlist</span> (.csv / .xlsx) to screen each name through the rule engine.
        </p>

        {!uploadResp && (
          <div className="mt-8 space-y-5">
            <FileDropzone onFile={setFile} disabled={uploading} />

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div>
                <label className="label">Title (optional)</label>
                <input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="e.g. Mid-May watchlist"
                  disabled={uploading}
                  className="mt-1.5 w-full rounded-md border bg-bg-panel px-3 py-2 text-[13px] text-fg outline-none focus:border-brand"
                  style={{ borderColor: "var(--border)" }}
                />
              </div>
              <div>
                <label className="label">Notes (optional)</label>
                <input
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Why this list — analyst thesis, etc."
                  disabled={uploading}
                  className="mt-1.5 w-full rounded-md border bg-bg-panel px-3 py-2 text-[13px] text-fg outline-none focus:border-brand"
                  style={{ borderColor: "var(--border)" }}
                />
              </div>
            </div>

            <div className="flex items-center justify-between gap-3 pt-1">
              <a
                href={api.speculative.sampleTemplateUrl()}
                download
                className="inline-flex items-center gap-1.5 text-[12px] text-fg-muted transition-colors hover:text-fg"
              >
                <Download className="h-3.5 w-3.5" strokeWidth={1.75} />
                Download CSV template
              </a>
              <button
                onClick={handleUpload}
                disabled={!file || uploading}
                className="inline-flex items-center gap-1.5 rounded-md px-5 py-2.5 text-[13px] font-semibold transition-opacity disabled:opacity-40 hover:opacity-90"
                style={{ background: "var(--brand)", color: "#ffffff" }}
              >
                {uploading ? (
                  <><Loader2 className="h-4 w-4 animate-spin" strokeWidth={2.25} />Uploading…</>
                ) : (
                  <>Upload and parse</>
                )}
              </button>
            </div>
          </div>
        )}

        {uploadResp && (
          <div className="mt-8 space-y-5">
            <div className="panel p-5">
              <div className="text-[11px] uppercase tracking-widest text-fg-dim">
                {uploadResp.mode === "review" ? "Report uploaded" : "Parsed"}
              </div>
              <div className="mt-1 text-[16px] font-semibold text-fg">{uploadResp.title}</div>
              {uploadResp.mode === "review" ? (
                <div className="mt-2 text-[12.5px] text-fg-muted">
                  Written report received. Running the review will extract its thesis &amp; claims, verify each
                  against our data, assess every aspect (incl. floor-sheet manipulation), and issue a verdict.
                </div>
              ) : (
              <div className="mt-2 flex items-center gap-4 text-[12.5px] text-fg-muted">
                <span><span className="num font-medium text-fg">{uploadResp.tickers.length}</span> known</span>
                {uploadResp.unknown_tickers.length > 0 && (
                  <span style={{ color: "var(--err)" }}>
                    <span className="num font-medium">{uploadResp.unknown_tickers.length}</span> unknown (will be skipped)
                  </span>
                )}
              </div>
              )}
              <div className="mt-4 flex flex-wrap gap-1.5">
                {uploadResp.tickers.map(t => (
                  <span
                    key={t}
                    className="rounded-md px-2 py-1 text-[11.5px] font-mono num font-semibold"
                    style={{ background: "var(--brand-soft)", color: "var(--brand)" }}
                  >
                    {t}
                  </span>
                ))}
                {uploadResp.unknown_tickers.map(t => (
                  <span
                    key={t}
                    className="rounded-md px-2 py-1 text-[11.5px] font-mono num font-semibold line-through"
                    style={{ background: "var(--bg-hover)", color: "var(--err)" }}
                    title="Not in active universe — will be skipped"
                  >
                    {t}
                  </span>
                ))}
              </div>
            </div>

            <div className="flex items-center justify-between gap-3">
              <Link
                href="/speculative"
                className="inline-flex items-center gap-1 text-[12px] text-fg-muted transition-colors hover:text-fg"
              >
                <ChevronLeft className="h-3.5 w-3.5" strokeWidth={1.75} />
                Cancel
              </Link>
              <button
                onClick={handleAnalyze}
                disabled={analyzing || (uploadResp.mode !== "review" && uploadResp.tickers.length === 0)}
                className="inline-flex items-center gap-1.5 rounded-md px-5 py-2.5 text-[13px] font-semibold transition-opacity disabled:opacity-40 hover:opacity-90"
                style={{ background: "var(--brand)", color: "#ffffff" }}
              >
                {analyzing ? (
                  <><Loader2 className="h-4 w-4 animate-spin" strokeWidth={2.25} />Running analysis…</>
                ) : (
                  <><Play className="h-4 w-4" strokeWidth={2.25} />Run analysis</>
                )}
              </button>
            </div>
            <p className="text-[11.5px] text-fg-dim text-center">
              {uploadResp.mode === "review"
                ? "Report review runs multiple AI passes — typically 30–90 seconds."
                : "Typically completes in 3–8 seconds for ≤20 tickers."}
            </p>
          </div>
        )}

        {error && (
          <div
            className="mt-6 flex items-start gap-2.5 rounded-md p-3 text-[12.5px]"
            style={{ background: "var(--bg-subtle)", color: "var(--err)", border: "1px solid var(--err)" }}
          >
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" strokeWidth={1.75} />
            <span>{error}</span>
          </div>
        )}
      </div>
    </div>
  );
}
