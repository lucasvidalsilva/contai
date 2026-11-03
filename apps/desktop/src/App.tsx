import { useState, type ReactNode } from "react";

import { describeError, pickAndAnalyzeInvoice } from "./desktop";
import { formatIssueDate, severityLabel } from "./format";
import type { AnalysisResult, Alert } from "./types";
import "./App.css";

type ViewState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "result"; analysis: AnalysisResult }
  | { kind: "error"; message: string };

type IconName = "arrow" | "check" | "document" | "lock" | "report" | "shield";

function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, ReactNode> = {
    arrow: (
      <>
        <path d="M5 12h14" />
        <path d="m14 7 5 5-5 5" />
      </>
    ),
    check: <path d="m5 12 4 4L19 6" />,
    document: (
      <>
        <path d="M6 2h8l4 4v16H6z" />
        <path d="M14 2v5h5M9 12h6M9 16h6" />
      </>
    ),
    lock: (
      <>
        <rect x="5" y="10" width="14" height="11" rx="2" />
        <path d="M8 10V7a4 4 0 0 1 8 0v3" />
      </>
    ),
    report: (
      <>
        <path d="M4 4h16v16H4z" />
        <path d="M8 15v-3M12 15V8M16 15v-5" />
      </>
    ),
    shield: (
      <>
        <path d="M12 2 20 5v6c0 5-3.4 9-8 11-4.6-2-8-6-8-11V5z" />
        <path d="m8.5 12 2.2 2.2 4.8-5" />
      </>
    ),
  };

  return (
    <svg
      aria-hidden="true"
      className="icon"
      fill="none"
      height={size}
      viewBox="0 0 24 24"
      width={size}
    >
      {paths[name]}
    </svg>
  );
}

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
      <div className="result-status__mark" aria-hidden="true">
        {hasError ? "×" : hasWarning ? "!" : <Icon name="check" size={22} />}
      </div>
      <div className="result-status__copy">
        <p className="overline">Resultado da análise</p>
        <h2>{title}</h2>
        <p>
          {analysis.fileName} · {report.alerts.length} {report.alerts.length === 1 ? "alerta" : "alertas"}
        </p>
      </div>
      <span className="result-status__scope">processado localmente</span>
    </section>
  );
}

function Summary({ analysis }: { analysis: AnalysisResult }) {
  const { report } = analysis;
  return (
    <dl className="summary-grid" aria-label="Resumo da análise">
      <div>
        <dt>Documento</dt>
        <dd title={analysis.fileName}>{analysis.fileName}</dd>
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
        <dt>Contrato do motor</dt>
        <dd>{report.contract_version}</dd>
      </div>
    </dl>
  );
}

function AlertCard({ alert, number }: { alert: Alert; number: number }) {
  return (
    <article className={`alert-card alert-card--${alert.severity}`}>
      <div className="alert-card__number">{String(number).padStart(2, "0")}</div>
      <div className="alert-card__body">
        <div className="alert-card__heading">
          <span className="severity">{severityLabel(alert.severity)}</span>
          <code>{alert.rule_id}</code>
        </div>
        <h3>{alert.message}</h3>
        {alert.field_path && <p className="field-path">Campo analisado: {alert.field_path}</p>}
        {alert.evidence.length > 0 && (
          <ul className="evidence-list" aria-label="Evidências da regra">
            {alert.evidence.map((evidence) => (
              <li key={evidence}>{evidence}</li>
            ))}
          </ul>
        )}
      </div>
    </article>
  );
}

