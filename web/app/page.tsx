import { redirect } from "next/navigation";
import { auth } from "@/auth";
import LandingNav from "@/components/landing/LandingNav";
import Hero from "@/components/landing/Hero";
import HowItWorks from "@/components/landing/HowItWorks";
import FeatureBlurbs from "@/components/landing/FeatureBlurbs";
import PricingCard from "@/components/landing/PricingCard";
import CtaBand from "@/components/landing/CtaBand";
import LandingFooter from "@/components/landing/LandingFooter";

export default async function Home() {
  const session = await auth();
  if (session?.user) {
    redirect("/dashboard");
  }

  return (
    <div className="flex min-h-screen flex-1 flex-col bg-[var(--color-app-bg)]">
      <LandingNav />
      <main className="flex-1">
        <Hero />
        <HowItWorks />
        <FeatureBlurbs />
        <PricingCard />
        <CtaBand />
      </main>
      <LandingFooter />
    </div>
  );
}
