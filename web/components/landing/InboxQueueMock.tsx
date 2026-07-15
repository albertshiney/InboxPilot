// Static, div-built mock of the /inbox review queue used as the landing
// page "screenshot". No image asset — this mirrors the real table's tabs,
// category pills, and confidence badges so the marketing page can't drift
// from the actual product without someone noticing.

type MockRow = {
  from: string;
  subject: string;
  category: string;
  categoryColor: string;
  confidence: number;
  confidenceColor: string;
  time: string;
};

const ROWS: MockRow[] = [
  {
    from: "jordan@northfield.co",
    subject: "Refund for duplicate charge on order #4821",
    category: "Refund",
    categoryColor: "bg-orange-50 text-orange-700",
    confidence: 92,
    confidenceColor: "bg-emerald-50 text-emerald-700",
    time: "2m ago",
  },
  {
    from: "priya@lumen-labs.io",
    subject: "How do I connect the API to Zapier?",
    category: "Technical",
    categoryColor: "bg-blue-50 text-blue-700",
    confidence: 88,
    confidenceColor: "bg-emerald-50 text-emerald-700",
    time: "14m ago",
  },
  {
    from: "sam.reyes@grove.app",
    subject: "Invoice says I was charged twice this month",
    category: "Billing",
    categoryColor: "bg-violet-50 text-violet-700",
    confidence: 64,
    confidenceColor: "bg-amber-50 text-amber-700",
    time: "38m ago",
  },
  {
    from: "delivery@parkside-shop.com",
    subject: "Package marked delivered but never arrived",
    category: "Shipping",
    categoryColor: "bg-teal-50 text-teal-700",
    confidence: 79,
    confidenceColor: "bg-amber-50 text-amber-700",
    time: "1h ago",
  },
];

const TABS = ["Needs review", "Autopilot", "Sent", "All"];

export default function InboxQueueMock() {
  return (
    <div
      aria-hidden="true"
      className="w-full overflow-hidden rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-card-bg)] shadow-sm"
    >
      {/* Window chrome */}
      <div className="flex items-center gap-1.5 border-b border-[var(--color-border)] px-4 py-3">
        <span className="h-2.5 w-2.5 rounded-full bg-red-300" />
        <span className="h-2.5 w-2.5 rounded-full bg-amber-300" />
        <span className="h-2.5 w-2.5 rounded-full bg-emerald-300" />
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 overflow-x-auto border-b border-[var(--color-border)] px-3 pt-2.5 text-xs sm:px-4">
        {TABS.map((tab, i) => (
          <span
            key={tab}
            className={`whitespace-nowrap rounded-t-[var(--radius-sm)] px-3 py-1.5 font-medium ${
              i === 0
                ? "bg-[var(--color-accent-soft)] text-[var(--color-accent)]"
                : "text-[var(--color-muted)]"
            }`}
          >
            {tab}
          </span>
        ))}
      </div>

      {/* Rows */}
      <div className="divide-y divide-[var(--color-border)]">
        {ROWS.map((row, i) => (
          <div
            key={row.from}
            className={`flex flex-col gap-2 px-3 py-3 sm:flex-row sm:items-center sm:gap-4 sm:px-4 ${
              i === 0 ? "bg-[var(--color-accent-soft)]/40" : ""
            }`}
          >
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-medium text-[var(--color-foreground)]">
                {row.subject}
              </p>
              <p className="truncate text-xs text-[var(--color-muted)]">{row.from}</p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <span
                className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${row.categoryColor}`}
              >
                {row.category}
              </span>
              <span
                className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${row.confidenceColor}`}
              >
                {row.confidence}%
              </span>
              <span className="hidden w-14 text-right text-[11px] text-[var(--color-muted)] sm:inline-block">
                {row.time}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
