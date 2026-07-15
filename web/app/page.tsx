import LandingNav from "@/components/landing/LandingNav";
import Hero from "@/components/landing/Hero";
import FeatureBlurbs from "@/components/landing/FeatureBlurbs";
import PricingCard from "@/components/landing/PricingCard";
import LandingFooter from "@/components/landing/LandingFooter";

export default function Home() {
  return (
    <div className="flex min-h-screen flex-1 flex-col bg-[var(--color-app-bg)]">
      <LandingNav />
      <main className="flex-1">
        <Hero />
        <FeatureBlurbs />
        <PricingCard />
      </main>
      <LandingFooter />
    </div>
  );
}
