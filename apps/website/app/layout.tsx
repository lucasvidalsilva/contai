import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

const deploymentHost = process.env.VERCEL_PROJECT_PRODUCTION_URL ?? process.env.VERCEL_URL;

export const metadata: Metadata = {
  metadataBase: new URL(deploymentHost ? `https://${deploymentHost}` : "http://localhost:3000"),
  title: "contAI — Inteligência fiscal com evidências",
  description:
    "Conferência local de NF-e com regras determinísticas, fontes rastreáveis e evidências para revisão profissional.",
  applicationName: "contAI",
  keywords: ["NF-e", "conferência fiscal", "contador", "inteligência fiscal", "auditoria fiscal"],
  robots: { index: true, follow: true },
  openGraph: {
    title: "contAI — Fiscal, com evidências.",
    description:
      "Transforme lotes de NF-e em conferências objetivas e pendências que o contador consegue revisar.",
    locale: "pt_BR",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "contAI — Fiscal, com evidências.",
    description: "Conferência local de NF-e com regras determinísticas e evidências revisáveis.",
  },
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
