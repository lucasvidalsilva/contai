param(
    [string]$InstallerPath
)

$ErrorActionPreference = "Stop"

$desktopRoot = Split-Path -Parent $PSScriptRoot
$defaultInstaller = Join-Path $desktopRoot "src-tauri\target\release\bundle\nsis\contAI_0.1.0_x64-setup.exe"
$installer = if ([string]::IsNullOrWhiteSpace($InstallerPath)) { $defaultInstaller } else { $InstallerPath }
$installRoot = Join-Path $desktopRoot "var\install-smoke"
$appPath = Join-Path $installRoot "contai-desktop.exe"
$sidecarPath = Join-Path $installRoot "contai-fiscal-engine.exe"
$uninstallerPath = Join-Path $installRoot "uninstall.exe"
$app = $null

if (-not (Test-Path -LiteralPath $installer)) {
    throw "Instalador ausente: $installer"
}
if (Test-Path -LiteralPath $installRoot) {
    throw "O destino isolado já existe e não será sobrescrito: $installRoot"
}

try {
    $install = Start-Process -FilePath $installer -ArgumentList "/S", "/D=$installRoot" -WindowStyle Hidden -Wait -PassThru
    if ($install.ExitCode -ne 0) {
        throw "Instalador encerrou com código $($install.ExitCode)."
    }
    foreach ($path in ($appPath, $sidecarPath, $uninstallerPath)) {
        if (-not (Test-Path -LiteralPath $path)) {
            throw "Artefato instalado ausente: $path"
        }
    }

    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "verify-test-invoices.ps1") -BinaryPath $sidecarPath
    if ($LASTEXITCODE -ne 0) {
        throw "O sidecar instalado falhou na matriz sintética."
    }

    $env:WEBVIEW2_USER_DATA_FOLDER = Join-Path $env:TEMP "contai-installer-smoke-webview"
    $stderrPath = Join-Path $env:TEMP "contai-installer-smoke-stderr.txt"
    $app = Start-Process -FilePath $appPath -WindowStyle Hidden -RedirectStandardError $stderrPath -PassThru
    Start-Sleep -Seconds 8
    $app.Refresh()
    if ($app.HasExited) {
        $stderr = if (Test-Path -LiteralPath $stderrPath) {
            Get-Content -Raw -LiteralPath $stderrPath
        } else {
            ""
        }
        throw "O aplicativo instalado encerrou durante o smoke test. $stderr"
    }
    Stop-Process -Id $app.Id
    $app = $null
} finally {
    if ($null -ne $app -and -not $app.HasExited) {
        Stop-Process -Id $app.Id
    }
    if (Test-Path -LiteralPath $uninstallerPath) {
        $uninstall = Start-Process -FilePath $uninstallerPath -ArgumentList "/S" -WindowStyle Hidden -Wait -PassThru
        if ($uninstall.ExitCode -ne 0) {
            throw "Desinstalador encerrou com código $($uninstall.ExitCode)."
        }
        Start-Sleep -Seconds 2
    }
}

if (Test-Path -LiteralPath $installRoot) {
    throw "O desinstalador não removeu o destino isolado: $installRoot"
}

Write-Output "Instalador verificado: instalação, 12 cenários, inicialização e desinstalação concluídas."
