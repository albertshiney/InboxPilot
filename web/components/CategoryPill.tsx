// Category pill for the fixed draft.category vocabulary produced by
// app/draft.py's system prompt. Unknown values fall back to the "other"
// styling with their raw label so the UI never breaks on a new category.

const LABELS: Record<string, string> = {
  billing: "Billing",
  technical: "Technical",
  shipping: "Shipping",
  account: "Account",
  refund: "Refund",
  other: "Other",
};

const COLORS: Record<string, string> = {
  billing: "bg-violet-50 text-violet-700",
  technical: "bg-blue-50 text-blue-700",
  shipping: "bg-teal-50 text-teal-700",
  account: "bg-indigo-50 text-indigo-700",
  refund: "bg-orange-50 text-orange-700",
  other: "bg-gray-100 text-gray-600",
};

export default function CategoryPill({
  category,
}: {
  category: string | null | undefined;
}) {
  if (!category) return null;

  const label = LABELS[category] ?? category;
  const color = COLORS[category] ?? COLORS.other;

  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ${color}`}
    >
      {label}
    </span>
  );
}
