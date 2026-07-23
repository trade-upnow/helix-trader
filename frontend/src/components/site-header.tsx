"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { Link, useRouter } from "@/i18n/navigation";
import { authStorage } from "@/lib/api";

import { LanguageSwitcher } from "./language-switcher";

export function SiteHeader() {
  const t = useTranslations("nav");
  const router = useRouter();
  const [isLoggedIn, setIsLoggedIn] = useState(false);

  useEffect(() => {
    const syncToken = () => {
      setIsLoggedIn(Boolean(authStorage.getToken()));
    };

    syncToken();
    return authStorage.subscribe(syncToken);
  }, []);

  return (
    <header className="mx-auto flex w-full max-w-7xl items-center justify-between px-6 py-6 lg:px-10">
      <Link href="/" className="text-lg font-semibold tracking-[0.2em] text-white">
        {t("brand")}
      </Link>
      <div className="flex items-center gap-3">
        <nav className="hidden items-center gap-2 md:flex">
          {!isLoggedIn ? (
            <Link
              href="/login"
              className="rounded-full px-4 py-2 text-sm text-white/75 transition hover:bg-white/6 hover:text-white"
            >
              {t("login")}
            </Link>
          ) : (
            <div className="flex items-center gap-2">
              <Link
                href="/settings"
                className="rounded-full px-4 py-2 text-sm text-white/75 transition hover:bg-white/6 hover:text-white"
              >
                {t("settings")}
              </Link>
              <button
                type="button"
                onClick={() => {
                  authStorage.clear();
                  router.push("/login");
                }}
                className="rounded-full px-4 py-2 text-sm text-rose-400/80 transition hover:bg-rose-500/10 hover:text-rose-400"
              >
                {t("logout", { fallback: "Logout" })}
              </button>
            </div>
          )}
          <Link
            href={isLoggedIn ? "/app" : "/login"}
            className="rounded-full px-5 py-2 text-sm font-medium text-cyan-400 bg-cyan-400/10 border border-cyan-400/20 transition hover:bg-cyan-400/20"
          >
            {t("launch")}
          </Link>
        </nav>
        <LanguageSwitcher />
      </div>
    </header>
  );
}
