import AuthCard from "@/components/AuthCard";

export default function LoginPage() {
  return (
    <AuthCard
      heading="Log in to InboxPilot"
      subheading="We'll email you a magic link — no password needed."
      switchHref="/signup"
      switchLabel="New to InboxPilot?"
      switchLinkText="Create an account"
    />
  );
}
