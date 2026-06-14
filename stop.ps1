# =============================================================================
#  Affinity-Core  -  Stop All Services
#  Run from the project root:  .\stop.ps1
# =============================================================================

param(
    [switch]$SkipDocker,
    [switch]$StopDocker
)

$Root = $PSScriptRoot

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "   Affinity-Core  -  Stopping All Services " -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# -- Kill Python processes by their command-line signatures -------------------
$targets = @(
    @{ Name = "Mock gRPC Engine";    Match = "*mock_grpc_server*" },
    @{ Name = "FastAPI Backend";     Match = "*uvicorn*server_fastapi*" },
    @{ Name = "ARQ Worker";          Match = "*arq*task_queue*" }
)

foreach ($t in $targets) {
    $procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like $t.Match }
    if ($procs) {
        foreach ($p in $procs) {
            Write-Host "  Stopping $($t.Name)  (PID $($p.ProcessId))..." -ForegroundColor Yellow
            Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        }
        Write-Host "  [OK] $($t.Name) stopped" -ForegroundColor Green
    } else {
        Write-Host "  [INFO] $($t.Name) was not running" -ForegroundColor Gray
    }
}

# -- Kill C++ Engine processes ------------------------------------------------
$cppTargets = @(
    "entry_live_grpc",
    "entry_backtest",
    "entry_gateway",
    "entry_market_data",
    "entry_live"
)
foreach ($c in $cppTargets) {
    $procs = Get-Process -Name $c -ErrorAction SilentlyContinue
    if ($procs) {
        foreach ($p in $procs) {
            Write-Host "  Stopping C++ Engine target $($c) (PID $($p.Id))..." -ForegroundColor Yellow
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        }
        Write-Host "  [OK] C++ target $($c) stopped" -ForegroundColor Green
    }
}

# -- Kill Node / Next.js on port 3000 ----------------------------------------
Write-Host "  Stopping Next.js Frontend (:3000)..." -ForegroundColor Yellow
$nodeProcs = Get-NetTCPConnection -LocalPort 3000 -ErrorAction SilentlyContinue |
             Select-Object -ExpandProperty OwningProcess -Unique
foreach ($nodePid in $nodeProcs) {
    Stop-Process -Id $nodePid -Force -ErrorAction SilentlyContinue
}
if ($nodeProcs) {
    Write-Host "  [OK] Next.js stopped" -ForegroundColor Green
} else {
    Write-Host "  [INFO] Next.js was not running" -ForegroundColor Gray
}

Write-Host ""

# -- Docker containers --------------------------------------------------------
$choice = ""
if ($SkipDocker) {
    $choice = "n"
} elseif ($StopDocker) {
    $choice = "y"
} else {
    $choice = Read-Host "  Stop Docker containers (PostgreSQL + Redis)? [y/N]"
}

if ($choice -match '^[Yy]$') {
    Write-Host "  Stopping Docker containers..." -ForegroundColor Yellow
    Set-Location $Root
    docker compose down
    Write-Host "  [OK] Containers stopped (data preserved)" -ForegroundColor Green
    Write-Host ""
    Write-Host "  TIP: To also delete all database data, run:" -ForegroundColor Gray
    Write-Host "       docker compose down -v" -ForegroundColor Gray
} else {
    Write-Host "  [INFO] Docker containers left running" -ForegroundColor Gray
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "   Done. All Python/Node services stopped.  " -ForegroundColor Cyan
Write-Host "   To restart, run:  .\start.ps1            " -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
