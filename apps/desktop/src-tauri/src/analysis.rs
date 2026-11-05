use std::{
    collections::HashMap,
    fs::{self, File},
    io::Read,
    path::{Path, PathBuf},
};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use tauri::{AppHandle, ipc::Channel};
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_shell::{ShellExt, process::CommandEvent};
use tempfile::{TempDir, tempdir};
use zip::ZipArchive;

const ENGINE_CONTRACT_VERSION: &str = "fiscal-engine-v1";
const MAX_XML_BYTES: u64 = 2_000_000;
const MAX_ZIP_BYTES: u64 = 25_000_000;
const MAX_BATCH_UNCOMPRESSED_BYTES: u64 = 50_000_000;
const MAX_BATCH_DOCUMENTS: usize = 100;
const MAX_ARCHIVE_ENTRIES: usize = 1_000;
const MAX_SIDECAR_OUTPUT_BYTES: usize = 1_000_000;
const MAX_SIDECAR_STDERR_BYTES: usize = 1_000_000;

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

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct BatchAnalysis {
    source_name: String,
    documents: Vec<DesktopAnalysis>,
    duplicate_files: Vec<String>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct BatchProgress {
    processed: usize,
    total: usize,
    file_name: Option<String>,
}

#[derive(Debug, Deserialize)]
struct EngineBatchLine {
    index: usize,
    report: AnalysisReport,
}

#[derive(Debug)]
struct PreparedDocument {
    file_name: String,
    path: PathBuf,
}

#[derive(Debug)]
struct PreparedBatch {
    source_name: String,
    documents: Vec<PreparedDocument>,
    duplicate_files: Vec<String>,
    _temporary_directory: Option<TempDir>,
}

fn selected_file_name(path: &Path, fallback: &str) -> String {
    path.file_name()
        .and_then(|value| value.to_str())
        .filter(|value| !value.is_empty())
        .unwrap_or(fallback)
        .to_owned()
}

fn extension_is(path: &Path, expected: &str) -> bool {
    path.extension()
        .and_then(|extension| extension.to_str())
        .is_some_and(|extension| extension.eq_ignore_ascii_case(expected))
}

fn validate_selection_path(path: PathBuf) -> Result<PathBuf, CommandError> {
    let metadata = fs::metadata(&path).map_err(|_| {
        CommandError::new(
            "selection_unavailable",
            "O arquivo selecionado não está mais disponível.",
        )
    })?;

    if !metadata.is_file() || (!extension_is(&path, "xml") && !extension_is(&path, "zip")) {
        return Err(CommandError::new(
            "invalid_selection_file",
            "Selecione um XML de NF-e ou um lote ZIP válido.",
        ));
    }
    if metadata.len() == 0 {
        return Err(CommandError::new(
            "invalid_selection_size",
            "O arquivo selecionado está vazio.",
        ));
    }
    if extension_is(&path, "xml") && metadata.len() > MAX_XML_BYTES {
        return Err(CommandError::new(
            "invalid_selection_size",
            "Cada XML deve ter no máximo 2 MB.",
        ));
    }
    if extension_is(&path, "zip") && metadata.len() > MAX_ZIP_BYTES {
        return Err(CommandError::new(
            "invalid_selection_size",
            "O lote ZIP deve ter no máximo 25 MB.",
        ));
    }

    Ok(path)
}

fn prepare_single_xml(path: PathBuf) -> PreparedBatch {
    let file_name = selected_file_name(&path, "nota-fiscal.xml");
    PreparedBatch {
        source_name: file_name.clone(),
        documents: vec![PreparedDocument { file_name, path }],
        duplicate_files: Vec::new(),
        _temporary_directory: None,
    }
}

fn prepare_zip(path: PathBuf) -> Result<PreparedBatch, CommandError> {
    let source_name = selected_file_name(&path, "lote-fiscal.zip");
    let archive_file = File::open(&path).map_err(|_| {
        CommandError::new(
            "archive_unavailable",
            "O lote ZIP selecionado não pôde ser aberto.",
        )
    })?;
    let mut archive = ZipArchive::new(archive_file).map_err(|_| {
        CommandError::new(
            "invalid_archive",
            "O arquivo selecionado não é um ZIP válido.",
        )
    })?;
    if archive.len() > MAX_ARCHIVE_ENTRIES {
        return Err(CommandError::new(
            "archive_too_many_entries",
            "O ZIP excede o limite de 1.000 entradas.",
        ));
    }

    let temporary_directory = tempdir().map_err(|_| {
        CommandError::new(
            "temporary_storage_unavailable",
            "O aplicativo não conseguiu preparar o lote localmente.",
        )
    })?;
    let mut documents = Vec::new();
    let mut duplicate_files = Vec::new();
    let mut hashes: HashMap<Vec<u8>, String> = HashMap::new();
    let mut total_uncompressed = 0_u64;

    for archive_index in 0..archive.len() {
        let mut entry = archive.by_index(archive_index).map_err(|_| {
            CommandError::new(
                "invalid_archive",
                "O ZIP contém uma entrada que não pôde ser lida.",
            )
        })?;
        let enclosed_path = entry.enclosed_name().ok_or_else(|| {
            CommandError::new(
                "unsafe_archive_path",
                "O ZIP contém um caminho de arquivo inseguro.",
            )
        })?;
        if entry.is_symlink() {
            return Err(CommandError::new(
                "unsupported_archive_entry",
                "O ZIP não pode conter links simbólicos.",
            ));
        }

        total_uncompressed = total_uncompressed
            .checked_add(entry.size())
            .ok_or_else(|| {
                CommandError::new(
                    "archive_expansion_limit",
                    "O tamanho descompactado do ZIP é inválido.",
                )
            })?;
        if total_uncompressed > MAX_BATCH_UNCOMPRESSED_BYTES {
            return Err(CommandError::new(
                "archive_expansion_limit",
                "O ZIP excede o limite de 50 MB descompactados.",
            ));
        }
        if !entry.is_file() || !extension_is(&enclosed_path, "xml") {
            continue;
        }
        if entry.encrypted() {
            return Err(CommandError::new(
                "encrypted_archive",
                "XMLs protegidos por senha não são aceitos.",
            ));
        }
        if entry.size() == 0 || entry.size() > MAX_XML_BYTES {
            return Err(CommandError::new(
                "invalid_archive_entry_size",
                "Cada XML dentro do ZIP deve ter entre 1 byte e 2 MB.",
            ));
        }
        if documents.len() + duplicate_files.len() >= MAX_BATCH_DOCUMENTS {
            return Err(CommandError::new(
                "archive_document_limit",
                "O lote aceita no máximo 100 arquivos XML.",
            ));
        }

        let mut payload = Vec::with_capacity(entry.size() as usize);
        entry.read_to_end(&mut payload).map_err(|_| {
            CommandError::new(
                "invalid_archive_entry",
                "Um XML do ZIP não pôde ser descompactado.",
            )
        })?;
        if payload.len() as u64 != entry.size() {
            return Err(CommandError::new(
                "invalid_archive_entry",
                "Um XML do ZIP possui tamanho inconsistente.",
            ));
        }

        let file_name = selected_file_name(&enclosed_path, "nota-fiscal.xml");
        let digest = Sha256::digest(&payload).to_vec();
        if hashes.contains_key(&digest) {
            duplicate_files.push(file_name);
            continue;
        }
        hashes.insert(digest, file_name.clone());

        let local_path = temporary_directory
            .path()
            .join(format!("{:04}.xml", documents.len()));
        fs::write(&local_path, payload).map_err(|_| {
            CommandError::new(
                "temporary_storage_unavailable",
                "O aplicativo não conseguiu preparar o lote localmente.",
            )
        })?;
        documents.push(PreparedDocument {
            file_name,
            path: local_path,
        });
    }

    if documents.is_empty() {
        return Err(CommandError::new(
            "archive_without_xml",
            "O ZIP não contém arquivos XML de NF-e para análise.",
        ));
    }

    Ok(PreparedBatch {
        source_name,
        documents,
        duplicate_files,
        _temporary_directory: Some(temporary_directory),
    })
}

fn prepare_selection(path: PathBuf) -> Result<PreparedBatch, CommandError> {
    let validated = validate_selection_path(path)?;
    if extension_is(&validated, "zip") {
        prepare_zip(validated)
    } else {
        Ok(prepare_single_xml(validated))
    }
}

fn validate_report(report: AnalysisReport) -> Result<AnalysisReport, CommandError> {
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

#[cfg(test)]
fn parse_sidecar_output(stdout: &[u8]) -> Result<AnalysisReport, CommandError> {
    if stdout.is_empty() || stdout.len() > MAX_SIDECAR_OUTPUT_BYTES {
        return Err(CommandError::new(
            "invalid_engine_response",
            "O motor fiscal local retornou uma resposta inválida.",
        ));
    }
    let report = serde_json::from_slice(stdout).map_err(|_| {
        CommandError::new(
            "invalid_engine_response",
            "O motor fiscal local retornou uma resposta inválida.",
        )
    })?;
    validate_report(report)
}

fn send_progress(
    channel: &Channel<BatchProgress>,
    processed: usize,
    total: usize,
    file_name: Option<String>,
) {
    let _ = channel.send(BatchProgress {
        processed,
        total,
        file_name,
    });
}

async fn analyze_documents(
    app: &AppHandle,
    documents: &[PreparedDocument],
    on_progress: &Channel<BatchProgress>,
) -> Result<Vec<AnalysisReport>, CommandError> {
    let mut arguments = Vec::with_capacity(documents.len() + 1);
    arguments.push("--desktop-batch".to_owned());
    arguments.extend(
        documents
            .iter()
            .map(|document| document.path.to_string_lossy().into_owned()),
    );
    let sidecar = app
        .shell()
        .sidecar("contai-fiscal-engine")
        .map_err(|_| {
            CommandError::new(
                "engine_unavailable",
                "O motor fiscal local não pôde ser iniciado.",
            )
        })?
        .args(arguments);
    let (mut receiver, _child) = sidecar.spawn().map_err(|_| {
        CommandError::new(
            "engine_unavailable",
            "O motor fiscal local não pôde ser iniciado.",
        )
    })?;

    let total = documents.len();
    let mut reports: Vec<Option<AnalysisReport>> = (0..total).map(|_| None).collect();
    let mut processed = 0;
    let mut exit_code = None;
    let mut stderr_bytes = 0_usize;

    while let Some(event) = receiver.recv().await {
        match event {
            CommandEvent::Stdout(line) => {
                if line.is_empty() || line.len() > MAX_SIDECAR_OUTPUT_BYTES {
                    return Err(CommandError::new(
                        "invalid_engine_response",
                        "O motor fiscal local retornou uma resposta inválida.",
                    ));
                }
                let engine_line: EngineBatchLine = serde_json::from_slice(&line).map_err(|_| {
                    CommandError::new(
                        "invalid_engine_response",
                        "O motor fiscal local retornou uma resposta inválida.",
                    )
                })?;
                if engine_line.index >= total || reports[engine_line.index].is_some() {
                    return Err(CommandError::new(
                        "invalid_engine_response",
                        "O motor fiscal local retornou uma resposta inválida.",
                    ));
                }
                reports[engine_line.index] = Some(validate_report(engine_line.report)?);
                processed += 1;
                send_progress(
                    on_progress,
                    processed,
                    total,
                    Some(documents[engine_line.index].file_name.clone()),
                );
            }
            CommandEvent::Stderr(line) => {
                stderr_bytes = stderr_bytes.saturating_add(line.len());
                if stderr_bytes > MAX_SIDECAR_STDERR_BYTES {
                    return Err(CommandError::new(
                        "invalid_engine_response",
                        "O motor fiscal local retornou uma resposta inválida.",
                    ));
                }
            }
            CommandEvent::Error(_) => {
                return Err(CommandError::new(
                    "engine_unavailable",
                    "O motor fiscal local foi interrompido durante a análise.",
                ));
            }
            CommandEvent::Terminated(payload) => {
                exit_code = payload.code;
            }
            _ => {}
        }
    }

    if exit_code != Some(0) || processed != total {
        return Err(CommandError::new(
            "engine_unavailable",
            "O motor fiscal local não concluiu todos os documentos.",
        ));
    }
    reports
        .into_iter()
        .collect::<Option<Vec<_>>>()
        .ok_or_else(|| {
            CommandError::new(
                "invalid_engine_response",
                "O motor fiscal local retornou uma resposta incompleta.",
            )
        })
}

#[tauri::command]
pub async fn pick_and_analyze_documents(
    app: AppHandle,
    on_progress: Channel<BatchProgress>,
) -> Result<Option<BatchAnalysis>, CommandError> {
    let selected = app
        .dialog()
        .file()
        .add_filter("NF-e ou lote ZIP", &["xml", "zip"])
        .blocking_pick_file();
    let Some(selected) = selected else {
        return Ok(None);
    };
    let path = selected.into_path().map_err(|_| {
        CommandError::new(
            "invalid_selection_file",
            "Selecione um XML de NF-e ou um lote ZIP válido.",
        )
    })?;
    let prepared = prepare_selection(path)?;
    send_progress(&on_progress, 0, prepared.documents.len(), None);
    let reports = analyze_documents(&app, &prepared.documents, &on_progress).await?;
    let documents = prepared
        .documents
        .iter()
        .zip(reports)
        .map(|(document, report)| DesktopAnalysis {
            file_name: document.file_name.clone(),
            report,
        })
        .collect();

    Ok(Some(BatchAnalysis {
        source_name: prepared.source_name,
        documents,
        duplicate_files: prepared.duplicate_files,
    }))
}

#[cfg(test)]
mod tests {
    use std::io::Write;

    use tempfile::Builder;
    use zip::{CompressionMethod, ZipWriter, write::SimpleFileOptions};

    use super::{MAX_XML_BYTES, parse_sidecar_output, prepare_zip, validate_selection_path};

    const VALID_REPORT: &[u8] = br#"{
        "contract_version":"fiscal-engine-v1",
        "status":"analyzed",
        "document_model":"55",
        "issue_date":"2026-10-30",
        "ncm_release_id":null,
        "alerts":[]
    }"#;

    fn synthetic_zip(entries: &[(&str, &[u8])]) -> tempfile::NamedTempFile {
        let mut file = Builder::new().suffix(".zip").tempfile().unwrap();
        {
            let mut writer = ZipWriter::new(file.as_file_mut());
            let options =
                SimpleFileOptions::default().compression_method(CompressionMethod::Stored);
            for (name, payload) in entries {
                writer.start_file(*name, options).unwrap();
                writer.write_all(payload).unwrap();
            }
            writer.finish().unwrap();
        }
        file
    }

    #[test]
    fn accepts_existing_xml_inside_size_limit() {
        let mut file = Builder::new().suffix(".XML").tempfile().unwrap();
        file.write_all(b"<NFe/>").unwrap();

        let result = validate_selection_path(file.path().to_path_buf());

        assert_eq!(result.unwrap(), file.path());
    }

    #[test]
    fn accepts_existing_zip_inside_size_limit() {
        let file = synthetic_zip(&[("document.xml", b"<NFe/>")]);

        let result = validate_selection_path(file.path().to_path_buf());

        assert_eq!(result.unwrap(), file.path());
    }

    #[test]
    fn rejects_unknown_extension_without_exposing_path() {
        let mut file = Builder::new().suffix(".txt").tempfile().unwrap();
        file.write_all(b"not an invoice").unwrap();

        let error = validate_selection_path(file.path().to_path_buf()).unwrap_err();

        assert_eq!(error.code, "invalid_selection_file");
        assert!(!error.message.contains(file.path().to_str().unwrap()));
    }

    #[test]
    fn rejects_empty_xml_at_desktop_boundary() {
        let file = Builder::new().suffix(".xml").tempfile().unwrap();

        let error = validate_selection_path(file.path().to_path_buf()).unwrap_err();

        assert_eq!(error.code, "invalid_selection_size");
    }

    #[test]
    fn rejects_xml_above_desktop_size_limit() {
        let mut file = Builder::new().suffix(".xml").tempfile().unwrap();
        file.as_file_mut().set_len(MAX_XML_BYTES + 1).unwrap();

        let error = validate_selection_path(file.path().to_path_buf()).unwrap_err();

        assert_eq!(error.code, "invalid_selection_size");
    }

    #[test]
    fn zip_uses_safe_names_and_deduplicates_equal_xmls() {
        let file = synthetic_zip(&[
            ("folder/first.xml", b"<NFe/>"),
            ("second.xml", b"<NFe/>"),
            ("notes.txt", b"ignored"),
        ]);

        let batch = prepare_zip(file.path().to_path_buf()).unwrap();

        assert_eq!(batch.documents.len(), 1);
        assert_eq!(batch.documents[0].file_name, "first.xml");
        assert_eq!(batch.duplicate_files, ["second.xml"]);
        assert!(
            batch.documents[0]
                .path
                .starts_with(batch._temporary_directory.as_ref().unwrap().path())
        );
    }

    #[test]
    fn zip_rejects_path_traversal() {
        let file = synthetic_zip(&[("../escape.xml", b"<NFe/>")]);

        let error = prepare_zip(file.path().to_path_buf()).unwrap_err();

        assert_eq!(error.code, "unsafe_archive_path");
    }

    #[test]
    fn zip_rejects_archive_without_xml() {
        let file = synthetic_zip(&[("readme.txt", b"no invoice")]);

        let error = prepare_zip(file.path().to_path_buf()).unwrap_err();

        assert_eq!(error.code, "archive_without_xml");
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
