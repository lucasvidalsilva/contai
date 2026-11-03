export type Severity = "info" | "warning" | "error";

export interface Alert {
  rule_id: string;
  rule_version: string;
  severity: Severity;
  code: string;
  message: string;
  field_path: string | null;
  evidence: string[];
}

export interface AnalysisReport {
  contract_version: "fiscal-engine-v1";
  status: "analyzed" | "rejected";
  document_model: string | null;
  issue_date: string | null;
  ncm_release_id: string | null;
  alerts: Alert[];
}

export interface AnalysisResult {
  fileName: string;
  report: AnalysisReport;
}

export interface CommandErrorPayload {
  code: string;
  message: string;
}
