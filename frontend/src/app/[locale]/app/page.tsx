import { BotControlPanel } from "@/components/bot-control-panel";
import { SiteHeader } from "@/components/site-header";

export default function AppPage() {
  return (
    <main className="min-h-screen pb-16">
      <SiteHeader />
      <BotControlPanel />
    </main>
  );
}
