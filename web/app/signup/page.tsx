import { redirect } from "next/navigation";
import { auth } from "@/auth";
import AuthCard from "@/components/AuthCard";

export default async function SignupPage() {
  const session = await auth();
  if (session?.user) {
    redirect("/dashboard");
  }
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
