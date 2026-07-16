"use client";

// InboxPilot brand mark: a paper plane climbing along a dashed flight
// path, set in an indigo gradient tile. Keep in sync with app/icon.svg.

import { useId } from "react";

export function LogoMark({ size = 32 }: { size?: number }) {
  // The mark renders more than once per page (sidebar + mobile top bar).
  // The gradient id must be unique per instance: url(#...) resolves to the
  // first matching id in the document, and a gradient inside a display:none
  // subtree (the lg-hidden sidebar on phones) paints nothing.
  const gradientId = useId();
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      aria-hidden="true"
      className="shrink-0"
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="32" x2="32" y2="0">
          <stop offset="0%" stopColor="#4338CA" />
          <stop offset="100%" stopColor="#6366F1" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="8" fill={`url(#${gradientId})`} />
      <path
        d="M5.5 26.5C10 25.5 12.5 22.5 14 18.5"
        stroke="#C7D2FE"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeDasharray="0.5 3.4"
      />
      <path
        d="M26.5 5.5L14.6 17.4"
        stroke="#A5B4FC"
        strokeWidth="1.4"
        strokeLinecap="round"
      />
      <path
        d="M26.5 5.5L19 25.5L14.6 17.4L6.5 13L26.5 5.5Z"
        fill="#fff"
      />
    </svg>
  );
}

export default function Logo({
  size = 30,
  wordmark = true,
  className = "",
}: {
  size?: number;
  wordmark?: boolean;
  className?: string;
}) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <LogoMark size={size} />
      {wordmark && (
        <span className="font-display text-lg font-semibold tracking-tight text-[var(--color-foreground)]">
          InboxPilot
        </span>
      )}
    </span>
  );
}
