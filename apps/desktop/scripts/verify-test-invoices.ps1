param(
    [string]$BinaryPath
)

$ErrorActionPreference = "Stop"

$desktopRoot = Split-Path -Parent $PSScriptRoot
$defaultBinaryPath = Join-Path $desktopRoot "src-tauri\binaries\contai-fiscal-engine-x86_64-pc-windows-msvc.exe"
$binaryPath = if ([string]::IsNullOrWhiteSpace($BinaryPath)) { $defaultBinaryPath } else { $BinaryPath }
$testDataRoot = Join-Path $desktopRoot "var\test-invoices"
$manifestPath = Join-Path $testDataRoot "manifest.json"

if (-not (Test-Path -LiteralPath $binaryPath)) {
    throw "Sidecar ausente; execute npm run sidecar:build antes da matriz."
}
if (-not (Test-Path -LiteralPath $manifestPath)) {
    throw "Matriz ausente; execute npm run testdata:build antes da verificação."
}

$manifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $manifestPath | ConvertFrom-Json
if ($manifest.contract_version -ne "contai-desktop-testdata-v1" -or -not $manifest.synthetic_only) {
    throw "Manifesto de teste inválido ou não sintético."
}

$verified = 0
foreach ($case in $manifest.cases) {
    $invoicePath = Join-Path $testDataRoot $case.file
    $json = & $binaryPath $invoicePath
    $exitCode = $LASTEXITCODE
    $expectedExitCode = if ($case.status -eq "analyzed") { 0 } else { 2 }
    if ($exitCode -ne $expectedExitCode) {
        throw "$($case.file): código de saída $exitCode, esperado $expectedExitCode."
    }

    $report = $json | ConvertFrom-Json
    if ($report.contract_version -ne "fiscal-engine-v1" -or $report.status -ne $case.status) {
        throw "$($case.file): contrato ou status inesperado."
    }

    $actualCodes = @($report.alerts | ForEach-Object { $_.code } | Sort-Object)
    $expectedCodes = @($case.alert_codes | Sort-Object)
    if (Compare-Object -ReferenceObject $expectedCodes -DifferenceObject $actualCodes) {
        throw "$($case.file): alertas inesperados: $($actualCodes -join ', ')."
    }
    $verified += 1
}

$archivePath = Join-Path $testDataRoot $manifest.archive.file
if (-not (Test-Path -LiteralPath $archivePath)) {
    throw "Lote ZIP sintético ausente: $archivePath"
}

$batchCases = @($manifest.cases | Where-Object { $_.desktop_boundary -eq $null } | Select-Object -First 3)
$batchPaths = @($batchCases | ForEach-Object { Join-Path $testDataRoot $_.file })
$batchJson = @(& $binaryPath "--desktop-batch" @batchPaths)
if ($LASTEXITCODE -ne 0) {
    throw "Sidecar rejeitou a matriz em lote com código $LASTEXITCODE."
}
if ($batchJson.Count -ne $batchCases.Count) {
    throw "Fluxo em lote retornou $($batchJson.Count) itens, esperado $($batchCases.Count)."
}
for ($index = 0; $index -lt $batchJson.Count; $index += 1) {
    $batchLine = $batchJson[$index] | ConvertFrom-Json
    if ($batchLine.index -ne $index -or $batchLine.report.status -ne $batchCases[$index].status) {
        throw "Fluxo em lote retornou item inesperado no índice $index."
    }
}

Write-Output "Matriz sintética verificada: $verified cenários individuais e $($batchJson.Count) itens em lote."
