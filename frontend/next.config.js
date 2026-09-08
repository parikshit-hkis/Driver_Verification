/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/api/gateway/:path*",
        destination: "http://127.0.0.1:8000/api/v1/:path*",
      },
      {
        source: "/api/health",
        destination: "http://127.0.0.1:8000/health",
      },
    ];
  },
};

module.exports = nextConfig;
