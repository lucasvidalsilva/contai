import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import "@fontsource-variable/bricolage-grotesque/wdth.css";
import "@fontsource/ibm-plex-mono/latin-400.css";
import "@fontsource/ibm-plex-mono/latin-500.css";
import "./globals.css";

const deploymentHost =
	process.env.VERCEL_PROJECT_PRODUCTION_URL ?? process.env.VERCEL_URL;

export const metadata: Metadata = {
	metadataBase: new URL(
		deploymentHost ? `https://${deploymentHost}` : "http://localhost:3000",
	),
	title: "contAI — engenharia fiscal da fonte à evidência",
	description:
		"Pipeline tributária em Python, PostgreSQL versionado e motor fiscal offline para transformar NF-e em alertas com evidências reproduzíveis.",
	applicationName: "contAI",
	keywords: [
		"NF-e",
		"conferência fiscal",
		"contador",
		"NCM",
		"TIPI",
		"reforma tributária",
		"IBS e CBS",
		"Python",
		"PostgreSQL",
		"engenharia de dados",
	],
	robots: { index: true, follow: true },
	openGraph: {
		title: "contAI: da fonte oficial à divergência na NF-e",
		description:
			"Um sistema de ponta a ponta: fontes oficiais, pipeline em Python, PostgreSQL e regras fiscais determinísticas com evidências.",
		locale: "pt_BR",
		type: "website",
	},
	twitter: {
		card: "summary_large_image",
		title: "contAI: da fonte oficial à divergência na NF-e",
		description:
			"Pipeline tributária, PostgreSQL versionado e motor fiscal offline com limites explícitos.",
	},
};

export const viewport: Viewport = {
	themeColor: "#f5f7fa",
};

export default function RootLayout({
	children,
}: Readonly<{ children: ReactNode }>) {
	return (
		<html lang="pt-BR">
			<body>{children}</body>
		</html>
	);
}
