const STEPS = ["Connect Gmail", "Upload knowledge", "Choose mode"];

export default function Stepper({ current }: { current: number }) {
  return (
    <ol className="flex items-center gap-3">
      {STEPS.map((label, i) => {
        const stepNumber = i + 1;
        const isDone = stepNumber < current;
        const isActive = stepNumber === current;
        return (
          <li key={label} className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <span
                className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-medium ${
                  isDone
                    ? "bg-[var(--color-accent)] text-white"
                    : isActive
                      ? "border-2 border-[var(--color-accent)] text-[var(--color-accent)]"
                      : "border border-[var(--color-border)] text-[var(--color-muted)]"
                }`}
              >
                {isDone ? "✓" : stepNumber}
              </span>
              <span
                className={`text-sm ${
                  isActive
                    ? "font-medium text-[var(--color-foreground)]"
                    : "text-[var(--color-muted)]"
                }`}
              >
                {label}
              </span>
            </div>
            {stepNumber < STEPS.length && (
              <span className="h-px w-8 bg-[var(--color-border)]" />
            )}
          </li>
        );
      })}
    </ol>
  );
}
