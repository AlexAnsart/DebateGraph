# Run backend using venv Python (avoids "user install" and reload subprocess using wrong interpreter).
# From backend/: .\run.ps1
$venvPython = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Error "venv not found. Create it: python -m venv venv"
    exit 1
}

# Free port 8010 if already in use (Windows Errno 10048)
$pids = @()
try {
    $conn = Get-NetTCPConnection -LocalPort 8010 -State Listen -ErrorAction SilentlyContinue
    if ($conn) { $pids = $conn.OwningProcess | Sort-Object -Unique }
} catch {}
if (-not $pids.Count) {
    $line = netstat -ano | Select-String ":8010"
    if ($line) {
        $pids = @(($line.Line -split '\s+')[-1])
    }
}
if ($pids) {
    foreach ($p in $pids) {
        Write-Host "Killing process $p on port 8010"
        taskkill /PID $p /F 2>$null
    }
    Start-Sleep -Seconds 2
}

& $venvPython -m uvicorn main:app --host 0.0.0.0 --port 8010 --reload --reload-exclude "venv"
