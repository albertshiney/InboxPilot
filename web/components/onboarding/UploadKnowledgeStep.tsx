"use client";

import { useState } from "react";
import { Plus } from "lucide-react";
import { apiUpload } from "@/lib/api";
import UploadDropzone from "@/components/UploadDropzone";
import PasteTextModal from "@/components/PasteTextModal";

export default function UploadKnowledgeStep({
  onNext,
}: {
  onNext: () => void;
}) {
  const [uploading, setUploading] = useState(false);
  const [uploadedCount, setUploadedCount] = useState(0);
  const [showPasteModal, setShowPasteModal] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleUploadFile(file: File) {
    setUploading(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      await apiUpload("kb/upload", formData);
      setUploadedCount((c) => c + 1);
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
    await apiUpload("kb/upload", formData);
    setUploadedCount((c) => c + 1);
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-[var(--color-foreground)]">
            Upload knowledge
          </h2>
          <p className="mt-1 text-sm text-[var(--color-muted)]">
            Add docs, FAQs, or policies so drafts sound like your business.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowPasteModal(true)}
          className="flex items-center gap-1.5 rounded-[var(--radius-sm)] border border-[var(--color-border)] px-3 py-1.5 text-sm font-medium text-[var(--color-foreground)] hover:bg-[var(--color-app-bg)]"
        >
          <Plus size={14} />
          Paste text
        </button>
      </div>

      <UploadDropzone onUpload={handleUploadFile} disabled={uploading} uploading={uploading} />

      {error && <p className="text-sm text-red-600">{error}</p>}

      {uploadedCount > 0 && (
        <p className="text-sm text-emerald-700">
          {uploadedCount} document{uploadedCount === 1 ? "" : "s"} uploaded.
        </p>
      )}

      <p className="text-xs text-[var(--color-muted)]">
        Drafts will be generic without this.
      </p>

      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onNext}
          className="rounded-[var(--radius-sm)] px-4 py-2 text-sm font-medium text-[var(--color-muted)] hover:bg-[var(--color-app-bg)]"
        >
          Skip
        </button>
        <button
          type="button"
          onClick={onNext}
          className="rounded-[var(--radius-sm)] bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white"
        >
          Continue
        </button>
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
