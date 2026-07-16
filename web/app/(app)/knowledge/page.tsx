"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { FileText, Loader2, Plus, Trash2 } from "lucide-react";
import { apiDelete, apiGet, apiUpload } from "@/lib/api";
import UploadDropzone from "@/components/UploadDropzone";
import PasteTextModal from "@/components/PasteTextModal";
import Spinner from "@/components/Spinner";

type KbDocumentStatus = "processing" | "ready" | "failed";

type KbDocument = {
  id: string;
  filename: string;
  type: string;
  chunkCount: number;
  status: KbDocumentStatus;
  createdAt: string;
};

const POLL_INTERVAL_MS = 3000;

function StatusPill({ status }: { status: KbDocumentStatus }) {
  const styles: Record<KbDocumentStatus, string> = {
    processing: "bg-amber-50 text-amber-700",
    ready: "bg-emerald-50 text-emerald-700",
    failed: "bg-red-50 text-red-700",
  };

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${styles[status]}`}
    >
      {status === "processing" && <Loader2 size={11} className="animate-spin" />}
      {status}
    </span>
  );
}

function formatDate(value: string): string {
  try {
    return new Date(value).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return value;
  }
}

export default function KnowledgePage() {
  const [documents, setDocuments] = useState<KbDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showPasteModal, setShowPasteModal] = useState(false);
  const [uploading, setUploading] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadDocuments = useCallback(async () => {
    try {
      const docs = await apiGet<KbDocument[]>("kb");
      setDocuments(docs);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load documents");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let ignore = false;

    async function run() {
      try {
        const docs = await apiGet<KbDocument[]>("kb");
        if (ignore) return;
        setDocuments(docs);
        setError(null);
      } catch (e) {
        if (ignore) return;
        setError(e instanceof Error ? e.message : "Failed to load documents");
      } finally {
        if (!ignore) setLoading(false);
      }
    }

    void run();

    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    const hasProcessing = documents.some((d) => d.status === "processing");

    if (hasProcessing && !pollRef.current) {
      pollRef.current = setInterval(() => {
        void loadDocuments();
      }, POLL_INTERVAL_MS);
    }

    if (!hasProcessing && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }

    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [documents, loadDocuments]);

  async function handleUploadFile(file: File) {
    setUploading(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const doc = await apiUpload<KbDocument>("kb/upload", formData);
      setDocuments((prev) => [doc, ...prev]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function handlePasteText(title: string, text: string) {
    const formData = new FormData();
    formData.append("title", title);
    formData.append("text", text);
    const doc = await apiUpload<KbDocument>("kb/upload", formData);
    setDocuments((prev) => [doc, ...prev]);
  }

  async function handleDelete(id: string) {
    const previous = documents;
    setDocuments((prev) => prev.filter((d) => d.id !== id));
    try {
      await apiDelete(`kb/${id}`);
    } catch (e) {
      setDocuments(previous);
      setError(e instanceof Error ? e.message : "Failed to delete document");
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight text-[var(--color-foreground)] sm:text-3xl">
            Knowledge
          </h1>
          <p className="mt-1 text-[15px] text-[var(--color-muted)]">
            Documents used to ground automated replies.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowPasteModal(true)}
          className="flex items-center gap-2 rounded-[var(--radius-sm)] bg-[var(--color-accent)] px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-[var(--color-accent-hover)]"
        >
          <Plus size={16} />
          Paste text
        </button>
      </div>

      <UploadDropzone onUpload={handleUploadFile} disabled={uploading} uploading={uploading} />

      {error && <p className="text-sm text-red-600">{error}</p>}

      {/* Phones/tablets: stacked rows, no sideways scrolling. */}
      <div className="rounded-[var(--radius-md)] border border-[var(--color-border)] bg-white shadow-[var(--shadow-card)] lg:hidden">
        {loading && (
          <div className="px-4 py-6 text-center text-[var(--color-muted)]">
            <span className="inline-flex items-center gap-2.5 text-sm">
              <Spinner size={16} className="text-[var(--color-accent)]" />
              Loading documents
            </span>
          </div>
        )}
        {!loading && documents.length === 0 && (
          <div className="px-4 py-6 text-center text-sm text-[var(--color-muted)]">
            No documents yet. Upload a file or paste text to get started.
          </div>
        )}
        {!loading && documents.length > 0 && (
          <ul className="divide-y divide-[var(--color-border)]">
            {documents.map((doc) => (
              <li key={doc.id} className="flex items-start gap-3 px-4 py-4">
                <FileText size={16} className="mt-0.5 shrink-0 text-[var(--color-muted)]" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="min-w-0 truncate text-sm font-medium text-[var(--color-foreground)]">
                      {doc.filename}
                    </span>
                    <StatusPill status={doc.status} />
                  </div>
                  <p className="mt-1 text-[13px] text-[var(--color-muted)]">
                    {doc.type} · {doc.chunkCount} chunks · {formatDate(doc.createdAt)}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => handleDelete(doc.id)}
                  aria-label={`Delete ${doc.filename}`}
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[var(--radius-sm)] text-[var(--color-muted)] hover:bg-[var(--color-app-bg)] hover:text-red-600"
                >
                  <Trash2 size={15} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="hidden overflow-x-auto rounded-[var(--radius-md)] border border-[var(--color-border)] bg-white shadow-[var(--shadow-card)] lg:block">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead>
            <tr className="border-b border-[var(--color-border)] bg-[var(--color-app-bg)]/60 text-xs uppercase tracking-wide text-[var(--color-muted)]">
              <th className="px-5 py-3 font-medium">Name</th>
              <th className="px-5 py-3 font-medium">Type</th>
              <th className="px-5 py-3 font-medium">Chunks</th>
              <th className="px-5 py-3 font-medium">Status</th>
              <th className="px-5 py-3 font-medium">Uploaded</th>
              <th className="px-5 py-3 font-medium" />
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-[var(--color-muted)]">
                  <span className="inline-flex items-center gap-2.5 text-sm">
                    <Spinner size={16} className="text-[var(--color-accent)]" />
                    Loading documents
                  </span>
                </td>
              </tr>
            )}
            {!loading && documents.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-[var(--color-muted)]">
                  No documents yet. Upload a file or paste text to get started.
                </td>
              </tr>
            )}
            {documents.map((doc) => (
              <tr key={doc.id} className="border-b border-[var(--color-border)] last:border-0">
                <td className="flex items-center gap-2 px-5 py-3.5">
                  <FileText size={14} className="shrink-0 text-[var(--color-muted)]" />
                  <span className="truncate">{doc.filename}</span>
                </td>
                <td className="px-5 py-3.5 text-[var(--color-muted)]">{doc.type}</td>
                <td className="px-5 py-3.5 text-[var(--color-muted)]">{doc.chunkCount}</td>
                <td className="px-5 py-3.5">
                  <StatusPill status={doc.status} />
                </td>
                <td className="px-5 py-3.5 text-[var(--color-muted)]">
                  {formatDate(doc.createdAt)}
                </td>
                <td className="px-5 py-3.5 text-right">
                  <button
                    type="button"
                    onClick={() => handleDelete(doc.id)}
                    aria-label={`Delete ${doc.filename}`}
                    className="rounded-[var(--radius-sm)] p-1.5 text-[var(--color-muted)] hover:bg-[var(--color-app-bg)] hover:text-red-600"
                  >
                    <Trash2 size={14} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showPasteModal && (
        <PasteTextModal
          onClose={() => setShowPasteModal(false)}
          onSubmit={handlePasteText}
        />
      )}
    </div>
  );
}
