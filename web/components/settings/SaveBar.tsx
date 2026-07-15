// Save button + inline "Saved" toast / error, shared by every settings
// section that PATCHes /settings.

export default function SaveBar({
  onSave,
  saving,
  saved,
  error,
  label = "Save",
}: {
  onSave: () => void;
  saving: boolean;
  saved: boolean;
  error: string | null;
  label?: string;
}) {
  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        onClick={onSave}
        disabled={saving}
        className="w-fit rounded-[var(--radius-sm)] bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
      >
        {saving ? "Saving..." : label}
      </button>
      {saved && <span className="text-sm text-emerald-600">Saved</span>}
      {error && <span className="text-sm text-red-600">{error}</span>}
    </div>
  );
}
