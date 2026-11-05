import { Channel, invoke } from "@tauri-apps/api/core";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { describeError, pickAndAnalyzeDocuments } from "./desktop";
import type { AnalysisProgress, AnalysisReport, BatchAnalysis } from "./types";

vi.mock("@tauri-apps/api/core", () => ({
  Channel: class MockChannel<T> {
    onmessage?: (message: T) => void;
  },
  invoke: vi.fn(),
}));

const report: AnalysisReport = {
  contract_version: "fiscal-engine-v1",
  status: "analyzed",
  document_model: "55",
  issue_date: "2026-10-30",
  ncm_release_id: null,
  alerts: [],
};

const batch: BatchAnalysis = {
  sourceName: "lote-sintetico.zip",
  documents: [{ fileName: "nfe-sintetica.xml", report }],
  duplicateFiles: [],
};

describe("desktop bridge", () => {
  beforeEach(() => vi.clearAllMocks());

  it("streams ordered progress and returns a batch without receiving full paths", async () => {
    const progress: AnalysisProgress[] = [];
    vi.mocked(invoke).mockImplementation(async (_command, args) => {
      const channel = (args as { onProgress: Channel<AnalysisProgress> }).onProgress;
      channel.onmessage?.({ processed: 0, total: 1, fileName: null });
      channel.onmessage?.({ processed: 1, total: 1, fileName: "nfe-sintetica.xml" });
      return batch;
    });

    const result = await pickAndAnalyzeDocuments((update) => progress.push(update));

    expect(invoke).toHaveBeenCalledWith("pick_and_analyze_documents", {
      onProgress: expect.any(Channel),
    });
    expect(progress).toEqual([
      { processed: 0, total: 1, fileName: null },
      { processed: 1, total: 1, fileName: "nfe-sintetica.xml" },
    ]);
    expect(result).toEqual(batch);
    expect(JSON.stringify(result)).not.toContain("clientes");
  });

  it("returns null when the native selection is cancelled", async () => {
    vi.mocked(invoke).mockResolvedValue(null);

    expect(await pickAndAnalyzeDocuments(vi.fn())).toBeNull();
    expect(invoke).toHaveBeenCalledOnce();
  });

  it("uses a sanitized backend message when available", () => {
    expect(describeError({ code: "engine_unavailable", message: "Motor indisponível." })).toBe(
      "Motor indisponível.",
    );
    expect(describeError(new Error())).toBe("O aplicativo não conseguiu concluir a análise local.");
  });
});
