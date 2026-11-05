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
		"Aplicativo fiscal em desenvolvimento com pipeline Python, PostgreSQL versionado, motor offline e conector de IA planejado.",
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
			"Aplicativo em desenvolvimento: fontes oficiais, pipeline Python, PostgreSQL, regras fiscais e conector de IA planejado.",
		locale: "pt_BR",
		type: "website",
	},
	twitter: {
		card: "summary_large_image",
		title: "contAI: da fonte oficial à divergência na NF-e",
		description:
			"Aplicativo fiscal em desenvolvimento com motor offline e conector de IA planejado.",
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
