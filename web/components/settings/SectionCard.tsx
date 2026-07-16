// Shared card shell for every anchored settings section: id (for the
// sub-nav anchor links), title, optional description, content.

export default function SectionCard({
  id,
  title,
  description,
  children,
}: {
  id: string;
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <section
      id={id}
      className="scroll-mt-6 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-white p-6 shadow-[var(--shadow-card)] sm:p-7"
    >
      <h2 className="text-lg font-semibold text-[var(--color-foreground)]">{title}</h2>
      {description && (
        <p className="mt-1 text-[15px] text-[var(--color-muted)]">{description}</p>
      )}
      <div className="mt-5 flex flex-col gap-4">{children}</div>
    </section>
  );
}
