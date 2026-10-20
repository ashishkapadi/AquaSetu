$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    throw 'First create .venv and install requirements.txt as described in README.md.'
}
if (-not (Test-Path -LiteralPath 'frontend\dist\index.html')) {
    Push-Location -LiteralPath 'frontend'
    try {
        npm.cmd install
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
        npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    } finally { Pop-Location }
}
if (-not (Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue)) {
    & '.venv\Scripts\python.exe' -m pip show streamlit *> $null
    if ($LASTEXITCODE -ne 0) {
        & '.venv\Scripts\python.exe' -m pip install -r 'Dashboard\jalbach\requirements.txt'
        if ($LASTEXITCODE -ne 0) { throw 'Dashboard dependency installation failed.' }
    }
    Start-Process -FilePath '.venv\Scripts\python.exe' -ArgumentList '-m','streamlit','run','app.py','--server.address','127.0.0.1','--server.port','8501','--server.headless','true' -WorkingDirectory (Join-Path $PSScriptRoot 'Dashboard\jalbach') -WindowStyle Hidden
}
Write-Host 'Requiem: http://127.0.0.1:8000 — press Ctrl+C to stop.'
Write-Host 'Planning dashboard: http://127.0.0.1:8501'
& '.venv\Scripts\python.exe' -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
