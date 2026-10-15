import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  // cacheComponents (Next 16's experimental PPR successor) was the
  // create-next-app default but stalls client-side hydration on plain
  // "use client" + useQuery pages like /jobs — too unstable for this
  // project right now. Revisit once it's stable.
  // The API is reached through this server (`/api/...` → Django), so the app
  // works from one address: localhost, or a tunnel like ngrok shared with
  // someone else, whose browser can't reach this laptop's localhost:8000.
  // Django's URLs end in "/", so Next must not strip trailing slashes.
  skipTrailingSlashRedirect: true,
  async rewrites() {
    const target = process.env.API_PROXY_TARGET ?? "http://localhost:8000";
    return [
      // The trailing-slash form first: `:path*` alone would drop the slash.
      { source: "/api/:path*/", destination: `${target}/api/:path*/` },
      { source: "/api/:path*", destination: `${target}/api/:path*` },
    ];
  },
  // ngrok's free tunnel addresses, so the dev server serves its assets there.
  allowedDevOrigins: ["*.ngrok-free.app", "*.ngrok-free.dev", "*.ngrok.app"],
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