function IdleWorkspace({ onSelect }: { onSelect: () => void }) {
  return (
    <>
      <section className="workspace-grid">
        <article className="import-panel">
          <div className="panel-index" aria-hidden="true">
            01
          </div>
          <div className="document-mark" aria-hidden="true">
            <Icon name="document" size={28} />
            <span>XML</span>
          </div>
          <p className="overline">Nova conferência</p>
          <h2>Selecione uma NF-e para revisar.</h2>
          <p className="import-panel__description">
            O arquivo é aberto apenas pelo motor local. Nenhum XML, caminho ou dado fiscal é enviado para servidores.
          </p>
          <button className="primary-button" type="button" onClick={onSelect}>
            Selecionar XML
            <Icon name="arrow" size={18} />
          </button>
          <p className="file-requirements">NF-e modelo 55 · XML de até 2 MB · uma nota por análise</p>
        </article>

        <aside className="scope-panel" aria-labelledby="scope-title">
          <div>
            <p className="overline">Escopo do motor</p>
            <h2 id="scope-title">Conferência objetiva, sem promessas amplas.</h2>
          </div>
          <ol className="scope-list">
            <li>
              <span>01</span>
              <div>
                <strong>Estrutura oficial</strong>
                <p>Leiaute NF-e 4.00 e modelo 55.</p>
              </div>
            </li>
            <li>
              <span>02</span>
              <div>
                <strong>Totais e itens</strong>
                <p>Regras determinísticas com evidências.</p>
              </div>
            </li>
            <li>
              <span>03</span>
              <div>
                <strong>Relatório local</strong>
                <p>Resultado sem persistir o documento.</p>
              </div>
            </li>
          </ol>
          <div className="scope-note">
            <Icon name="shield" size={18} />
            <p>O resultado não substitui autorização SEFAZ nem revisão profissional.</p>
          </div>
        </aside>
      </section>

      <section className="process-line" aria-label="Etapas da conferência">
        <div>
          <span>01</span>
          <strong>Seleção local</strong>
          <p>Você escolhe o arquivo.</p>
        </div>
        <div>
          <span>02</span>
          <strong>Análise determinística</strong>
          <p>O motor aplica regras versionadas.</p>
        </div>
        <div>
          <span>03</span>
          <strong>Revisão das evidências</strong>
          <p>Você decide o próximo passo.</p>
        </div>
      </section>
    </>
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
      <aside className="navigation">
        <a className="brand" href="#main" aria-label="contAI — início">
          cont<span>AI</span>
        </a>

        <nav aria-label="Navegação principal">
          <a className="navigation__item navigation__item--active" href="#main" aria-current="page">
            <Icon name="report" size={19} />
            <span>Conferência</span>
          </a>
        </nav>

        <div className="local-state" id="privacy">
          <Icon name="lock" size={17} />
          <div>
            <strong>Processamento local</strong>
            <span>Sem envio do XML</span>
          </div>
        </div>
      </aside>

      <div className="application">
        <header className="app-header">
          <div className="app-header__title">
            <span aria-hidden="true">01</span>
            <div>
              <p>Ferramentas fiscais</p>
              <h1>Conferência de NF-e</h1>
            </div>
          </div>
          <div className="engine-state">
            <span aria-hidden="true" />
            Motor local <strong>v1</strong>
          </div>
        </header>

        <main id="main" className="workspace">
          {state.kind === "idle" && <IdleWorkspace onSelect={selectInvoice} />}

          {state.kind === "loading" && (
            <section className="loading-panel" aria-live="polite">
              <div className="loading-panel__indicator" aria-hidden="true">
                <span />
              </div>
              <p className="overline">Motor fiscal local</p>
              <h2>Analisando o documento…</h2>
              <p>Validando estrutura, itens e totais pelas regras disponíveis.</p>
            </section>
          )}

          {state.kind === "error" && (
            <section className="error-panel" role="alert">
              <div className="error-panel__code" aria-hidden="true">
                !
              </div>
              <div>
                <p className="overline">Análise interrompida</p>
                <h2>{state.message}</h2>
                <p>Nenhum conteúdo do XML foi enviado ou persistido pelo contAI.</p>
                <button className="secondary-button" type="button" onClick={selectInvoice}>
                  Tentar novamente
                  <Icon name="arrow" size={17} />
                </button>
              </div>
            </section>
          )}

          {state.kind === "result" && (
            <div className="results">
              <div className="results-toolbar">
                <div>
                  <p className="overline">Sessão atual</p>
                  <strong>Relatório de conferência</strong>
                </div>
                <button className="secondary-button" type="button" onClick={selectInvoice}>
                  Analisar outro XML
                  <Icon name="arrow" size={17} />
                </button>
              </div>

              <ResultStatus analysis={state.analysis} />
              <Summary analysis={state.analysis} />

              <section className="alerts-section">
                <div className="section-heading">
                  <div>
                    <p className="overline">Evidências</p>
                    <h2>Alertas para revisão</h2>
                  </div>
                  <span>{String(state.analysis.report.alerts.length).padStart(2, "0")}</span>
                </div>

                {state.analysis.report.alerts.length === 0 ? (
                  <div className="empty-alerts">
                    <div aria-hidden="true">
                      <Icon name="check" size={22} />
                    </div>
                    <div>
                      <strong>Nenhuma divergência nas verificações executadas.</strong>
                      <p>Isso não representa conformidade fiscal integral. Considere os limites do motor ao decidir.</p>
                    </div>
                  </div>
                ) : (
                  <div className="alert-list">
                    {state.analysis.report.alerts.map((alert, index) => (
                      <AlertCard key={`${alert.rule_id}-${index}`} alert={alert} number={index + 1} />
                    ))}
                  </div>
                )}
              </section>
            </div>
          )}
        </main>

        <footer>
          <span>contAI · conferência local</span>
          <span>O documento permanece neste computador.</span>
        </footer>
      </div>
    </div>
  );
}

export default App;
