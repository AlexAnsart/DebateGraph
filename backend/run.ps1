# Run backend using venv Python (avoids "user install" and reload subprocess using wrong interpreter).
# From backend/: .\run.ps1
$venvPython = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Error "venv not found. Create it: python -m venv venv"
    exit 1
}
& $venvPython -m uvicorn main:app --host 0.0.0.0 --port 8010 --reload --reload-exclude "venv"
