"use client";

import { useEffect, useState, type FormEvent } from "react";
import { signIn } from "next-auth/react";

const RESEND_COOLDOWN_SECONDS = 30;

type AuthCardProps = {
  heading: string;
  subheading: string;
  /** Text for the link at the bottom, pointing at the other of /login or /signup. */
  switchHref: string;
  switchLabel: string;
  switchLinkText: string;
};

export default function AuthCard({
  heading,
  subheading,
  switchHref,
  switchLabel,
  switchLinkText,
}: AuthCardProps) {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"form" | "sending" | "sent">("form");
  const [error, setError] = useState<string | null>(null);
  const [cooldown, setCooldown] = useState(0);

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = setInterval(() => {
      setCooldown((seconds) => Math.max(0, seconds - 1));
    }, 1000);
    return () => clearInterval(timer);
  }, [cooldown]);

  async function sendMagicLink() {
    setStatus("sending");
    setError(null);
    const result = await signIn("resend", {
      email: email.trim().toLowerCase(),
      redirect: false,
      redirectTo: "/dashboard",
    });

    if (result?.error) {
      setError("Something went wrong sending your link. Try again.");
      setStatus("form");
      return;
    }

    setStatus("sent");
    setCooldown(RESEND_COOLDOWN_SECONDS);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void sendMagicLink();
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--color-app-bg)] px-4">
      <div className="w-full max-w-sm rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-card-bg)] p-8 shadow-sm">
        <h1 className="text-lg font-semibold text-[var(--color-foreground)]">
          {heading}
        </h1>
        <p className="mt-1 text-sm text-[var(--color-muted)]">{subheading}</p>

        {status === "sent" ? (
          <div className="mt-6">
            <p className="text-sm text-[var(--color-foreground)]">
              Check your inbox — we sent a sign-in link to{" "}
              <span className="font-medium">{email}</span>.
            </p>
            <button
              type="button"
              onClick={() => void sendMagicLink()}
              disabled={cooldown > 0}
              className="mt-4 w-full rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-card-bg)] px-3 py-2 text-sm font-medium text-[var(--color-foreground)] transition-colors hover:bg-[var(--color-app-bg)] disabled:cursor-not-allowed disabled:text-[var(--color-muted)] disabled:hover:bg-[var(--color-card-bg)]"
            >
              {cooldown > 0 ? `Resend link (${cooldown}s)` : "Resend link"}
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-3">
            <label className="flex flex-col gap-1.5">
              <span className="text-sm font-medium text-[var(--color-foreground)]">
                Email
              </span>
              <input
                type="email"
                required
                autoFocus
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@company.com"
                className="rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-card-bg)] px-3 py-2 text-sm text-[var(--color-foreground)] outline-none placeholder:text-[var(--color-muted)] focus:border-[var(--color-accent)]"
              />
            </label>

            {error && <p className="text-sm text-red-600">{error}</p>}

            <button
              type="submit"
              disabled={status === "sending"}
              className="mt-1 w-full rounded-[var(--radius-sm)] bg-[var(--color-accent)] px-3 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-60"
            >
              {status === "sending" ? "Sending…" : "Continue with email"}
            </button>
          </form>
        )}

        <p className="mt-6 text-center text-sm text-[var(--color-muted)]">
          {switchLabel}{" "}
          <a
            href={switchHref}
            className="font-medium text-[var(--color-accent)] hover:underline"
          >
            {switchLinkText}
          </a>
        </p>
      </div>
    </div>
  );
}
