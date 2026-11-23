/** @type {import('next').NextConfig} */
const nextConfig = {
  // ── Tree-shake large icon/chart libraries at build time ──────────────────
  experimental: {
    optimizePackageImports: ["lucide-react", "recharts"],
  },

  // ── Image optimization ───────────────────────────────────────────────────
  images: {
    remotePatterns: [
      { protocol: "http",  hostname: "localhost" },
      { protocol: "https", hostname: "**" },
    ],
  },

  // ── API proxy to FastAPI backend ─────────────────────────────────────────
  async rewrites() {
    return [
      {
        source:      "/api/backend/:path*",
        destination: `${process.env.BACKEND_API_URL || "http://127.0.0.1:8000"}/api/v1/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
