import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Enable standalone output for Docker (copies only needed files)
  output: "standalone",
};

export default nextConfig;
