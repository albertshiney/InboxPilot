"use client";

import { useCallback, useRef, useState } from "react";
import { UploadCloud } from "lucide-react";

const ACCEPTED_EXTENSIONS = [".pdf", ".docx", ".txt", ".md"];

function hasAcceptedExtension(filename: string): boolean {
  const lower = filename.toLowerCase();
  return ACCEPTED_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

export default function UploadDropzone({
  onUpload,
  disabled,
}: {
  onUpload: (file: File) => Promise<void> | void;
  disabled?: boolean;
}) {
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(
    async (file: File) => {
      setError(null);
      if (!hasAcceptedExtension(file.name)) {
        setError("Unsupported file type. Use .pdf, .docx, .txt, or .md.");
        return;
      }
      await onUpload(file);
    },
    [onUpload],
  );

  return (
    <div>
      <div
        role="button"
        tabIndex={0}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
        }}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragging(false);
          if (disabled) return;
          const file = e.dataTransfer.files?.[0];
          if (file) void handleFile(file);
        }}
        className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-[var(--radius-md)] border border-dashed px-6 py-10 text-center transition-colors ${
          isDragging
            ? "border-[var(--color-accent)] bg-[var(--color-accent-soft)]"
            : "border-[var(--color-border)] bg-[var(--color-card-bg)] hover:bg-[var(--color-app-bg)]"
        } ${disabled ? "pointer-events-none opacity-60" : ""}`}
      >
        <UploadCloud size={22} className="text-[var(--color-muted)]" />
        <p className="text-sm text-[var(--color-foreground)]">
          Drag a file here, or click to browse
        </p>
        <p className="text-xs text-[var(--color-muted)]">
          .pdf, .docx, .txt, or .md
        </p>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED_EXTENSIONS.join(",")}
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (file) void handleFile(file);
        }}
      />
      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
    </div>
  );
}
