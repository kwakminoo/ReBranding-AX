param([string]$Source, [string]$Bundle, [switch]$Hooks, [switch]$InstallPython)
$ErrorActionPreference = 'Stop'
$axRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $axRoot
function Find-AxPython {
    $axCandidates = @()
    $axCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($axCommand -and $axCommand.Source -notlike '*WindowsApps*') { $axCandidates += $axCommand.Source }
    foreach ($axVersion in @('314', '313', '312', '311')) {
        $axCandidates += Join-Path $env:LOCALAPPDATA "Programs\Python\Python$axVersion\python.exe"
    }
    foreach ($axCandidate in $axCandidates) {
        if (Test-Path -LiteralPath $axCandidate) {
            & $axCandidate -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' 2>$null
            if ($LASTEXITCODE -eq 0) { return $axCandidate }
        }
    }
    return $null
}
$axPython = Find-AxPython
if (-not $axPython -and $InstallPython) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw 'Install Python 3.11+ from python.org, then rerun setup.' }
    winget install --id Python.Python.3.14 --exact --source winget --scope user --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw 'Python installation failed. See README.md.' }
    $axPython = Find-AxPython
}
if (-not $axPython) { throw 'Python 3.11+ required. Rerun with -InstallPython or install it from python.org.' }
if ($Source -and $Bundle) { throw 'Specify either Source or Bundle, not both.' }
# Restore first so a customized private config is not shadowed by setup defaults.
if ($Bundle) {
    & $axPython -X utf8 scripts/ax.py restore $Bundle
    if ($LASTEXITCODE -ne 0) { throw 'Private data restore failed; existing files are not overwritten.' }
}
$axSetupArgs = @('-X', 'utf8', 'scripts/ax.py', 'setup')
if ($Hooks) { $axSetupArgs += '--hooks' }
& $axPython @axSetupArgs
if ($LASTEXITCODE -ne 0) { throw 'Setup failed.' }
if ($Source) {
    & $axPython -X utf8 scripts/ax.py import-source $Source
    if ($LASTEXITCODE -ne 0) { throw 'Source import failed.' }
}
& $axPython -X utf8 scripts/ax.py doctor
if ($LASTEXITCODE -ne 0) { throw 'Doctor failed: restore private data and check missing files.' }
Write-Host 'Local setup ready. Open this folder as a Codex project and follow the app checks in README.md.'
if ($Hooks) { Write-Host 'Hooks require review and trust in Codex. This installer does not bypass hook trust.' }
