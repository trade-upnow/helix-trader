import createNextIntlPlugin from "next-intl/plugin";
import type { NextConfig } from "next";

/** 浏览器走同源 /api/* 时，由 Next 转发到后端，避免 CORS，且 Network 里能看到对 3000 的请求。 */
const backendProxyTarget =
  process.env.BACKEND_PROXY_URL?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  typedRoutes: true,
  allowedDevOrigins: ["127.0.0.1"],
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendProxyTarget}/api/:path*`,
      },
    ];
  },
};

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

export default withNextIntl(nextConfig);
