# run_api_tests.ps1
# Runs the backend API unit/integration tests directly using the virtualenv python interpreter.

$BackendDir = Join-Path $PSScriptRoot "backend_orchestrator"
$PythonExe = Join-Path $BackendDir ".venv\Scripts\python.exe"

if (-not (Test-Path $PythonExe)) {
    Write-Error "Python virtual environment executor not found at: $PythonExe"
    exit 1
}

Write-Host "Executing FastAPI Backend API tests..." -ForegroundColor Cyan
& $PythonExe -m pytest -v --rootdir=$BackendDir (Join-Path $BackendDir "tests")
