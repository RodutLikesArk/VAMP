param([string]$Python = 'python', [switch]$IncludeAI)
$ErrorActionPreference = 'Stop'
$taskRepoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $taskRepoRoot
try {
    & $Python -m venv .venv-build
    if ($LASTEXITCODE -ne 0) { throw 'Could not create build environment' }
    $taskBuildPython = Join-Path $taskRepoRoot '.venv-build\Scripts\python.exe'
    & $taskBuildPython -m pip install -r pc/requirements.txt 'pyinstaller>=6,<7'
    if ($LASTEXITCODE -ne 0) { throw 'Build dependencies failed' }
    & $taskBuildPython tools/make_icon.py
    $taskBuildArgs = @('--noconfirm', '--noupx', '--onefile', '--windowed', '--name', 'VAMP-Operator', '--icon', 'pc/assets/vamp.ico', '--add-data', 'pc/assets:pc/assets', '--paths', '.', 'VAMP.pyw')
    if ($IncludeAI) {
        & $taskBuildPython -m pip install ultralytics
        if ($LASTEXITCODE -ne 0) { throw 'AI build dependencies failed' }
        $taskBuildArgs = @('--collect-all', 'ultralytics') + $taskBuildArgs
    }
    & $taskBuildPython -m PyInstaller @taskBuildArgs
    if ($LASTEXITCODE -ne 0) { throw 'Application build failed' }
    Write-Output 'Built dist\VAMP-Operator.exe'
} finally {
    Pop-Location
}
