// Loading indicators for the Flight deck design system. The spinner is a
// rotating dashed ring — the same dashed flight-path motif as the logo and
// hero — so "loading" reads as "in flight". Inherits `currentColor`, so it
// picks up whatever text color the surrounding button or label uses.
// Rotation lives in globals.css (`.spinner`), where reduced-motion swaps the
// continuous spin for a discrete stepped tick.

export default function Spinner({
  size = 16,
  className = "",
}: {
  size?: number;
  className?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      className={`spinner shrink-0 ${className}`}
    >
      <circle
        cx="12"
        cy="12"
        r="9"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeDasharray="4.71 4.71"
      />
    </svg>
  );
}

// Centered loader for client-fetched pages (settings, AI behavior, thread
// view) — replaces bare "Loading..." text so every wait looks the same.
export function PageLoader({ label = "Loading" }: { label?: string }) {
  return (
    <div
      role="status"
      className="flex flex-col items-center justify-center gap-3 py-16 text-[var(--color-muted)]"
    >
      <Spinner size={24} className="text-[var(--color-accent)]" />
      <span className="text-sm">{label}</span>
    </div>
  );
}
