import { describe, expect, it } from "vitest";

import { formatIssueDate, severityLabel } from "./format";

describe("formatIssueDate", () => {
  it("formats ISO date without timezone drift", () => {
    const formatted = formatIssueDate("2026-10-30");

    expect(formatted).toContain("30");
    expect(formatted).toContain("2026");
  });

  it("does not invent a date for absent or malformed input", () => {
    expect(formatIssueDate(null)).toBe("Não identificada");
    expect(formatIssueDate("30/10/2026")).toBe("Não identificada");
  });
});

it("uses user-facing severity labels", () => {
  expect(severityLabel("info")).toBe("Informativo");
  expect(severityLabel("warning")).toBe("Atenção");
  expect(severityLabel("error")).toBe("Erro");
});
