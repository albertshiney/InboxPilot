"use client";

import { useState } from "react";

const MIN_THRESHOLD = 50;
const MAX_THRESHOLD = 99;
const DEFAULT_THRESHOLD = 85;

export type ModeSelection = {
  autopilot: boolean;
  confidenceThreshold: number;
};

export default function ChooseModeStep({
  onFinish,
  finishing,
}: {
  onFinish: (selection: ModeSelection) => void;
  finishing: boolean;
}) {
  const [autopilot, setAutopilot] = useState(false);
  const [threshold, setThreshold] = useState(DEFAULT_THRESHOLD);

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h2 className="text-lg font-semibold text-[var(--color-foreground)]">
          Choose your mode
        </h2>
        <p className="mt-1 text-sm text-[var(--color-muted)]">
          You can change this later in Settings.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label
          className={`cursor-pointer rounded-[var(--radius-md)] border px-4 py-3 transition-colors ${
            !autopilot
              ? "border-[var(--color-accent)] bg-[var(--color-accent-soft)]"
              : "border-[var(--color-border)] bg-[var(--color-card-bg)] hover:bg-[var(--color-app-bg)]"
          }`}
        >
          <div className="flex items-start gap-2">
            <input
              type="radio"
              name="mode"
              checked={!autopilot}
              onChange={() => setAutopilot(false)}
              className="mt-1"
            />
            <div>
              <p className="text-sm font-medium text-[var(--color-foreground)]">
                Draft mode <span className="text-[var(--color-accent)]">(recommended)</span>
              </p>
              <p className="mt-1 text-xs text-[var(--color-muted)]">
                Every reply is drafted for your review before it sends. Nothing
                goes out without your approval.
              </p>
            </div>
          </div>
        </label>

        <label
          className={`cursor-pointer rounded-[var(--radius-md)] border px-4 py-3 transition-colors ${
            autopilot
              ? "border-[var(--color-accent)] bg-[var(--color-accent-soft)]"
              : "border-[var(--color-border)] bg-[var(--color-card-bg)] hover:bg-[var(--color-app-bg)]"
          }`}
        >
          <div className="flex items-start gap-2">
            <input
              type="radio"
              name="mode"
              checked={autopilot}
              onChange={() => setAutopilot(true)}
              className="mt-1"
            />
            <div>
              <p className="text-sm font-medium text-[var(--color-foreground)]">Autopilot</p>
              <p className="mt-1 text-xs text-[var(--color-muted)]">
                High-confidence replies send automatically. Anything below the
                threshold still lands in your review queue.
              </p>
            </div>
          </div>
        </label>
      </div>

      {autopilot && (
        <div className="rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-card-bg)] px-4 py-3">
          <div className="flex items-center justify-between">
            <label htmlFor="threshold" className="text-sm font-medium text-[var(--color-foreground)]">
              Confidence threshold
            </label>
            <span className="text-sm font-semibold text-[var(--color-accent)]">
              {threshold}%
            </span>
          </div>
          <input
            id="threshold"
            type="range"
            min={MIN_THRESHOLD}
            max={MAX_THRESHOLD}
            value={threshold}
            onChange={(e) => setThreshold(Number(e.target.value))}
            className="mt-3 w-full accent-[var(--color-accent)]"
          />
          <p className="mt-2 text-xs text-[var(--color-muted)]">
            Only drafts InboxPilot scores at or above {threshold}% confidence
            send automatically — everything else, and any category you&apos;ve
            blocked, always waits for your review.
          </p>
        </div>
      )}

      <div className="flex justify-end">
        <button
          type="button"
          onClick={() => onFinish({ autopilot, confidenceThreshold: threshold })}
          disabled={finishing}
          className="rounded-[var(--radius-sm)] bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {finishing ? "Finishing..." : "Finish"}
        </button>
      </div>
    </div>
  );
}
