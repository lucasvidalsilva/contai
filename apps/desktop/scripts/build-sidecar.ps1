$ErrorActionPreference = "Stop"

$desktopRoot = Split-Path -Parent $PSScriptRoot
$repositoryRoot = (Resolve-Path (Join-Path $desktopRoot "..\..")).Path
$engineProject = Join-Path $repositoryRoot "packages\fiscal-engine"
$entrypoint = Join-Path $desktopRoot "sidecar\entrypoint.py"
$binaryDirectory = Join-Path $desktopRoot "src-tauri\binaries"
$buildRoot = Join-Path $desktopRoot "var\pyinstaller"
$rustcCommand = Get-Command rustc -ErrorAction SilentlyContinue
$rustcPath = if ($null -ne $rustcCommand) {
    $rustcCommand.Source
} else {
    Join-Path $env:USERPROFILE ".cargo\bin\rustc.exe"
}

if (-not (Test-Path -LiteralPath $rustcPath)) {
    throw "rustc não encontrado; instale o toolchain stable-msvc antes de construir o sidecar."
}

$hostLine = & $rustcPath -vV | Where-Object { $_ -like "host: *" }
$targetTriple = ($hostLine -replace "^host:\s*", "").Trim()
if ($targetTriple -ne "x86_64-pc-windows-msvc") {
    throw "O primeiro corte desktop suporta somente x86_64-pc-windows-msvc; alvo detectado: $targetTriple"
}

New-Item -ItemType Directory -Force -Path $binaryDirectory | Out-Null
New-Item -ItemType Directory -Force -Path $buildRoot | Out-Null

$binaryName = "contai-fiscal-engine-$targetTriple"
& uv run --project $engineProject pyinstaller `
    --noconfirm `
    --clean `
    --onefile `
    --name $binaryName `
    --distpath $binaryDirectory `
    --workpath (Join-Path $buildRoot "work") `
    --specpath $buildRoot `
    --paths (Join-Path $engineProject "src") `
    --collect-data contai_fiscal_engine `
    $entrypoint

if ($LASTEXITCODE -ne 0) {
    throw "Falha ao construir o sidecar fiscal."
}

$binaryPath = Join-Path $binaryDirectory "$binaryName.exe"
if (-not (Test-Path -LiteralPath $binaryPath)) {
    throw "PyInstaller não produziu o binário esperado: $binaryPath"
}

Write-Output "Sidecar fiscal construído: $binaryPath"
