import { invoke } from "@tauri-apps/api/core";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { describeError, pickAndAnalyzeInvoice } from "./desktop";
import type { AnalysisReport } from "./types";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));

const report: AnalysisReport = {
  contract_version: "fiscal-engine-v1",
  status: "analyzed",
  document_model: "55",
  issue_date: "2026-10-30",
  ncm_release_id: null,
  alerts: [],
};

describe("desktop bridge", () => {
  beforeEach(() => vi.clearAllMocks());

  it("asks Rust to select and analyze without receiving a full path", async () => {
    vi.mocked(invoke).mockResolvedValue({ fileName: "nfe-sintetica.xml", report });

    const result = await pickAndAnalyzeInvoice();

    expect(invoke).toHaveBeenCalledWith("pick_and_analyze_invoice");
    expect(result).toEqual({ fileName: "nfe-sintetica.xml", report });
    expect(JSON.stringify(result)).not.toContain("clientes");
  });

  it("returns null when the native selection is cancelled", async () => {
    vi.mocked(invoke).mockResolvedValue(null);

    expect(await pickAndAnalyzeInvoice()).toBeNull();
    expect(invoke).toHaveBeenCalledOnce();
  });

  it("uses a sanitized backend message when available", () => {
    expect(describeError({ code: "engine_unavailable", message: "Motor indisponível." })).toBe(
      "Motor indisponível.",
    );
    expect(describeError(new Error())).toBe("O aplicativo não conseguiu concluir a análise local.");
  });
});
