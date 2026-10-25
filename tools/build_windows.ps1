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
    # Some managed Python distributions load an adjacent SSL trust-policy file
    # when SSLContext is constructed. urllib initializes that context even for
    # plain HTTP. Preserve the runtime's policy file in the frozen application.
    $taskRuntimeCa = & $taskBuildPython -c "import pathlib,ssl; p=pathlib.Path(ssl.__file__).with_name('codex-rejected-cas.pem'); print(p if p.is_file() else '')"
    if ($taskRuntimeCa) {
        $taskBuildArgs = @('--add-data', ($taskRuntimeCa + ':.')) + $taskBuildArgs
    }
    if ($IncludeAI) {
        & $taskBuildPython -m pip install ultralytics
        if ($LASTEXITCODE -ne 0) { throw 'AI build dependencies failed' }
        $taskBuildArgs = @('--collect-all', 'ultralytics') + $taskBuildArgs
    }
    & $taskBuildPython -m PyInstaller @taskBuildArgs
    if ($LASTEXITCODE -ne 0) { throw 'Application build failed' }
    & $taskBuildPython tools/check_windows_connection.py
    if ($LASTEXITCODE -ne 0) { throw 'Packaged application failed connection check' }
    Write-Output 'Built dist\VAMP-Operator.exe'
} finally {
    Pop-Location
}
