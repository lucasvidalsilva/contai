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

Write-Output "Matriz sintética verificada: $verified cenários, contrato fiscal-engine-v1."
