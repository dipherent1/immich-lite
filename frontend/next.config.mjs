// Plain .mjs (not .ts) on purpose: the production image runs `next start` with
// devDependencies pruned, so a TypeScript config couldn't be loaded there — and
// the runner stage must copy this file for the settings below to apply at runtime.

/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    // Uploads go browser -> Next (the rewrite below) -> API. Next buffers proxied
    // request bodies and silently truncates them at 10MB by default, which
    // corrupts multi-photo uploads. The browser sends <= ~40MB per request.
    proxyClientMaxBodySize: "100mb",
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.INTERNAL_API_URL || "http://app:8000"}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
