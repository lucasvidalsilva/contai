import { useState, type ReactNode } from "react";

import { describeError, pickAndAnalyzeDocuments } from "./desktop";
import { formatIssueDate, severityLabel } from "./format";
import type { Alert, AnalysisProgress, BatchAnalysis } from "./types";
import "./App.css";

type ViewState =
  | { kind: "idle" }
  | { kind: "loading"; progress: AnalysisProgress }
  | { kind: "result"; batch: BatchAnalysis }
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

function batchStatistics(batch: BatchAnalysis) {
  return {
    analyzed: batch.documents.filter(({ report }) => report.status === "analyzed").length,
    rejected: batch.documents.filter(({ report }) => report.status === "rejected").length,
    alerts: batch.documents.reduce((total, { report }) => total + report.alerts.length, 0),
  };
}

function ResultStatus({ batch }: { batch: BatchAnalysis }) {
  const statistics = batchStatistics(batch);
  const hasError =
    statistics.rejected > 0 ||
    batch.documents.some(({ report }) => report.alerts.some((alert) => alert.severity === "error"));
  const hasWarning = batch.documents.some(({ report }) =>
    report.alerts.some((alert) => alert.severity === "warning"),
  );
  const tone = hasError ? "danger" : hasWarning ? "attention" : "success";
  const title = hasError
    ? "Conferência concluída com rejeições"
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
          {batch.sourceName} · {batch.documents.length}{" "}
          {batch.documents.length === 1 ? "documento" : "documentos"} · {statistics.alerts}{" "}
          {statistics.alerts === 1 ? "alerta" : "alertas"}
        </p>
      </div>
      <span className="result-status__scope">processado localmente</span>
    </section>
  );
}

