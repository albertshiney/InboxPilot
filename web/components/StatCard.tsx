import Link from "next/link";
import { ArrowUpRight } from "lucide-react";

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
      className={`group relative rounded-[var(--radius-md)] border border-[var(--color-border)] bg-white px-5 py-5 shadow-[var(--shadow-card)] transition-all sm:px-6 ${
        href ? "hover:-translate-y-0.5 hover:border-[var(--color-border-strong)] hover:shadow-[var(--shadow-raised)]" : ""
      }`}
    >
      <p className="text-[13px] font-medium uppercase tracking-wide text-[var(--color-muted)]">
        {label}
      </p>
      <p className="readout mt-2 text-3xl font-semibold text-[var(--color-foreground)]">
        {loading ? "—" : value}
      </p>
      {href && (
        <ArrowUpRight
          size={16}
          className="absolute right-4 top-4 text-[var(--color-faint)] transition-colors group-hover:text-[var(--color-accent)]"
        />
      )}
    </div>
  );

  if (!href) return content;

  return (
    <Link href={href} className="block">
      {content}
    </Link>
  );
}
