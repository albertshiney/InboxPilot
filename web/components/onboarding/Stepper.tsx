import { Check } from "lucide-react";

const STEPS = ["Connect Gmail", "Upload knowledge", "Choose mode", "Start trial"];

// Equal-width columns with the label under each dot so no step ever truncates
// away. Connectors are the "flight path": dashed while upcoming, solid indigo
// once flown.
export default function Stepper({ current }: { current: number }) {
  return (
    <ol className="flex items-start">
      {STEPS.map((label, i) => {
        const stepNumber = i + 1;
        const isDone = stepNumber < current;
        const isActive = stepNumber === current;
        return (
          <li key={label} className="flex flex-1 flex-col items-center gap-2">
            <div className="flex w-full items-center">
              <span
                aria-hidden
                className={`flex-1 border-t ${
                  i === 0
                    ? "invisible"
                    : isDone || isActive
                      ? "border-solid border-[var(--color-accent)]"
                      : "border-dashed border-[var(--color-border)]"
                }`}
              />
              <span
                className={`readout mx-1.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-medium transition-colors sm:mx-2 ${
                  isDone
                    ? "bg-[var(--color-accent)] text-white"
                    : isActive
                      ? "border-2 border-[var(--color-accent)] bg-[var(--color-accent-soft)] text-[var(--color-accent)]"
                      : "border border-[var(--color-border)] bg-white text-[var(--color-muted)]"
                }`}
              >
                {isDone ? <Check size={13} strokeWidth={3} /> : stepNumber}
              </span>
              <span
                aria-hidden
                className={`flex-1 border-t ${
                  stepNumber === STEPS.length
                    ? "invisible"
                    : isDone
                      ? "border-solid border-[var(--color-accent)]"
                      : "border-dashed border-[var(--color-border)]"
                }`}
              />
            </div>
            <span
              className={`px-1 text-center text-[11px] leading-tight sm:text-xs ${
                isActive
                  ? "font-medium text-[var(--color-foreground)]"
                  : "text-[var(--color-muted)]"
              }`}
            >
              {label}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
