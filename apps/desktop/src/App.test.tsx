import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import App from "./App";
import { pickAndAnalyzeDocuments } from "./desktop";
import type { AnalysisResult, BatchAnalysis } from "./types";

vi.mock("./desktop", () => ({
  pickAndAnalyzeDocuments: vi.fn(),
  describeError: (error: unknown) =>
    typeof error === "object" && error !== null && "message" in error
      ? String(error.message)
      : "Falha local.",
}));

const successfulAnalysis: AnalysisResult = {
  fileName: "nfe-synthetic-55.xml",
  report: {
    contract_version: "fiscal-engine-v1",
    status: "analyzed",
    document_model: "55",
    issue_date: "2026-10-30",
    ncm_release_id: null,
    alerts: [],
  },
};

const successfulBatch: BatchAnalysis = {
  sourceName: "nfe-synthetic-55.xml",
  documents: [successfulAnalysis],
  duplicateFiles: [],
};

beforeEach(() => vi.clearAllMocks());

it("starts with a local XML or ZIP selection action", () => {
  render(<App />);

  expect(screen.getByRole("button", { name: "Selecionar XML ou ZIP" })).toBeVisible();
  expect(screen.getByText("Processamento local")).toBeVisible();
  expect(screen.getByRole("navigation", { name: "Navegação principal" })).toBeVisible();
});

it("shows actual batch progress while the local engine is running", async () => {
  let finishAnalysis: ((batch: BatchAnalysis) => void) | undefined;
  vi.mocked(pickAndAnalyzeDocuments).mockImplementation(
    (onProgress) =>
      new Promise((resolve) => {
        onProgress({ processed: 0, total: 3, fileName: null });
        onProgress({ processed: 1, total: 3, fileName: "primeira.xml" });
        finishAnalysis = resolve;
      }),
  );
  const user = userEvent.setup();
  render(<App />);

  await user.click(screen.getByRole("button", { name: "Selecionar XML ou ZIP" }));

  expect(screen.getByRole("heading", { name: "Analisando o lote…" })).toBeVisible();
  expect(screen.getByText("1 de 3")).toBeVisible();
  expect(screen.getByText("primeira.xml")).toBeVisible();
  expect(screen.getByRole("progressbar")).toHaveAttribute("value", "1");
  finishAnalysis?.(successfulBatch);
  expect(await screen.findByRole("heading", { name: "Conferência concluída" })).toBeVisible();
});

it("returns to the idle workspace when native selection is cancelled", async () => {
  vi.mocked(pickAndAnalyzeDocuments).mockResolvedValue(null);
  const user = userEvent.setup();
  render(<App />);

  await user.click(screen.getByRole("button", { name: "Selecionar XML ou ZIP" }));

  expect(await screen.findByRole("button", { name: "Selecionar XML ou ZIP" })).toBeVisible();
  expect(screen.queryByText("Resultado por documento")).not.toBeInTheDocument();
});

it("renders a successful deterministic report", async () => {
  vi.mocked(pickAndAnalyzeDocuments).mockResolvedValue(successfulBatch);
  const user = userEvent.setup();
  render(<App />);

  await user.click(screen.getByRole("button", { name: "Selecionar XML ou ZIP" }));

  expect(await screen.findByRole("heading", { name: "Conferência concluída" })).toBeVisible();
  expect(screen.getAllByText("nfe-synthetic-55.xml").length).toBeGreaterThan(0);
  expect(screen.getByText("Nenhuma divergência nas verificações executadas.")).toBeVisible();
});

it("renders every document, duplicate count and alert evidence from a ZIP", async () => {
  const warning: AnalysisResult = {
    ...successfulAnalysis,
    fileName: "nfe-com-alerta.xml",
    report: {
      ...successfulAnalysis.report,
      alerts: [
        {
          rule_id: "NFE-TOTAL-PROD-001",
          rule_version: "1.0.0",
          severity: "warning",
          code: "product_total_mismatch",
          message: "A soma dos itens diverge do total declarado.",
          field_path: "NFe/infNFe/total/ICMSTot/vProd",
          evidence: ["soma_dos_itens=10.00", "total_declarado=11.00"],
        },
      ],
    },
  };
  vi.mocked(pickAndAnalyzeDocuments).mockResolvedValue({
    sourceName: "lote-sintetico.zip",
    documents: [successfulAnalysis, warning],
    duplicateFiles: ["copia.xml"],
  });
  const user = userEvent.setup();
  render(<App />);

  await user.click(screen.getByRole("button", { name: "Selecionar XML ou ZIP" }));

  const resultHeading = await screen.findByRole("heading", {
    name: "Conferência concluída com alertas",
  });
  expect(resultHeading).toBeVisible();
  expect(resultHeading.closest("section")).toHaveTextContent("2 documentos");
  expect(screen.getByText("1 duplicado ignorado")).toBeVisible();
  expect(screen.getByText("copia.xml")).toBeVisible();
  expect(screen.getByText("nfe-com-alerta.xml")).toBeVisible();

  await user.click(screen.getByText("nfe-com-alerta.xml"));
  expect(screen.getByText("NFE-TOTAL-PROD-001")).toBeVisible();
  expect(screen.getByText("total_declarado=11.00")).toBeVisible();
});

it("distinguishes a rejected document inside a batch", async () => {
  vi.mocked(pickAndAnalyzeDocuments).mockResolvedValue({
    sourceName: "rejeitada.xml",
    duplicateFiles: [],
    documents: [
      {
        ...successfulAnalysis,
        fileName: "rejeitada.xml",
        report: {
          ...successfulAnalysis.report,
          status: "rejected",
          document_model: null,
          alerts: [
            {
              rule_id: "XML-PARSE-001",
              rule_version: "1.0.0",
              severity: "error",
              code: "document_rejected",
              message: "O documento não pôde ser interpretado como uma NF-e.",
              field_path: null,
              evidence: ["motivo=xml_malformado"],
            },
          ],
        },
      },
    ],
  });
  const user = userEvent.setup();
  render(<App />);

  await user.click(screen.getByRole("button", { name: "Selecionar XML ou ZIP" }));

  expect(
    await screen.findByRole("heading", { name: "Conferência concluída com rejeições" }),
  ).toBeVisible();
  expect(screen.getByText("XML-PARSE-001")).toBeVisible();
});

it("shows a sanitized local error and offers retry", async () => {
  vi.mocked(pickAndAnalyzeDocuments).mockRejectedValue({
    message: "O motor fiscal local não pôde ser iniciado.",
  });
  const user = userEvent.setup();
  render(<App />);

  await user.click(screen.getByRole("button", { name: "Selecionar XML ou ZIP" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("O motor fiscal local não pôde ser iniciado.");
  expect(screen.getByRole("button", { name: "Tentar novamente" })).toBeVisible();
});
