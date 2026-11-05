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

$batchJson = @(& $binaryPath "--desktop-batch" $fixturePath $fixturePath)
if ($LASTEXITCODE -ne 0) {
    throw "Sidecar rejeitou o protocolo em lote com código $LASTEXITCODE."
}
if ($batchJson.Count -ne 2) {
    throw "Protocolo em lote retornou $($batchJson.Count) linhas, esperado 2."
}
for ($index = 0; $index -lt $batchJson.Count; $index += 1) {
    $batchLine = $batchJson[$index] | ConvertFrom-Json
    if ($batchLine.index -ne $index -or $batchLine.report.contract_version -ne "fiscal-engine-v1") {
        throw "Protocolo em lote retornou item inválido no índice $index."
    }
}

Write-Output "Sidecar verificado: contrato individual e fluxo incremental em lote aprovados."
