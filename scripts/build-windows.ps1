# Build a DeskOS Windows executable.
#
#   .\scripts\build-windows.ps1            # normal build
#   .\scripts\build-windows.ps1 -Test      # run the test suite first
#
# Produces dist\DeskOS\DeskOS.exe (one folder, unsigned).

param(
    [switch]$Test,
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not $SkipInstall) {
    if (-not (Test-Path ".venv\Scripts\python.exe")) {
        Write-Host "Creating virtual environment..."
        py -3.11 -m venv .venv
    }
    & ".venv\Scripts\python.exe" -m pip install --upgrade pip
    & ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    & ".venv\Scripts\python.exe" -m pip install -e ".[build]"
    if ($LASTEXITCODE -ne 0) { throw "dependency installation failed" }
}

$Python = ".venv\Scripts\python.exe"

if ($Test) {
    Write-Host "Running the test suite..."
    $env:QT_QPA_PLATFORM = "offscreen"
    & $Python -m pytest
    if ($LASTEXITCODE -ne 0) { throw "tests failed; not building" }
    & $Python -m deskos --self-test
    if ($LASTEXITCODE -ne 0) { throw "self-test failed; not building" }
}

Write-Host "Building with PyInstaller..."
& $Python scripts\build.py
if ($LASTEXITCODE -ne 0) { throw "build failed" }

$Exe = Join-Path $Root "dist\DeskOS\DeskOS.exe"
if (-not (Test-Path $Exe)) { throw "expected output missing: $Exe" }

Write-Host ""
Write-Host "Done: $Exe"
Write-Host "Distribute the whole dist\DeskOS folder, not just the .exe."
