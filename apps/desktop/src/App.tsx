import { useState } from "react";

import { describeError, pickAndAnalyzeInvoice } from "./desktop";
import { formatIssueDate, severityLabel } from "./format";
import type { AnalysisResult, Alert } from "./types";
import "./App.css";

type ViewState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "result"; analysis: AnalysisResult }
  | { kind: "error"; message: string };

function ResultStatus({ analysis }: { analysis: AnalysisResult }) {
  const { report } = analysis;
  const hasError = report.status === "rejected" || report.alerts.some((alert) => alert.severity === "error");
  const hasWarning = report.alerts.some((alert) => alert.severity === "warning");
  const tone = hasError ? "danger" : hasWarning ? "attention" : "success";
  const title = hasError
    ? "Documento rejeitado"
    : hasWarning
      ? "Conferência concluída com alertas"
      : "Conferência concluída";

  return (
    <section className={`result-status result-status--${tone}`} aria-live="polite">
      <div className="result-status__icon" aria-hidden="true">
        {hasError ? "×" : hasWarning ? "!" : "✓"}
      </div>
      <div>
        <p className="eyebrow">Resultado local</p>
        <h2>{title}</h2>
        <p>
          {analysis.fileName} · {report.alerts.length} {report.alerts.length === 1 ? "alerta" : "alertas"}
        </p>
      </div>
    </section>
  );
}

function Summary({ analysis }: { analysis: AnalysisResult }) {
  const { report } = analysis;
  return (
    <dl className="summary-grid" aria-label="Resumo da análise">
      <div>
        <dt>Documento</dt>
        <dd>{analysis.fileName}</dd>
      </div>
      <div>
        <dt>Modelo</dt>
        <dd>{report.document_model ?? "Não identificado"}</dd>
      </div>
      <div>
        <dt>Emissão</dt>
        <dd>{formatIssueDate(report.issue_date)}</dd>
      </div>
      <div>
        <dt>Motor</dt>
        <dd>{report.contract_version}</dd>
      </div>
    </dl>
  );
}

function AlertCard({ alert }: { alert: Alert }) {
  return (
    <article className={`alert-card alert-card--${alert.severity}`}>
      <div className="alert-card__heading">
        <span className="severity">{severityLabel(alert.severity)}</span>
        <code>{alert.rule_id}</code>
      </div>
      <h3>{alert.message}</h3>
      {alert.field_path && <p className="field-path">Campo: {alert.field_path}</p>}
      {alert.evidence.length > 0 && (
        <ul className="evidence-list" aria-label="Evidências da regra">
          {alert.evidence.map((evidence) => (
            <li key={evidence}>{evidence}</li>
          ))}
        </ul>
      )}
    </article>
  );
}

function App() {
  const [state, setState] = useState<ViewState>({ kind: "idle" });

  async function selectInvoice() {
    setState({ kind: "loading" });
    try {
      const analysis = await pickAndAnalyzeInvoice();
      setState(analysis ? { kind: "result", analysis } : { kind: "idle" });
    } catch (error) {
      setState({ kind: "error", message: describeError(error) });
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#main" aria-label="contAI — início">
          cont<span>AI</span>
        </a>
        <div className="local-badge">
          <span aria-hidden="true" />
          Processamento local
        </div>
      </header>

      <main id="main" className="workspace">
        <section className="intro">
          <p className="eyebrow">Conferência fiscal</p>
          <h1>Revise uma NF-e com evidências objetivas.</h1>
          <p>
            Selecione um XML de NF-e modelo 55. O arquivo permanece neste computador e é avaliado somente pelas
            verificações disponíveis no motor fiscal.
          </p>
        </section>

        {state.kind === "idle" && (
          <section className="import-panel">
            <div className="file-mark" aria-hidden="true">
              XML
            </div>
            <div>
              <h2>Escolha uma nota fiscal</h2>
              <p>Arquivo XML · até 2 MB · uma nota por vez neste primeiro corte</p>
            </div>
            <button className="primary-button" type="button" onClick={selectInvoice}>
              Selecionar XML
            </button>
          </section>
        )}

        {state.kind === "loading" && (
          <section className="import-panel import-panel--loading" aria-live="polite">
            <div className="spinner" aria-hidden="true" />
            <div>
              <h2>Analisando localmente…</h2>
              <p>Validando estrutura e executando as regras disponíveis.</p>
            </div>
          </section>
        )}

        {state.kind === "error" && (
          <section className="error-panel" role="alert">
            <p className="eyebrow">Não foi possível analisar</p>
            <h2>{state.message}</h2>
            <p>Nenhum conteúdo do XML foi enviado ou persistido pelo contAI.</p>
            <button className="secondary-button" type="button" onClick={selectInvoice}>
              Tentar novamente
            </button>
          </section>
        )}

        {state.kind === "result" && (
          <div className="results">
            <ResultStatus analysis={state.analysis} />
            <Summary analysis={state.analysis} />

            <section className="alerts-section">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">Pendências encontradas</p>
                  <h2>Alertas para revisão</h2>
                </div>
                <button className="secondary-button" type="button" onClick={selectInvoice}>
                  Analisar outro XML
                </button>
              </div>

              {state.analysis.report.alerts.length === 0 ? (
                <div className="empty-alerts">
                  <strong>Nenhuma divergência nas verificações executadas.</strong>
                  <p>Isso não representa conformidade fiscal integral. Revise os limites do motor antes de decidir.</p>
                </div>
              ) : (
                <div className="alert-list">
                  {state.analysis.report.alerts.map((alert, index) => (
                    <AlertCard key={`${alert.rule_id}-${index}`} alert={alert} />
                  ))}
                </div>
              )}
            </section>
          </div>
        )}
      </main>

      <footer>
        <strong>Privacidade por padrão.</strong> O contAI não envia o XML para servidores no fluxo de conferência.
      </footer>
    </div>
  );
}

export default App;
