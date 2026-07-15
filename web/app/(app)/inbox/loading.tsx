// Instant loading skeleton for /inbox: mirrors the tab bar + table shell so
// the swap-in on real data doesn't jump the layout.

function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div className={`animate-pulse rounded-[var(--radius-sm)] bg-[var(--color-border)] ${className}`} />
  );
}

export default function InboxLoading() {
  return (
    <div className="flex flex-col gap-4">
      <Skeleton className="h-6 w-20" />

      <div className="flex gap-4 border-b border-[var(--color-border)] pb-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-4 w-20" />
        ))}
      </div>

      <div className="overflow-hidden rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-card-bg)]">
        {Array.from({ length: 8 }).map((_, i) => (
          <div
            key={i}
            className="flex items-center gap-4 border-b border-[var(--color-border)] px-4 py-3 last:border-0"
          >
            <Skeleton className="h-3 w-1/6" />
            <Skeleton className="h-3 w-1/3" />
            <Skeleton className="h-3 w-16" />
            <Skeleton className="h-3 w-12" />
            <Skeleton className="h-3 w-10" />
          </div>
        ))}
      </div>
    </div>
  );
}
