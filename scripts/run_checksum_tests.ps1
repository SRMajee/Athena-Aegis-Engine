<#
.SYNOPSIS
    NFR-03 Deterministic Replay Checksum Test Suite - CI Runner

.DESCRIPTION
    Runs verify_determinism.py against a configurable set of parquet files and
    strategies. Prints a summary table and exits non-zero if any test fails.

    Usage (from workspace root):
        .\scripts\run_checksum_tests.ps1
        .\scripts\run_checksum_tests.ps1 -Symbol SPY -Strategy StraddleTestStrategy -MaxFiles 5
        .\scripts\run_checksum_tests.ps1 -Runs 3 -VerboseOutput
        .\scripts\run_checksum_tests.ps1 -Parquet "data\SPY\2010\01\2010-01-04.parquet" -Strategy IronCondorTestStrategy

.PARAMETER Symbol
    Filter to a specific symbol directory under data\. Default: "" (all symbols).

.PARAMETER Strategy
    Strategy class to pass to entry_backtest. Default: StraddleTestStrategy.

.PARAMETER Runs
    Number of identical runs per file (--runs N). Default: 2.

.PARAMETER MaxFiles
    Maximum number of parquet files to test (to limit CI time). 0 = unlimited. Default: 10.

.PARAMETER Timeout
    Per-run timeout in seconds. Default: 300.

.PARAMETER Parquet
    Test a single specific parquet file path (workspace-relative or absolute).

.PARAMETER VerboseOutput
    Pass --verbose to verify_determinism.py for per-field diff on failure.

.PARAMETER PythonExe
    Path to Python executable. Default: "python".
#>

