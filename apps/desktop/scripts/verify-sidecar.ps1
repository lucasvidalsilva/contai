$ErrorActionPreference = "Stop"

$desktopRoot = Split-Path -Parent $PSScriptRoot
$repositoryRoot = (Resolve-Path (Join-Path $desktopRoot "..\..")).Path
$binaryPath = Join-Path $desktopRoot "src-tauri\binaries\contai-fiscal-engine-x86_64-pc-windows-msvc.exe"
$fixturePath = Join-Path $repositoryRoot "packages\fiscal-engine\tests\fixtures\nfe-synthetic-55.xml"

if (-not (Test-Path -LiteralPath $binaryPath)) {
    throw "Sidecar ausente; execute npm run sidecar:build antes da verificação."
}

$json = & $binaryPath $fixturePath
if ($LASTEXITCODE -ne 0) {
    throw "Sidecar rejeitou a fixture sintética com código $LASTEXITCODE."
}

$report = $json | ConvertFrom-Json
if ($report.contract_version -ne "fiscal-engine-v1") {
    throw "Contrato inesperado no sidecar: $($report.contract_version)"
}
if ($report.status -ne "analyzed" -or $report.document_model -ne "55" -or $report.alerts.Count -ne 0) {
    throw "Resultado inesperado para a fixture sintética."
}

Write-Output "Sidecar verificado: contrato fiscal-engine-v1, modelo 55, zero alertas."
