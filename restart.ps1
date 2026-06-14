# =============================================================================
#  Affinity-Core  -  Restart All Services
#  Run from the project root:  .\restart.ps1
# =============================================================================

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "   Affinity-Core  -  Restarting All Services" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Stop all services first (keeping Docker containers running by passing -SkipDocker)
Write-Host "Stopping all running services..." -ForegroundColor Yellow
.\stop.ps1 -SkipDocker

Write-Host "Waiting 2s for processes to release resources..." -ForegroundColor Gray
Start-Sleep -Seconds 2

# Start all services
Write-Host "Starting all services..." -ForegroundColor Yellow
.\start.ps1