function BatchSummary({ batch }: { batch: BatchAnalysis }) {
  const statistics = batchStatistics(batch);
  return (
    <dl className="summary-grid summary-grid--batch" aria-label="Resumo do lote">
      <div>
        <dt>Documentos</dt>
        <dd>{batch.documents.length}</dd>
      </div>
      <div>
        <dt>Analisados</dt>
        <dd>{statistics.analyzed}</dd>
      </div>
      <div>
        <dt>Rejeitados</dt>
        <dd>{statistics.rejected}</dd>
      </div>
      <div>
        <dt>Alertas</dt>
        <dd>{statistics.alerts}</dd>
      </div>
      <div>
        <dt>Duplicados ignorados</dt>
        <dd>{batch.duplicateFiles.length}</dd>
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

function DocumentResult({
  analysis,
  index,
  initiallyOpen,
}: {
  analysis: BatchAnalysis["documents"][number];
  index: number;
  initiallyOpen: boolean;
}) {
  const { report } = analysis;
  const rejected = report.status === "rejected";
  const hasAlerts = report.alerts.length > 0;
  const tone = rejected ? "rejected" : hasAlerts ? "attention" : "success";
  const label = rejected ? "Rejeitado" : hasAlerts ? "Com alertas" : "Sem alertas";

  return (
    <details className={`document-result document-result--${tone}`} open={initiallyOpen}>
      <summary>
        <span className="document-result__index">{String(index).padStart(2, "0")}</span>
        <span className="document-result__name" title={analysis.fileName}>
          {analysis.fileName}
        </span>
        <span className="document-result__meta">
          Modelo {report.document_model ?? "—"} · {formatIssueDate(report.issue_date)}
        </span>
        <span className="document-result__status">{label}</span>
        <span className="document-result__count">{report.alerts.length}</span>
      </summary>
      <div className="document-result__content">
        {report.alerts.length === 0 ? (
          <div className="document-empty">
            <Icon name="check" size={18} />
            Nenhuma divergência nas verificações executadas.
          </div>
        ) : (
          <div className="alert-list">
            {report.alerts.map((alert, alertIndex) => (
              <AlertCard
                key={`${alert.rule_id}-${alertIndex}`}
                alert={alert}
                number={alertIndex + 1}
              />
            ))}
          </div>
        )}
      </div>
    </details>
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
            <span>XML/ZIP</span>
          </div>
          <p className="overline">Nova conferência</p>
          <h2>Selecione uma NF-e ou um lote ZIP.</h2>
          <p className="import-panel__description">
            Os arquivos são abertos apenas pelo motor local. Nenhum XML, caminho ou dado fiscal é enviado para
            servidores.
          </p>
          <button className="primary-button" type="button" onClick={onSelect}>
            Selecionar XML ou ZIP
            <Icon name="arrow" size={18} />
          </button>
          <p className="file-requirements">Até 100 XMLs · 2 MB por XML · ZIP de até 25 MB</p>
        </article>

        <aside className="scope-panel" aria-labelledby="scope-title">
          <div>
            <p className="overline">Escopo do motor</p>
            <h2 id="scope-title">Conferência objetiva, individual ou em lote.</h2>
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
                <strong>Lote protegido</strong>
                <p>Limites, deduplicação e progresso local.</p>
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
          <p>XML único ou lote ZIP.</p>
        </div>
        <div>
          <span>02</span>
          <strong>Análise progressiva</strong>
          <p>Um motor, vários documentos.</p>
        </div>
        <div>
          <span>03</span>
          <strong>Revisão das evidências</strong>
          <p>Resultado por documento.</p>
        </div>
      </section>
    </>
  );
}

function LoadingWorkspace({ progress }: { progress: AnalysisProgress }) {
  const maximum = Math.max(progress.total, 1);
  const percentage = progress.total === 0 ? 0 : Math.round((progress.processed / progress.total) * 100);
  return (
    <section className="loading-panel" aria-live="polite">
      <div className="loading-panel__indicator" aria-hidden="true">
        <span />
      </div>
      <p className="overline">Motor fiscal local</p>
      <h2>{progress.total === 0 ? "Preparando os documentos…" : "Analisando o lote…"}</h2>
      <p className="loading-panel__file">
        {progress.fileName ?? "Validando limites e removendo duplicidades."}
      </p>
      <div className="progress-block">
        <div>
          <strong>{progress.total === 0 ? "Preparando" : `${progress.processed} de ${progress.total}`}</strong>
          <span>{percentage}%</span>
        </div>
        <progress max={maximum} value={progress.processed}>
          {percentage}%
        </progress>
      </div>
    </section>
  );
}

function App() {
  const [state, setState] = useState<ViewState>({ kind: "idle" });

  async function selectDocuments() {
    setState({
      kind: "loading",
      progress: { processed: 0, total: 0, fileName: null },
    });
    try {
      const batch = await pickAndAnalyzeDocuments((progress) => {
        setState({ kind: "loading", progress });
      });
      setState(batch ? { kind: "result", batch } : { kind: "idle" });
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
          {state.kind === "idle" && <IdleWorkspace onSelect={selectDocuments} />}
          {state.kind === "loading" && <LoadingWorkspace progress={state.progress} />}

          {state.kind === "error" && (
            <section className="error-panel" role="alert">
              <div className="error-panel__code" aria-hidden="true">
                !
              </div>
              <div>
                <p className="overline">Análise interrompida</p>
                <h2>{state.message}</h2>
                <p>Nenhum conteúdo fiscal foi enviado ou persistido pelo contAI.</p>
                <button className="secondary-button" type="button" onClick={selectDocuments}>
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
                  <strong>{state.batch.sourceName}</strong>
                </div>
                <button className="secondary-button" type="button" onClick={selectDocuments}>
                  Analisar outro arquivo
                  <Icon name="arrow" size={17} />
                </button>
              </div>

              <ResultStatus batch={state.batch} />
              <BatchSummary batch={state.batch} />

              {state.batch.duplicateFiles.length > 0 && (
                <aside className="duplicate-note">
                  <strong>
                    {state.batch.duplicateFiles.length}{" "}
                    {state.batch.duplicateFiles.length === 1 ? "duplicado ignorado" : "duplicados ignorados"}
                  </strong>
                  <span>{state.batch.duplicateFiles.join(", ")}</span>
                </aside>
              )}

              <section className="alerts-section">
                <div className="section-heading">
                  <div>
                    <p className="overline">Resultado por documento</p>
                    <h2>Documentos analisados</h2>
                  </div>
                  <span>{String(state.batch.documents.length).padStart(2, "0")}</span>
                </div>

                <div className="document-list">
                  {state.batch.documents.map((analysis, index) => (
                    <DocumentResult
                      key={`${analysis.fileName}-${index}`}
                      analysis={analysis}
                      index={index + 1}
                      initiallyOpen={state.batch.documents.length === 1}
                    />
                  ))}
                </div>

                <p className="result-disclaimer">
                  Ausência de alertas não representa conformidade fiscal integral. Considere os limites do motor ao
                  decidir.
                </p>
              </section>
            </div>
          )}
        </main>

        <footer>
          <span>contAI · conferência local</span>
          <span>Os documentos permanecem neste computador.</span>
        </footer>
      </div>
    </div>
  );
}

export default App;
