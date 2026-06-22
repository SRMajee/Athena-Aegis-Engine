# =============================================================================
#  Affinity-Core  -  Start All Services
#  Run from the project root:  .\start.ps1
# =============================================================================

$env:PATH = "C:\msys64\mingw64\bin;$env:PATH"

$Root      = $PSScriptRoot
$Backend   = Join-Path $Root "backend_orchestrator"
$Frontend  = Join-Path $Root "frontend_terminal"
$Venv      = Join-Path $Backend ".venv\Scripts\Activate.ps1"

# Helper: open a new, titled PowerShell window and run a command inside it
function Start-Service {
    param(
        [string]$Title,
        [string]$WorkDir,
        [string]$Command,
        [string]$Color = "DarkBlue"
    )
    $escaped = $Command -replace '"', '\"'
    $cmd = "Set-Location '$WorkDir'; `$host.UI.RawUI.WindowTitle = '$Title'; $escaped"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $cmd
    Start-Sleep -Milliseconds 400
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "   Affinity-Core  -  Starting All Services " -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# -- 1. Docker (PostgreSQL + Redis) -------------------------------------------
Write-Host "[1/5] Starting Docker containers (PostgreSQL + Redis)..." -ForegroundColor Yellow
Set-Location $Root
docker compose up -d
if ($LASTEXITCODE -ne 0) {
    Write-Host "      [!]  docker compose failed - is Docker Desktop running?" -ForegroundColor Red
} else {
    Write-Host "      [OK] PostgreSQL :5433  Redis :6379" -ForegroundColor Green
}
Write-Host ""

# Wait a moment for containers to be healthy
Write-Host "      Waiting 3s for containers to be ready..." -ForegroundColor Gray
Start-Sleep -Seconds 3

# -- 2. C++ Engine Binaries (Gateway, Market Data, gRPC Engine) -----------------
Write-Host "[2/5] Opening windows: C++ Engine Helper processes..." -ForegroundColor Yellow
$CppBuild = Join-Path $Root "cpp_engine\build"

Start-Service `
    -Title    "AFFINITY - C++ entry_gateway" `
    -WorkDir  $CppBuild `
    -Command  "`$env:PATH = 'C:\msys64\mingw64\bin;' + `$env:PATH; .\entry_gateway.exe"

Start-Service `
    -Title    "AFFINITY - C++ entry_market_data" `
    -WorkDir  $CppBuild `
    -Command  "`$env:PATH = 'C:\msys64\mingw64\bin;' + `$env:PATH; .\entry_market_data.exe"

Start-Sleep -Seconds 1

Write-Host "      Opening window: C++ gRPC Engine (:50051)..." -ForegroundColor Yellow
Start-Service `
    -Title    "AFFINITY - C++ gRPC Engine :50051" `
    -WorkDir  $CppBuild `
    -Command  "`$env:PATH = 'C:\msys64\mingw64\bin;' + `$env:PATH; .\entry_live_grpc.exe"
Write-Host "      [OK] Windows opened" -ForegroundColor Green

Start-Sleep -Seconds 2   # let gRPC bind before FastAPI connects

# -- 3. FastAPI Backend -------------------------------------------------------
Write-Host "[3/5] Opening window: FastAPI Backend (:8085)..." -ForegroundColor Yellow
Start-Service `
    -Title    "AFFINITY - FastAPI Backend :8085" `
    -WorkDir  $Backend `
    -Command  "& '$Venv'; python -m uvicorn server_fastapi:app --host 0.0.0.0 --port 8085 --reload"
Write-Host "      [OK] Window opened" -ForegroundColor Green

Start-Sleep -Seconds 2

# -- 4. ARQ Worker ------------------------------------------------------------
Write-Host "[4/5] Opening window: ARQ Worker (backtest jobs)..." -ForegroundColor Yellow
Start-Service `
    -Title    "AFFINITY - ARQ Worker" `
    -WorkDir  $Backend `
    -Command  "& '$Venv'; python -m arq src.infra.task_queue.WorkerSettings"
Write-Host "      [OK] Window opened" -ForegroundColor Green

# -- 5. Next.js Frontend ------------------------------------------------------
Write-Host "[5/5] Opening window: Next.js Frontend (:3000)..." -ForegroundColor Yellow
Start-Service `
    -Title    "AFFINITY - Next.js Frontend :3000" `
    -WorkDir  $Frontend `
    -Command  "`$env:NEXT_PUBLIC_API_URL='http://localhost:8085'; npm run dev"
Write-Host "      [OK] Window opened" -ForegroundColor Green

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "   All services launching in new windows!  " -ForegroundColor Cyan
Write-Host "   Frontend ->  http://localhost:3000        " -ForegroundColor Cyan
Write-Host "   Backend  ->  http://localhost:8085        " -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  To stop everything, run:  .\stop.ps1" -ForegroundColor Gray
Write-Host ""
