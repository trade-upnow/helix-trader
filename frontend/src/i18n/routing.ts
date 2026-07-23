import { defineRouting } from "next-intl/routing";

export const routing = defineRouting({
  locales: ["ko", "zh-CN", "en", "es"],
  defaultLocale: "ko",
  localePrefix: "always",
});

export type AppLocale = (typeof routing.locales)[number];
