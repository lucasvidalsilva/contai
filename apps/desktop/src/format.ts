import type { Severity } from "./types";

export function formatIssueDate(value: string | null): string {
  if (!value) {
    return "Não identificada";
  }
  const parts = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!parts) {
    return "Não identificada";
  }
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(Number(parts[1]), Number(parts[2]) - 1, Number(parts[3]))));
}

export function severityLabel(severity: Severity): string {
  return { info: "Informativo", warning: "Atenção", error: "Erro" }[severity];
}
