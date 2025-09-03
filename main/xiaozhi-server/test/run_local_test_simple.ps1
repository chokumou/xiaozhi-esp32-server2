param(
    [string]$Token = "<YOUR_JWT>",
    [string]$DeviceId = "test-device"
)

Write-Host "Simple local test: server (background) + emulator (foreground)"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ServerDir = Resolve-Path (Join-Path $Root "..")
$TestDir = Resolve-Path $Root
$LogDir = Join-Path $TestDir "test_logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

$ServerPython = Join-Path $ServerDir ".venv\Scripts\python.exe"
if (-not (Test-Path $ServerPython)) { Write-Error "venv python not found: $ServerPython"; exit 1 }

Write-Host "Ensuring port 8090 is free..."
try {
    $conns = Get-NetTCPConnection -LocalPort 8090 -ErrorAction Stop
    foreach ($c in $conns) {
        if ($c.State -eq 'Listen' -or $c.State -eq 'Established') {
            Write-Host "Killing process using port 8090 (Id: $($c.OwningProcess))"
            Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    }
} catch {
    # Get-NetTCPConnection may not exist on older Windows; fallback to netstat parsing
    $net = netstat -ano | Select-String ":8090"
    foreach ($line in $net) {
        $parts = ($line -split "\s+") | Where-Object { $_ -ne "" }
        $pid = $parts[-1]
        if ($pid -match "^\d+$") {
            Write-Host "Killing PID $pid"
            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
        }
    }
}

Write-Host "Starting uvicorn (background) with LOCAL_TEST_DISABLE_AUTH=1..."
Write-Host "Starting app.py (background) with LOCAL_TEST_DISABLE_AUTH=1 and PORT=8090..."
$cmd = "set PORT=8090 && `"$ServerPython`" `"$ServerDir\\app.py`""
$serverProc = Start-Process -FilePath "cmd.exe" -ArgumentList "/c", $cmd -WorkingDirectory $ServerDir -WindowStyle Hidden -RedirectStandardOutput (Join-Path $LogDir "server.log") -RedirectStandardError (Join-Path $LogDir "server_error.log") -PassThru
Start-Sleep -Seconds 2

$emulatorScript = Join-Path $TestDir "emulate_device_ws.py"
$url = "ws://localhost:8090/ws?token=$Token&device_id=$DeviceId&local_test=1"
Write-Host "Running emulator (will show output here)..."
$emArgs = @($emulatorScript, "--url", $url, "--device-id", $DeviceId, "--token", $Token)

& $ServerPython @emArgs 2>&1 | Tee-Object -FilePath (Join-Path $LogDir "emulator.log")
$exitCode = $LASTEXITCODE

Write-Host "Emulator finished (exit code: $exitCode). Stopping server..."
try { Stop-Process -Id $serverProc.Id -Force -ErrorAction SilentlyContinue } catch {}

Write-Host "----- server.log (tail 200) -----"
Get-Content -Path (Join-Path $LogDir "server.log") -Tail 200 -ErrorAction SilentlyContinue
Write-Host "----- emulator.log (tail 200) -----"
Get-Content -Path (Join-Path $LogDir "emulator.log") -Tail 200 -ErrorAction SilentlyContinue

Write-Host "----- token/MEM_SAVE matches -----"
Select-String -Pattern "token|MEM_SAVE" -Path (Join-Path $LogDir "*") -ErrorAction SilentlyContinue

Write-Host "Logs saved to: $LogDir"


