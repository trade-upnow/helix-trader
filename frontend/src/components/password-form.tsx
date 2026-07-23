"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

import { apiRequest, authStorage } from "@/lib/api";

export function PasswordForm() {
  const t = useTranslations("settings");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  return (
    <form
      className="bg-[#0F172A] border border-white/10 shadow-2xl w-full max-w-xl rounded-[2.5rem] p-8 md:p-10"
      onSubmit={async (event) => {
        event.preventDefault();
        setMessage(null);
        setError(null);

        if (newPassword !== confirmPassword) {
          setError("Passwords do not match");
          return;
        }

        try {
          await apiRequest("/api/auth/password", {
            method: "PUT",
            token: authStorage.getToken(),
            body: JSON.stringify({
              current_password: currentPassword,
              new_password: newPassword,
            }),
          });
          setMessage("Password updated");
          setCurrentPassword("");
          setNewPassword("");
          setConfirmPassword("");
        } catch (requestError) {
          setError(
            requestError instanceof Error
              ? requestError.message
              : "Password update failed",
          );
        }
      }}
    >
      <h1 className="text-3xl font-semibold">{t("title")}</h1>
      <div className="mt-8 space-y-5">
        <label className="block">
          <span className="mb-2 block text-sm text-white/70">
            {t("currentPassword")}
          </span>
          <input
            type="password"
            value={currentPassword}
            onChange={(event) => setCurrentPassword(event.target.value)}
            className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 outline-none"
          />
        </label>
        <label className="block">
          <span className="mb-2 block text-sm text-white/70">
            {t("newPassword")}
          </span>
          <input
            type="password"
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
            className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 outline-none"
          />
        </label>
        <label className="block">
          <span className="mb-2 block text-sm text-white/70">
            {t("confirmPassword")}
          </span>
          <input
            type="password"
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
            className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 outline-none"
          />
        </label>
      </div>

      {message ? (
        <p className="mt-5 rounded-2xl border border-emerald-400/20 bg-emerald-400/10 px-4 py-3 text-sm text-emerald-100">
          {message}
        </p>
      ) : null}
      {error ? (
        <p className="mt-5 rounded-2xl border border-rose-400/20 bg-rose-400/10 px-4 py-3 text-sm text-rose-100">
          {error}
        </p>
      ) : null}

      <button
        type="submit"
        className="mt-8 w-full rounded-2xl bg-cyan-400 px-5 py-4 font-bold text-lg text-slate-950 transition-all hover:bg-cyan-300 shadow-[0_0_20px_rgba(6,182,212,0.4)] hover:shadow-[0_0_30px_rgba(6,182,212,0.6)] hover:-translate-y-1"
      >
        {t("submit")}
      </button>
    </form>
  );
}
