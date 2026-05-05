import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "**",
      },
    ],
  },
  // Allow loading JupyterLite iframe
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          {
            key: "Content-Security-Policy",
            value: "frame-src 'self' https://jupyterlite.github.io https://*.jupyterlite.github.io;",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
