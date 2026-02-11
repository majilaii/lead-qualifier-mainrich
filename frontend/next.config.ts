import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // "standalone" is only needed for Docker; Vercel handles builds natively.
  // Set OUTPUT_MODE=standalone in Docker env to re-enable if needed.
  ...(process.env.OUTPUT_MODE === "standalone" ? { output: "standalone" as const } : {}),
};

export default nextConfig;
