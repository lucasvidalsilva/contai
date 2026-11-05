import type { NextConfig } from "next";

const nextConfig: NextConfig = {
	agentRules: false,
	poweredByHeader: false,
	reactStrictMode: true,
	turbopack: {
		root: process.cwd(),
	},
	async headers() {
		return [
			{
				source: "/(.*)",
				headers: [
					{ key: "X-Content-Type-Options", value: "nosniff" },
					{ key: "X-Frame-Options", value: "DENY" },
					{ key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
					{
						key: "Permissions-Policy",
						value: "camera=(), geolocation=(), microphone=()",
					},
				],
			},
		];
	},
};

export default nextConfig;
