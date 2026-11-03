import { invoke } from "@tauri-apps/api/core";

import type { AnalysisResult, CommandErrorPayload } from "./types";

export async function pickAndAnalyzeInvoice(): Promise<AnalysisResult | null> {
  return invoke<AnalysisResult | null>("pick_and_analyze_invoice");
}

export function describeError(error: unknown): string {
  if (typeof error === "object" && error !== null && "message" in error) {
    const candidate = error as Partial<CommandErrorPayload>;
    if (typeof candidate.message === "string" && candidate.message.length > 0) {
      return candidate.message;
    }
  }
  return "O aplicativo não conseguiu concluir a análise local.";
}
