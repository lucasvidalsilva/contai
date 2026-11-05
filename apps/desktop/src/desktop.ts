import { Channel, invoke } from "@tauri-apps/api/core";

import type { AnalysisProgress, BatchAnalysis, CommandErrorPayload } from "./types";

export async function pickAndAnalyzeDocuments(
  onProgress: (progress: AnalysisProgress) => void,
): Promise<BatchAnalysis | null> {
  const progressChannel = new Channel<AnalysisProgress>();
  progressChannel.onmessage = onProgress;
  return invoke<BatchAnalysis | null>("pick_and_analyze_documents", {
    onProgress: progressChannel,
  });
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
