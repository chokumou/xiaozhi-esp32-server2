Param()

function Find-VenvActivate {
    param([string]$startDir)
    $cur = Get-Item -Path $startDir
    for ($i = 0; $i -lt 8; $i++) {
        $cand = Join-Path $cur.FullName ".venv\Scripts\Activate.ps1"
        if (Test-Path $cand) { return $cand }
        if ($cur.Parent -eq $null) { break }
        $cur = $cur.Parent
    }
    return $null
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Write-Host "Running test from: $scriptDir"

# try to find and activate virtualenv
$activate = Find-VenvActivate -startDir $scriptDir
if ($activate) {
    Write-Host "Activating venv: $activate"
    & $activate
} else {
    Write-Host "No .venv found automatically. Please activate your venv manually and re-run this script." -ForegroundColor Yellow
}

# prepare logs
$logDir = Join-Path $scriptDir "test_logs"
New-Item -Path $logDir -ItemType Directory -Force | Out-Null
$serverLog = Join-Path $logDir "server.log"
$serverErr = Join-Path $logDir "server.err.log"
$emuLog = Join-Path $logDir "emulator.log"

Write-Host "Starting uvicorn (railway_app:app) -- logs -> $serverLog"
$uvicornArgs = "-m uvicorn railway_app:app --host 0.0.0.0 --port 8090"
$uvicornProc = Start-Process -FilePath python -ArgumentList $uvicornArgs -RedirectStandardOutput $serverLog -RedirectStandardError $serverErr -PassThru
Start-Sleep -Seconds 2

if ($uvicornProc -eq $null) {
    Write-Host "Failed to start uvicorn. Check your Python environment." -ForegroundColor Red
    exit 1
}

Write-Host "Uvicorn started with PID: $($uvicornProc.Id)"

# get JWT from user
$jwt = Read-Host "Paste device JWT (or leave empty to skip emulator)"
if ($jwt -and $jwt.Trim() -ne "") {
    Write-Host "Running emulator... (logs -> $emuLog)"
    $emuScript = Join-Path $scriptDir "emulate_device_ws.py"
    if (-not (Test-Path $emuScript)) {
        Write-Host "Emulator script not found: $emuScript" -ForegroundColor Red
    } else {
        # Run emulator and capture output
        & python $emuScript --url ws://localhost:8090/ws --device-id test-device --token $jwt *> $emuLog
        Write-Host "Emulator finished. See $emuLog"
    }
} else {
    Write-Host "No JWT provided - skipping emulator run." -ForegroundColor Yellow
}

Start-Sleep -Seconds 2

Write-Host "--- Server log (tail) ---"
if (Test-Path $serverLog) { Get-Content $serverLog -Tail 200 } else { Write-Host "Server log not found: $serverLog" }
if (Test-Path $serverErr) { Write-Host "--- Server stderr (tail) ---"; Get-Content $serverErr -Tail 200 }

Write-Host "--- Search for token/MEM_SAVE in server log ---"
if (Test-Path $serverLog) { Select-String -Path $serverLog -Pattern "token=","[MEM_SAVE]","Save memory successful" -SimpleMatch } else { Write-Host "Server log not found" }

if (Test-Path $emuLog) {
    Write-Host "--- Emulator log (tail) ---"
    Get-Content $emuLog -Tail 200
}

Write-Host "Stopping uvicorn (PID $($uvicornProc.Id))"
Stop-Process -Id $uvicornProc.Id -Force
Write-Host "Done. Logs are in: $logDir"


