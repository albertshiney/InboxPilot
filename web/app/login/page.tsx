import { redirect } from "next/navigation";
import { auth } from "@/auth";
import AuthCard from "@/components/AuthCard";

export default async function LoginPage() {
  const session = await auth();
  if (session?.user) {
    redirect("/dashboard");
  }
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
