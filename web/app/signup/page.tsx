import AuthCard from "@/components/AuthCard";

export default function SignupPage() {
  return (
    <AuthCard
      heading="Create your InboxPilot account"
      subheading="Enter your email and we'll send you a magic link to get started."
      switchHref="/login"
      switchLabel="Already have an account?"
      switchLinkText="Log in"
    />
  );
}
