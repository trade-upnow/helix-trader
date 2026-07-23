import { SiteHeader } from "@/components/site-header";
import { StrategyShowcase } from "@/components/strategy-showcase";

export default function LandingPage() {
  return (
    <main className="min-h-screen pb-16">
      <SiteHeader />
      <StrategyShowcase />
    </main>
  );
}
