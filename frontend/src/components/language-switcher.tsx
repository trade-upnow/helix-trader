"use client";

import { Globe } from "lucide-react";
import { useLocale } from "next-intl";
import { useTransition } from "react";

import { usePathname, useRouter } from "@/i18n/navigation";
import { routing } from "@/i18n/routing";

export function LanguageSwitcher() {
  const locale = useLocale();
  const pathname = usePathname();
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  return (
    <label className="glass-card flex items-center gap-2 rounded-full px-3 py-2 text-sm text-white/80">
      <Globe size={16} className="text-cyan-300" />
      <select
        className="bg-transparent outline-none"
        disabled={isPending}
        value={locale}
        onChange={(event) => {
          const nextLocale = event.target.value as (typeof routing.locales)[number];
          startTransition(() => {
            router.replace(pathname, { locale: nextLocale });
            router.refresh();
          });
        }}
      >
        <option value="ko" className="bg-slate-900">
          KO
        </option>
        <option value="zh-CN" className="bg-slate-900">
          简中
        </option>
        <option value="en" className="bg-slate-900">
          EN
        </option>
        <option value="es" className="bg-slate-900">
          ES
        </option>
      </select>
    </label>
  );
}
