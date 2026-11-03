import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import App from "./App";
import { pickAndAnalyzeInvoice } from "./desktop";
import type { AnalysisResult } from "./types";

vi.mock("./desktop", () => ({
  pickAndAnalyzeInvoice: vi.fn(),
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

beforeEach(() => vi.clearAllMocks());

it("starts with a local XML selection action", () => {
  render(<App />);

  expect(screen.getByRole("button", { name: "Selecionar XML" })).toBeVisible();
  expect(screen.getByText("Processamento local")).toBeVisible();
  expect(screen.getByRole("navigation", { name: "Navegação principal" })).toBeVisible();
});

it("keeps an explicit loading state while the local engine is running", async () => {
  let finishAnalysis: ((analysis: AnalysisResult) => void) | undefined;
  vi.mocked(pickAndAnalyzeInvoice).mockImplementation(
    () =>
      new Promise((resolve) => {
        finishAnalysis = resolve;
      }),
  );
  const user = userEvent.setup();
  render(<App />);

  await user.click(screen.getByRole("button", { name: "Selecionar XML" }));

  expect(screen.getByRole("heading", { name: "Analisando o documento…" })).toBeVisible();
  finishAnalysis?.(successfulAnalysis);
  expect(await screen.findByRole("heading", { name: "Conferência concluída" })).toBeVisible();
});

it("returns to the idle workspace when native selection is cancelled", async () => {
  vi.mocked(pickAndAnalyzeInvoice).mockResolvedValue(null);
  const user = userEvent.setup();
  render(<App />);

  await user.click(screen.getByRole("button", { name: "Selecionar XML" }));

  expect(await screen.findByRole("button", { name: "Selecionar XML" })).toBeVisible();
  expect(screen.queryByText("Relatório de conferência")).not.toBeInTheDocument();
});

it("renders a successful deterministic report", async () => {
  vi.mocked(pickAndAnalyzeInvoice).mockResolvedValue(successfulAnalysis);
  const user = userEvent.setup();
  render(<App />);

  await user.click(screen.getByRole("button", { name: "Selecionar XML" }));

  expect(await screen.findByRole("heading", { name: "Conferência concluída" })).toBeVisible();
  expect(screen.getByText("nfe-synthetic-55.xml")).toBeVisible();
  expect(screen.getByText("Nenhuma divergência nas verificações executadas.")).toBeVisible();
});

it("renders alert evidence for professional review", async () => {
  vi.mocked(pickAndAnalyzeInvoice).mockResolvedValue({
    ...successfulAnalysis,
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
  });
  const user = userEvent.setup();
  render(<App />);

  await user.click(screen.getByRole("button", { name: "Selecionar XML" }));

  expect(await screen.findByRole("heading", { name: "Conferência concluída com alertas" })).toBeVisible();
  expect(screen.getByText("NFE-TOTAL-PROD-001")).toBeVisible();
  expect(screen.getByText("total_declarado=11.00")).toBeVisible();
});

it("distinguishes a rejected document from an analyzed document", async () => {
  vi.mocked(pickAndAnalyzeInvoice).mockResolvedValue({
    ...successfulAnalysis,
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
  });
  const user = userEvent.setup();
  render(<App />);

  await user.click(screen.getByRole("button", { name: "Selecionar XML" }));

  expect(await screen.findByRole("heading", { name: "Documento rejeitado" })).toBeVisible();
  expect(screen.getByText("XML-PARSE-001")).toBeVisible();
});

it("shows a sanitized local error and offers retry", async () => {
  vi.mocked(pickAndAnalyzeInvoice).mockRejectedValue({ message: "O motor fiscal local não pôde ser iniciado." });
  const user = userEvent.setup();
  render(<App />);

  await user.click(screen.getByRole("button", { name: "Selecionar XML" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("O motor fiscal local não pôde ser iniciado.");
  expect(screen.getByRole("button", { name: "Tentar novamente" })).toBeVisible();
});
