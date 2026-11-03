use std::{fs, path::PathBuf};

use serde::{Deserialize, Serialize};
use tauri::AppHandle;
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_shell::ShellExt;

const ENGINE_CONTRACT_VERSION: &str = "fiscal-engine-v1";
const MAX_XML_BYTES: u64 = 2_000_000;
const MAX_SIDECAR_OUTPUT_BYTES: usize = 1_000_000;

#[derive(Debug, Deserialize, PartialEq, Serialize)]
pub struct Alert {
    rule_id: String,
    rule_version: String,
    severity: String,
    code: String,
    message: String,
    field_path: Option<String>,
    evidence: Vec<String>,
}

#[derive(Debug, Deserialize, PartialEq, Serialize)]
pub struct AnalysisReport {
    contract_version: String,
    status: String,
    document_model: Option<String>,
    issue_date: Option<String>,
    ncm_release_id: Option<String>,
    alerts: Vec<Alert>,
}

#[derive(Debug, Serialize)]
pub struct CommandError {
    code: String,
    message: String,
}

impl CommandError {
    fn new(code: &str, message: &str) -> Self {
        Self {
            code: code.to_owned(),
            message: message.to_owned(),
        }
    }
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DesktopAnalysis {
    file_name: String,
    report: AnalysisReport,
}

fn validate_invoice_path(path: PathBuf) -> Result<PathBuf, CommandError> {
    let metadata = fs::metadata(&path).map_err(|_| {
        CommandError::new(
            "invoice_unavailable",
            "O arquivo selecionado não está mais disponível.",
        )
    })?;

    if !metadata.is_file()
        || !path
            .extension()
            .and_then(|extension| extension.to_str())
            .is_some_and(|extension| extension.eq_ignore_ascii_case("xml"))
    {
        return Err(CommandError::new(
            "invalid_invoice_file",
            "Selecione um arquivo XML de NF-e válido.",
        ));
    }
    if metadata.len() == 0 || metadata.len() > MAX_XML_BYTES {
        return Err(CommandError::new(
            "invalid_invoice_size",
            "O XML deve ter entre 1 byte e 2 MB.",
        ));
    }

    Ok(path)
}

fn parse_sidecar_output(stdout: &[u8]) -> Result<AnalysisReport, CommandError> {
    if stdout.is_empty() || stdout.len() > MAX_SIDECAR_OUTPUT_BYTES {
        return Err(CommandError::new(
            "invalid_engine_response",
            "O motor fiscal local retornou uma resposta inválida.",
        ));
    }

    let report: AnalysisReport = serde_json::from_slice(stdout).map_err(|_| {
        CommandError::new(
            "invalid_engine_response",
            "O motor fiscal local retornou uma resposta inválida.",
        )
    })?;
    if report.contract_version != ENGINE_CONTRACT_VERSION
        || !matches!(report.status.as_str(), "analyzed" | "rejected")
    {
        return Err(CommandError::new(
            "unsupported_engine_contract",
            "A versão do motor fiscal não é compatível com este aplicativo.",
        ));
    }

    Ok(report)
}

async fn analyze_invoice(
    app: &AppHandle,
    invoice_path: PathBuf,
) -> Result<AnalysisReport, CommandError> {
    let sidecar = app.shell().sidecar("contai-fiscal-engine").map_err(|_| {
        CommandError::new(
            "engine_unavailable",
            "O motor fiscal local não pôde ser iniciado.",
        )
    })?;
    let output = sidecar
        .args([invoice_path.to_string_lossy().into_owned()])
        .output()
        .await
        .map_err(|_| {
            CommandError::new(
                "engine_unavailable",
                "O motor fiscal local não pôde ser iniciado.",
            )
        })?;

    parse_sidecar_output(&output.stdout)
}

#[tauri::command]
pub async fn pick_and_analyze_invoice(
    app: AppHandle,
) -> Result<Option<DesktopAnalysis>, CommandError> {
    let selected = app
        .dialog()
        .file()
        .add_filter("Nota Fiscal Eletrônica", &["xml"])
        .blocking_pick_file();
    let Some(selected) = selected else {
        return Ok(None);
    };
    let path = selected.into_path().map_err(|_| {
        CommandError::new(
            "invalid_invoice_file",
            "Selecione um arquivo XML de NF-e válido.",
        )
    })?;
    let invoice_path = validate_invoice_path(path)?;
    let file_name = invoice_path
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("nota-fiscal.xml")
        .to_owned();
    let report = analyze_invoice(&app, invoice_path).await?;

    Ok(Some(DesktopAnalysis { file_name, report }))
}

#[cfg(test)]
mod tests {
    use std::io::Write;

    use tempfile::Builder;

    use super::{parse_sidecar_output, validate_invoice_path};

    const VALID_REPORT: &[u8] = br#"{
        "contract_version":"fiscal-engine-v1",
        "status":"analyzed",
        "document_model":"55",
        "issue_date":"2026-10-30",
        "ncm_release_id":null,
        "alerts":[]
    }"#;

    #[test]
    fn accepts_existing_xml_inside_size_limit() {
        let mut file = Builder::new().suffix(".XML").tempfile().unwrap();
        file.write_all(b"<NFe/>").unwrap();

        let result = validate_invoice_path(file.path().to_path_buf());

        assert_eq!(result.unwrap(), file.path());
    }

    #[test]
    fn rejects_non_xml_without_exposing_path() {
        let mut file = Builder::new().suffix(".txt").tempfile().unwrap();
        file.write_all(b"not an invoice").unwrap();

        let error = validate_invoice_path(file.path().to_path_buf()).unwrap_err();

        assert_eq!(error.code, "invalid_invoice_file");
        assert!(!error.message.contains(file.path().to_str().unwrap()));
    }

    #[test]
    fn accepts_supported_engine_contract() {
        let report = parse_sidecar_output(VALID_REPORT).unwrap();

        assert_eq!(report.contract_version, "fiscal-engine-v1");
        assert_eq!(report.status, "analyzed");
    }

    #[test]
    fn rejects_unknown_contract_without_echoing_output() {
        let payload = String::from_utf8(VALID_REPORT.to_vec())
            .unwrap()
            .replace("fiscal-engine-v1", "future-engine-v2");

        let error = parse_sidecar_output(payload.as_bytes()).unwrap_err();

        assert_eq!(error.code, "unsupported_engine_contract");
        assert!(!error.message.contains("future-engine-v2"));
    }
}
