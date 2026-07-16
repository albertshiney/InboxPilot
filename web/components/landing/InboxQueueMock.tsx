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
      className="w-full overflow-hidden rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-white shadow-[var(--shadow-overlay)]"
    >
      {/* Window chrome */}
      <div className="flex items-center gap-4 border-b border-[var(--color-border)] bg-[var(--color-app-bg)] px-5 py-3.5">
        <div className="flex items-center gap-2">
          <span className="h-3 w-3 rounded-full bg-[#FC5F57]" />
          <span className="h-3 w-3 rounded-full bg-[#FDBB2E]" />
          <span className="h-3 w-3 rounded-full bg-[#28C840]" />
        </div>
        <div className="hidden flex-1 justify-center sm:flex">
          <span className="rounded-md bg-white px-8 py-1 text-xs text-[var(--color-faint)] ring-1 ring-[var(--color-border)]">
            app.inboxpilot.com/inbox
          </span>
        </div>
        <div className="w-16" />
      </div>

      {/* Tabs */}
      <div className="scrollbar-none flex items-center gap-1 overflow-x-auto border-b border-[var(--color-border)] px-4 pt-3 text-sm sm:px-5">
        {TABS.map((tab, i) => (
          <span
            key={tab}
            className={`whitespace-nowrap border-b-2 px-3.5 pb-2.5 pt-1 font-medium ${
              i === 0
                ? "border-[var(--color-accent)] text-[var(--color-accent)]"
                : "border-transparent text-[var(--color-muted)]"
            }`}
          >
            {tab}
            {i === 0 && (
              <span className="readout ml-2 rounded-full bg-[var(--color-accent-soft)] px-2 py-0.5 text-xs text-[var(--color-accent)]">
                4
              </span>
            )}
          </span>
        ))}
      </div>

      {/* Rows */}
      <div className="divide-y divide-[var(--color-border)]">
        {ROWS.map((row, i) => (
          <div
            key={row.from}
            className={`flex flex-col gap-2.5 px-4 py-4 sm:flex-row sm:items-center sm:gap-4 sm:px-5 ${
              i === 0 ? "bg-[var(--color-accent-soft)]/50" : ""
            }`}
          >
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-[var(--color-foreground)]">
                {row.subject}
              </p>
              <p className="mt-0.5 truncate text-[13px] text-[var(--color-muted)]">
                {row.from}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2.5">
              <span
                className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ${row.categoryColor}`}
              >
                {row.category}
              </span>
              <span
                className={`readout inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ${row.confidenceColor}`}
              >
                {row.confidence}%
              </span>
              <span className="readout hidden w-16 text-right text-xs text-[var(--color-faint)] sm:inline-block">
                {row.time}
              </span>
              {i === 0 && (
                <span className="hidden rounded-lg bg-[var(--color-accent)] px-3.5 py-1.5 text-xs font-medium text-white shadow-sm sm:inline-block">
                  Approve
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
