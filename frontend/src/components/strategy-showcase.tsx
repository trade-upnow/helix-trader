import { ShieldCheck, Sparkles } from "lucide-react";
import { useTranslations } from "next-intl";

import { Link } from "@/i18n/navigation";

import { EquityChart } from "./equity-chart";

export function StrategyShowcase() {
  const tHero = useTranslations("hero");
  const tStrategy = useTranslations("strategy");

  return (
    <section className="mx-auto flex w-full max-w-7xl flex-col gap-10 px-6 py-10 lg:px-10">
      <div className="grid gap-8 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="space-y-8">
          <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-cyan-200">
            <Sparkles size={16} />
            {tHero("badge")}
          </div>
          <div className="space-y-5">
            <h1 className="max-w-4xl text-5xl font-semibold leading-tight tracking-tight md:text-7xl">
              <span className="gradient-text">{tHero("title")}</span>
            </h1>
            <p className="max-w-2xl text-lg leading-8 text-muted">
              {tHero("description")}
            </p>
          </div>
          <div className="flex flex-wrap gap-4 pt-4">
            <Link
              href="/app"
              className="rounded-full bg-cyan-400 px-8 py-4 font-bold text-lg text-slate-950 transition-all shadow-[0_0_20px_rgba(6,182,212,0.4)] hover:shadow-[0_0_30px_rgba(6,182,212,0.6)] hover:-translate-y-1"
            >
              {tHero("primary")}
            </Link>
            <a
              href="#strategy"
              className="rounded-full border border-white/12 px-8 py-4 font-bold text-lg text-white/90 transition-all hover:bg-white/6 hover:-translate-y-1"
            >
              {tHero("secondary")}
            </a>
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            {[
              { label: tHero("stats1Label"), value: "+28.4%", colorClass: "text-emerald-400 drop-shadow-[0_0_12px_rgba(52,211,153,0.4)]" },
              { label: tHero("stats2Label"), value: "~315.8%", colorClass: "text-cyan-400 drop-shadow-[0_0_12px_rgba(34,211,238,0.4)]" },
              { label: tHero("stats3Label"), value: "-6.2%", colorClass: "text-rose-400 drop-shadow-[0_0_12px_rgba(251,113,133,0.4)]" },
            ].map((stat) => (
              <div key={stat.label} className="bg-white/5 backdrop-blur-md border border-white/10 shadow-[0_8px_30px_rgb(0,0,0,0.12)] rounded-3xl p-6 relative overflow-hidden group hover:-translate-y-1 transition-all duration-300">
                <div className="absolute inset-0 bg-gradient-to-b from-white/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
                <p className="text-xs uppercase tracking-[0.2em] font-medium text-white/50 relative z-10">
                  {stat.label}
                </p>
                <p className={`mt-4 text-4xl font-extrabold font-mono ${stat.colorClass} relative z-10`}>{stat.value}</p>
              </div>
            ))}
          </div>
        </div>
        <EquityChart />
      </div>

      <div
        id="strategy"
        className="bg-[#0F172A] border border-white/10 shadow-2xl grid gap-8 rounded-[2.5rem] p-8 lg:grid-cols-[1fr_0.8fr]"
      >
        <div>
          <p className="text-sm uppercase tracking-[0.3em] text-cyan-300/80">
            {tStrategy("sectionTitle")}
          </p>
          <h2 className="mt-3 text-4xl font-semibold">{tStrategy("name")}</h2>
          <p className="mt-4 max-w-3xl text-lg leading-8 text-muted">
            {tStrategy("subtitle")}
          </p>
          <div className="mt-8 space-y-4">
            {[tStrategy("bullet1"), tStrategy("bullet2"), tStrategy("bullet3")].map(
              (item) => (
                <div key={item} className="flex gap-3 rounded-2xl border border-white/8 bg-white/3 p-4">
                  <ShieldCheck className="mt-1 text-cyan-300" size={18} />
                  <p className="text-sm leading-7 text-white/86">{item}</p>
                </div>
              ),
            )}
          </div>
        </div>

        <div className="space-y-4">
          {[
            { text: tStrategy("monthlyReturn"), icon: "📈", borderColor: "border-emerald-500/30", bgColor: "bg-emerald-500/10", textColor: "text-emerald-300" },
            { text: tStrategy("annualized"), icon: "🚀", borderColor: "border-cyan-500/30", bgColor: "bg-cyan-500/10", textColor: "text-cyan-300" },
            { text: tStrategy("winRate"), icon: "🎯", borderColor: "border-purple-500/30", bgColor: "bg-purple-500/10", textColor: "text-purple-300" },
          ].map((item) => (
            <div key={item.text} className={`rounded-3xl border ${item.borderColor} ${item.bgColor} p-5 shadow-[0_0_20px_rgba(0,0,0,0.2)] flex items-center gap-4 group hover:-translate-y-1 transition-all duration-300 relative overflow-hidden`}>
              <div className="absolute inset-0 bg-white/5 opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
              <span className="text-2xl relative z-10">{item.icon}</span>
              <p className={`text-lg font-bold tracking-wide ${item.textColor} relative z-10`}>{item.text}</p>
            </div>
          ))}
          <div
            className="flex items-center justify-between rounded-3xl border border-cyan-400/20 bg-cyan-400/8 p-5 text-cyan-100"
          >
            <div>
              <p className="text-sm uppercase tracking-[0.24em] text-cyan-300/80">
                {tStrategy("riskLabel")}
              </p>
              <p className="mt-2 max-w-lg text-sm leading-7 text-white/70">
                {tStrategy("riskText")}
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
