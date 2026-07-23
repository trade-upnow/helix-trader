import { routing } from "@/i18n/routing";

function resolveApiBaseUrl(): string {
  const raw = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (typeof raw === "string" && raw.trim() !== "") {
    return raw.trim().replace(/\/$/, "");
  }
  // 默认走相对路径 /api → 由 next.config rewrites 转到后端（本地开发更省事）
  return "";
}

const API_BASE_URL = resolveApiBaseUrl();
const AUTH_TOKEN_EVENT = "helix-auth-token-change";

function redirectToLogin() {
  if (typeof window === "undefined") {
    return;
  }

  const [, maybeLocale] = window.location.pathname.split("/");
  const locale = routing.locales.includes(maybeLocale as (typeof routing.locales)[number])
    ? maybeLocale
    : routing.defaultLocale;
  const loginPath = `/${locale}/login`;

  if (window.location.pathname !== loginPath) {
    window.location.replace(loginPath);
  }
}

type RequestOptions = RequestInit & {
  token?: string | null;
};

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { token, headers, ...rest } = options;

  const url =
    API_BASE_URL === "" ? path : `${API_BASE_URL}${path}`;

  const response = await fetch(url, {
    ...rest,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as
      | { detail?: string }
      | null;

    if (response.status === 401) {
      authStorage.clear();
      redirectToLogin();
    }

    throw new Error(payload?.detail ?? "Request failed");
  }

  return response.json() as Promise<T>;
}

export const authStorage = {
  getToken() {
    if (typeof window === "undefined") {
      return null;
    }

    return window.localStorage.getItem("helix_token");
  },
  setToken(token: string) {
    if (typeof window !== "undefined") {
      window.localStorage.setItem("helix_token", token);
      window.dispatchEvent(new Event(AUTH_TOKEN_EVENT));
    }
  },
  clear() {
    if (typeof window !== "undefined") {
      window.localStorage.removeItem("helix_token");
      window.dispatchEvent(new Event(AUTH_TOKEN_EVENT));
    }
  },
  subscribe(listener: () => void) {
    if (typeof window === "undefined") {
      return () => undefined;
    }

    const handleStorage = (event: StorageEvent) => {
      if (event.key === "helix_token") {
        listener();
      }
    };

    window.addEventListener("storage", handleStorage);
    window.addEventListener(AUTH_TOKEN_EVENT, listener);

    return () => {
      window.removeEventListener("storage", handleStorage);
      window.removeEventListener(AUTH_TOKEN_EVENT, listener);
    };
  },
};
