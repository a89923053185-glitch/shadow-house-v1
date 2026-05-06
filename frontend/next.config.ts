import type { NextConfig } from "next";

function apiRewriteDestination() {
  const explicitProxyTarget = process.env.API_PROXY_TARGET || process.env.BACKEND_PUBLIC_URL || "http://backend:8000";

  const baseUrl = explicitProxyTarget.replace(/\/$/, "").replace(/\/api\/v1$/, "");
  return `${baseUrl}/api/v1/:path*`;
}

const nextConfig: NextConfig = {
  async rewrites() {
    const destination = apiRewriteDestination();

    return [
      {
        source: "/api/v1/:path*",
        destination,
      },
    ];
  },
};

export default nextConfig;
