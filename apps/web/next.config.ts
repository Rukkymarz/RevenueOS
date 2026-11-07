import type { NextConfig } from "next";
const nextConfig: NextConfig = {
  output: process.env.VERCEL || process.env.NETLIFY ? undefined : "standalone",
  reactStrictMode: true,
  serverExternalPackages: ["ffmpeg-static"],
  outputFileTracingIncludes: {"/api/v1/*": ["./assets/fonts/**", "./node_modules/ffmpeg-static/ffmpeg"]},
  async headers() {
    return [{ source: "/(.*)", headers: [
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
      { key: "X-Frame-Options", value: "DENY" },
      { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
      { key: "Content-Security-Policy", value: "base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'" },
    ] }];
  },
};
export default nextConfig;
