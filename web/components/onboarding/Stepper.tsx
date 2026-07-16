import { Check } from "lucide-react";

const STEPS = ["Connect Gmail", "Upload knowledge", "Choose mode", "Start your free trial"];

export default function Stepper({ current }: { current: number }) {
  return (
    <ol className="flex items-center gap-2 sm:gap-3">
      {STEPS.map((label, i) => {
        const stepNumber = i + 1;
        const isDone = stepNumber < current;
        const isActive = stepNumber === current;
        return (
          <li key={label} className="flex min-w-0 items-center gap-2 sm:gap-3">
            <div className="flex min-w-0 items-center gap-2">
              <span
                className={`readout flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-medium transition-colors ${
                  isDone
                    ? "bg-[var(--color-accent)] text-white"
                    : isActive
                      ? "border-2 border-[var(--color-accent)] bg-[var(--color-accent-soft)] text-[var(--color-accent)]"
                      : "border border-[var(--color-border)] text-[var(--color-muted)]"
                }`}
              >
                {isDone ? <Check size={13} strokeWidth={3} /> : stepNumber}
              </span>
              {/* On small screens only the active step keeps its label. */}
              <span
                className={`truncate text-sm ${
                  isActive
                    ? "font-medium text-[var(--color-foreground)]"
                    : "hidden text-[var(--color-muted)] sm:inline"
                }`}
              >
                {label}
              </span>
            </div>
            {stepNumber < STEPS.length && (
              <span
                className={`h-px w-4 shrink-0 sm:w-8 ${
                  isDone ? "bg-[var(--color-accent)]" : "bg-[var(--color-border)]"
                }`}
              />
            )}
          </li>
        );
      })}
    </ol>
  );
}