[CmdletBinding()]
param(
    [string]$Symbol        = "",
    [string]$Strategy      = "StraddleTestStrategy",
    [int]   $Runs          = 2,
    [int]   $MaxFiles      = 10,
    [int]   $Timeout       = 300,
    [string]$Parquet       = "",
    [switch]$VerboseOutput,
    [string]$PythonExe     = "python"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Ensure MSYS2/MinGW64 DLLs are available for the C++ binary
$mingwBin = if ($env:MINGW64_BIN) { $env:MINGW64_BIN } else { "C:\msys64\mingw64\bin" }
if (Test-Path $mingwBin) {
    $env:PATH = "$mingwBin;$env:PATH"
}

# --- Paths -------------------------------------------------------------------
$ScriptDir     = Split-Path -Parent $MyInvocation.MyCommand.Path
$WorkspaceRoot = Split-Path -Parent $ScriptDir
$VerifyScript  = Join-Path $ScriptDir "verify_determinism.py"
$DataDir       = Join-Path $WorkspaceRoot "data"

if (-not (Test-Path $VerifyScript)) {
    Write-Error "verify_determinism.py not found at: $VerifyScript"
    exit 2
}

# --- Collect test cases ------------------------------------------------------
$testCases = [System.Collections.Generic.List[hashtable]]::new()

if ($Parquet -ne "") {
    # Single file mode
    $resolved = if ([System.IO.Path]::IsPathRooted($Parquet)) {
        $Parquet
    } else {
        Join-Path $WorkspaceRoot $Parquet
    }
    if (-not (Test-Path $resolved)) {
        Write-Error "Parquet file not found: $resolved"
        exit 2
    }
    $testCases.Add(@{ Parquet = $resolved; Label = (Split-Path -Leaf $resolved) })

} else {
    $searchRoot = if ($Symbol -ne "") {
        Join-Path $DataDir $Symbol
    } else {
        $DataDir
    }

    if (-not (Test-Path $searchRoot)) {
        Write-Error "Data directory not found: $searchRoot"
        exit 2
    }

    $files = Get-ChildItem -Path $searchRoot -Recurse -Filter "*.parquet" |
             Where-Object { $_.Name -match '^\d{4}-\d{2}-\d{2}\.parquet$' } |
             Sort-Object FullName

    if ($files.Count -eq 0) {
        $files = Get-ChildItem -Path $searchRoot -Recurse -Filter "*.parquet" |
                 Sort-Object FullName
    }

    if ($files.Count -eq 0) {
        Write-Error "No .parquet files found under: $searchRoot"
        exit 2
    }

    if ($MaxFiles -gt 0 -and $files.Count -gt $MaxFiles) {
        Write-Host "  Limiting to $MaxFiles of $($files.Count) available files." -ForegroundColor Cyan
        $files = $files | Select-Object -First $MaxFiles
    }

    foreach ($f in $files) {
        $label = $f.FullName.Replace($WorkspaceRoot, "").TrimStart('\', '/')
        $testCases.Add(@{ Parquet = $f.FullName; Label = $label })
    }
}

# --- Banner ------------------------------------------------------------------
$sep = "-" * 78
Write-Host $sep -ForegroundColor DarkGray
Write-Host "  NFR-03 Deterministic Replay Checksum Test Suite" -ForegroundColor Cyan
Write-Host $sep -ForegroundColor DarkGray
Write-Host "  Strategy  : $Strategy"
Write-Host "  Runs/file : $Runs"
Write-Host "  Timeout   : ${Timeout}s per run"
Write-Host "  Files     : $($testCases.Count)"
Write-Host $sep -ForegroundColor DarkGray
Write-Host ""

# --- Run tests ---------------------------------------------------------------
$results = [System.Collections.Generic.List[PSCustomObject]]::new()
$passed  = 0
$failed  = 0

foreach ($tc in $testCases) {
    $label = $tc.Label
    Write-Host "  Testing: $label" -ForegroundColor White

    $pyArgs = @(
        "-X", "utf8",
        $VerifyScript,
        "--parquet", $tc.Parquet,
        "--strategy", $Strategy,
        "--runs", $Runs,
        "--timeout", $Timeout
    )
    if ($VerboseOutput) { $pyArgs += "--verbose" }

    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        & $PythonExe @pyArgs
        $exitCode = $LASTEXITCODE
    } catch {
        $exitCode = 99
        Write-Host "  Exception: $_" -ForegroundColor Red
    }
    $sw.Stop()
    $duration = [math]::Round($sw.Elapsed.TotalSeconds, 1)

    if ($exitCode -eq 0) {
        $status = "PASS"
        $passed++
        Write-Host "  => PASS ($($duration)s)" -ForegroundColor Green
    } elseif ($exitCode -eq 2) {
        $status = "CONFIG_ERROR"
        $failed++
        Write-Host "  => CONFIG ERROR (exit 2)" -ForegroundColor Yellow
    } else {
        $status = "FAIL"
        $failed++
        Write-Host "  => FAIL ($($duration)s)" -ForegroundColor Red
    }
    Write-Host ""

    $results.Add([PSCustomObject]@{
        Label    = $label
        Status   = $status
        Duration = "${duration}s"
    })
}

# --- Summary table -----------------------------------------------------------
$colLabel  = 58
$colStatus = 14
$colDur    = 8
$innerSep  = "-" * ($colLabel + $colStatus + $colDur + 2)

Write-Host $sep -ForegroundColor DarkGray
Write-Host "  SUMMARY" -ForegroundColor Cyan
Write-Host $sep -ForegroundColor DarkGray

$header = "  {0,-$colLabel} {1,-$colStatus} {2,$colDur}" -f "File", "Status", "Duration"
Write-Host $header -ForegroundColor DarkGray
Write-Host "  $innerSep" -ForegroundColor DarkGray

foreach ($r in $results) {
    $colour = switch ($r.Status) {
        "PASS"         { "Green" }
        "FAIL"         { "Red" }
        "CONFIG_ERROR" { "Yellow" }
        default        { "White" }
    }
    $shortLabel = if ($r.Label.Length -gt $colLabel) {
        "..." + $r.Label.Substring($r.Label.Length - ($colLabel - 3))
    } else {
        $r.Label
    }
    $line = "  {0,-$colLabel} {1,-$colStatus} {2,$colDur}" -f $shortLabel, $r.Status, $r.Duration
    Write-Host $line -ForegroundColor $colour
}

Write-Host ""
Write-Host $sep -ForegroundColor DarkGray
$totalColour = if ($failed -eq 0) { "Green" } else { "Red" }
Write-Host "  Total: $($results.Count) | PASS: $passed | FAIL: $failed" -ForegroundColor $totalColour
Write-Host $sep -ForegroundColor DarkGray
Write-Host ""

if ($failed -gt 0) {
    Write-Host "  DETERMINISM CHECK FAILED - $failed test(s) did not produce identical checksums." -ForegroundColor Red
    exit 1
} else {
    Write-Host "  ALL TESTS PASSED - backtest engine is deterministic across all tested files." -ForegroundColor Green
    exit 0
}
