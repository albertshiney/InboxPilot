// Confidence badge: green >=85, amber 60-84, red <60. Renders a neutral
// dash when no draft (and therefore no confidence) exists yet.

const TIER_STYLES = {
  green: "bg-emerald-50 text-emerald-700",
  amber: "bg-amber-50 text-amber-700",
  red: "bg-red-50 text-red-700",
} as const;

function tierFor(confidence: number): keyof typeof TIER_STYLES {
  if (confidence >= 85) return "green";
  if (confidence >= 60) return "amber";
  return "red";
}

export default function ConfidenceBadge({
  confidence,
}: {
  confidence: number | null | undefined;
}) {
  if (confidence === null || confidence === undefined) {
    return (
      <span className="readout inline-flex items-center rounded-full bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-500">
        —
      </span>
    );
  }

  const tier = tierFor(confidence);

  return (
    <span
      className={`readout inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ${TIER_STYLES[tier]}`}
    >
      {confidence}%
    </span>
  );
}
