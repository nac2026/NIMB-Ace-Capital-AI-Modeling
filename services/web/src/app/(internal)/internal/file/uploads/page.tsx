"use client";

// Internal file uploads → MinIO. Users pick a category (folder), optionally a
// date (defaults to today), drop a file, and it lands at
// {category}/{date}/{filename} in object storage. The trade-book category is the
// source the surveillance scan reads. Browse is grouped by date to match the
// "date folder → files" mental model, though storage is category-first.

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  UploadCloud, Loader2, CheckCircle2, AlertTriangle, Download, Trash2,
  FolderClock, ShieldAlert, FileText,
} from "lucide-react";
import {
  api,
  type InternalUploadCategory,
  type InternalUploadItem,
} from "@/lib/api";
import { FileDropzone } from "@/components/speculative/file-dropzone";

function todayISO(): string {
  // Local calendar date as YYYY-MM-DD (matches the server's date.today()).
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

function fmtSize(bytes: number): string {
  if (!bytes) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const CATEGORY_LABEL: Record<string, string> = {
  "internal-trade-data": "Internal trade data",
  "strategic-plans": "Strategic plans",
  "goals-and-strategy": "Goals & strategy",
};

function labelFor(cat: string): string {
  return CATEGORY_LABEL[cat] ?? cat;
}

export default function InternalUploadsPage() {
  const [categories, setCategories] = useState<InternalUploadCategory[]>([]);
  const [category, setCategory] = useState<string>("internal-trade-data");
  const [date, setDate] = useState<string>(todayISO());
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [items, setItems] = useState<InternalUploadItem[]>([]);
  const [loadingList, setLoadingList] = useState(false);

  const currentCat = useMemo(
    () => categories.find((c) => c.category === category),
    [categories, category],
  );
  const acceptStr = currentCat?.extensions.join(",") ?? ".xlsx";

  // Load categories once.
  useEffect(() => {
    api.internal.uploads
      .categories()
      .then((cats) => {
        setCategories(cats);
        if (cats.length && !cats.some((c) => c.category === category)) {
          setCategory(cats[0].category);
        }
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refreshList = useCallback(async () => {
    setLoadingList(true);
    try {
      const list = await api.internal.uploads.list(category);
      setItems(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingList(false);
    }
  }, [category]);

  // Reload the file list whenever the category changes.
  useEffect(() => {
    refreshList();
  }, [refreshList]);

  async function handleUpload() {
    if (!file) return;
    setError(null);
    setNotice(null);
    setUploading(true);
    try {
      const res = await api.internal.uploads.upload(file, category, date || undefined);
      setNotice(
        `${res.replaced ? "Replaced" : "Uploaded"} ${res.filename} → ${labelFor(res.category)} · ${res.date}`,
      );
      setFile(null);
      await refreshList();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(key: string, filename: string) {
    if (!window.confirm(`Delete ${filename}? This removes it from object storage.`)) return;
    setError(null);
    setNotice(null);
    try {
      await api.internal.uploads.remove(key);
      setNotice(`Deleted ${filename}`);
      await refreshList();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  // Group the flat list into date buckets, newest date first.
  const byDate = useMemo(() => {
    const groups = new Map<string, InternalUploadItem[]>();
    for (const it of items) {
      const arr = groups.get(it.date) ?? [];
      arr.push(it);
      groups.set(it.date, arr);
    }
    return [...groups.entries()].sort((a, b) => (a[0] < b[0] ? 1 : -1));
  }, [items]);

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-[900px] px-8 py-10">
        <div className="flex items-center gap-2 text-[12px] text-fg-muted">
          <UploadCloud className="h-3.5 w-3.5" strokeWidth={1.75} />
          Internal files
        </div>
        <h1 className="mt-2 text-[26px] font-semibold tracking-tight text-fg">
          File uploads
        </h1>
        <p className="mt-1.5 text-[13.5px] text-fg-muted">
          Upload business files into secure object storage instead of a local folder.
          The <span className="text-fg">Internal trade data</span> folder is the source the{" "}
          <span className="inline-flex items-center gap-1 text-fg"><ShieldAlert className="h-3.5 w-3.5" strokeWidth={1.75} />Trade Surveillance</span>{" "}
          scan reads — upload today&apos;s trade book here, then hit{" "}
          <span className="text-fg">&ldquo;Load new trade-book data&rdquo;</span> on the surveillance board.
        </p>

        {/* Upload panel */}
        <div className="panel mt-8 rounded-xl border border-border-subtle bg-bg-panel p-5">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="label mb-1.5 block" htmlFor="category">Folder / category</label>
              <select
                id="category"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                disabled={uploading}
                className="w-full rounded-lg border border-border bg-bg-subtle px-3 py-2 text-[13.5px] text-fg outline-none transition-colors focus:border-[var(--brand)]"
              >
                {categories.map((c) => (
                  <option key={c.category} value={c.category}>{labelFor(c.category)}</option>
                ))}
              </select>
              <div className="mt-1 text-[11.5px] text-fg-muted">
                Allowed: {currentCat?.extensions.join(", ") ?? "…"}
              </div>
            </div>
            <div>
              <label className="label mb-1.5 block" htmlFor="date">Date folder</label>
              <input
                id="date"
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                disabled={uploading}
                className="w-full rounded-lg border border-border bg-bg-subtle px-3 py-2 text-[13.5px] text-fg outline-none transition-colors focus:border-[var(--brand)]"
              />
              <div className="mt-1 text-[11.5px] text-fg-muted">Defaults to today. No need to create folders.</div>
            </div>
          </div>

          <div className="mt-4">
            <FileDropzone
              onFile={setFile}
              disabled={uploading}
              accept={acceptStr}
              hint={<>Allowed for <span className="text-fg">{labelFor(category)}</span>: {currentCat?.extensions.join(", ") ?? "…"}</>}
            />
          </div>

          <div className="mt-4 flex items-center justify-between gap-3">
            <div className="min-h-[20px] text-[12.5px]">
              {error && (
                <span className="inline-flex items-center gap-1.5" style={{ color: "var(--err)" }}>
                  <AlertTriangle className="h-3.5 w-3.5" strokeWidth={1.75} />{error}
                </span>
              )}
              {!error && notice && (
                <span className="inline-flex items-center gap-1.5" style={{ color: "var(--ok, var(--brand))" }}>
                  <CheckCircle2 className="h-3.5 w-3.5" strokeWidth={1.75} />{notice}
                </span>
              )}
            </div>
            <button
              onClick={handleUpload}
              disabled={!file || uploading}
              className="inline-flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-medium text-black transition-opacity disabled:opacity-40"
              style={{ background: "var(--brand)" }}
            >
              {uploading ? <Loader2 className="h-4 w-4 animate-spin" strokeWidth={2} /> : <UploadCloud className="h-4 w-4" strokeWidth={2} />}
              {uploading ? "Uploading…" : "Upload"}
            </button>
          </div>
        </div>

        {/* Browse: date-grouped list for the selected category */}
        <div className="mt-9 flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-[15px] font-semibold text-fg">
            <FolderClock className="h-4 w-4" strokeWidth={1.75} />
            {labelFor(category)}
          </h2>
          <button
            onClick={refreshList}
            className="text-[12px] text-fg-muted transition-colors hover:text-fg"
          >
            {loadingList ? "Refreshing…" : "Refresh"}
          </button>
        </div>

        {byDate.length === 0 && !loadingList && (
          <div className="mt-4 rounded-xl border border-dashed border-border p-8 text-center text-[13px] text-fg-muted">
            No files uploaded in this folder yet.
          </div>
        )}

        <div className="mt-4 space-y-6">
          {byDate.map(([d, files]) => (
            <div key={d}>
              <div className="mb-2 flex items-center gap-2 text-[12px] font-medium text-fg-muted">
                <span className="num">{d}</span>
                <span className="text-fg-dim">· {files.length} file{files.length === 1 ? "" : "s"}</span>
              </div>
              <div className="overflow-hidden rounded-xl border border-border-subtle">
                {files.map((it, i) => (
                  <div
                    key={it.key}
                    className={`flex items-center justify-between gap-3 px-4 py-2.5 ${i > 0 ? "border-t border-border-subtle" : ""}`}
                  >
                    <div className="flex min-w-0 items-center gap-3">
                      <FileText className="h-4 w-4 shrink-0 text-fg-muted" strokeWidth={1.75} />
                      <span className="truncate text-[13px] text-fg">{it.filename}</span>
                    </div>
                    <div className="flex shrink-0 items-center gap-4">
                      <span className="num text-[11.5px] text-fg-muted">{fmtSize(it.size)}</span>
                      <a
                        href={api.internal.uploads.downloadUrl(it.key)}
                        className="flex h-7 w-7 items-center justify-center rounded-md text-fg-muted transition-colors hover:bg-bg-hover hover:text-fg"
                        title="Download"
                      >
                        <Download className="h-3.5 w-3.5" strokeWidth={1.75} />
                      </a>
                      <button
                        onClick={() => handleDelete(it.key, it.filename)}
                        className="flex h-7 w-7 items-center justify-center rounded-md text-fg-muted transition-colors hover:bg-bg-hover"
                        style={{ ["--hover-err" as string]: "var(--err)" }}
                        title="Delete"
                      >
                        <Trash2 className="h-3.5 w-3.5" strokeWidth={1.75} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
