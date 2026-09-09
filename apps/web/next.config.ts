import type { NextConfig } from "next";
const nextConfig: NextConfig = {
  transpilePackages: ["@atm/schema", "@atm/ui"],
  experimental: { serverActions: { bodySizeLimit: "2mb" } },
};
export default nextConfig;
