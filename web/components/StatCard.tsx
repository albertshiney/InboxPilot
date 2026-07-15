import Link from "next/link";

export default function StatCard({
  label,
  value,
  href,
  loading,
}: {
  label: string;
  value: string;
  href?: string;
  loading?: boolean;
}) {
  const content = (
    <div
      className={`rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-card-bg)] px-5 py-4 shadow-sm ${
        href ? "transition-colors hover:bg-[var(--color-app-bg)]" : ""
      }`}
    >
      <p className="text-xs font-medium text-[var(--color-muted)]">{label}</p>
      <p className="mt-1.5 text-2xl font-semibold text-[var(--color-foreground)]">
        {loading ? "—" : value}
      </p>
    </div>
  );

  if (!href) return content;

  return (
    <Link href={href} className="block">
      {content}
    </Link>
  );
}
