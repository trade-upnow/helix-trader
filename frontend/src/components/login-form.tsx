"use client";

import { useEffect, useState, useTransition } from "react";
import { useTranslations } from "next-intl";

import { useRouter } from "@/i18n/navigation";
import { apiRequest, authStorage } from "@/lib/api";

type LoginResponse = {
  access_token: string;
  token_type: string;
};

export function LoginForm() {
  const t = useTranslations("login");
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const busy = loading || isPending;

  useEffect(() => {
    if (!authStorage.getToken()) {
      return;
    }

    startTransition(() => {
      router.replace("/app");
      router.refresh();
    });
  }, [router, startTransition]);

  async function runLogin() {
    if (busy) {
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const payload = await apiRequest<LoginResponse>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });

      authStorage.setToken(payload.access_token);
      startTransition(() => {
        router.push("/app");
        router.refresh();
      });
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Login failed",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <form
      className="bg-[#0F172A] border border-white/10 shadow-2xl w-full max-w-lg rounded-[2.5rem] p-8 md:p-10"
      method="post"
      onSubmit={(event) => {
        event.preventDefault();
        void runLogin();
      }}
    >
      <div className="space-y-2">
        <h1 className="text-3xl font-semibold">{t("title")}</h1>
        <p className="text-sm leading-7 text-muted">{t("subtitle")}</p>
      </div>

      <div className="mt-8 space-y-5">
        <label className="block">
          <span className="mb-2 block text-sm text-white/70">{t("username")}</span>
          <input
            className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 outline-none focus:border-cyan-400/50"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
          />
        </label>
        <label className="block">
          <span className="mb-2 block text-sm text-white/70">{t("password")}</span>
          <input
            type="password"
            className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 outline-none focus:border-cyan-400/50"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
      </div>

      {error ? (
        <p className="mt-4 rounded-2xl border border-rose-400/20 bg-rose-400/10 px-4 py-3 text-sm text-rose-100">
          {error}
        </p>
      ) : null}

      <button
        type="button"
        disabled={busy}
        onClick={() => void runLogin()}
        className="mt-8 w-full rounded-2xl bg-cyan-400 px-5 py-4 font-bold text-lg text-slate-950 transition-all hover:bg-cyan-300 disabled:opacity-70 shadow-[0_0_20px_rgba(6,182,212,0.4)] hover:shadow-[0_0_30px_rgba(6,182,212,0.6)] hover:-translate-y-1"
      >
        {busy ? "..." : t("submit")}
      </button>

      <p className="mt-4 text-center text-sm text-muted">{t("hint")}</p>
    </form>
  );
}
