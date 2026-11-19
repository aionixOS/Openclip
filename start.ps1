# start.ps1 - Start the OpenClip backend and frontend on Windows.
# Press Ctrl+C to stop both servers.
#
# Usage (from the repo root):
#   powershell -ExecutionPolicy Bypass -File .\start.ps1

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

Write-Host ""
Write-Host "=========================================="
Write-Host "          Starting OpenClip"
Write-Host "=========================================="
Write-Host ""

# ------------------------------------------
# Setup must have run first
# ------------------------------------------
$venvPython = Join-Path $PSScriptRoot 'backend\.venv\Scripts\python.exe'
$missing = @()
if (-not (Test-Path 'backend\.env'))          { $missing += 'backend\.env' }
if (-not (Test-Path 'frontend\.env.local'))   { $missing += 'frontend\.env.local' }
if (-not (Test-Path $venvPython))             { $missing += 'backend\.venv' }
if (-not (Test-Path 'frontend\node_modules')) { $missing += 'frontend\node_modules' }
if ($missing.Count -gt 0) {
    foreach ($m in $missing) { Write-Host "Error: $m not found" -ForegroundColor Red }
    Write-Host ""
    Write-Host "Please run setup first:" -ForegroundColor Yellow
    Write-Host "  powershell -ExecutionPolicy Bypass -File .\setup.ps1"
    exit 1
}

# ------------------------------------------
# Warn about missing tools (non-fatal)
# ------------------------------------------
$wingetFfmpeg = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffmpeg.exe'
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue) -and -not (Test-Path $wingetFfmpeg)) {
    Write-Host "Warning: ffmpeg not found. Video processing will fail." -ForegroundColor Yellow
    Write-Host "  Install: winget install Gyan.FFmpeg"
    Write-Host ""
}
if (-not (Test-Path 'backend\.venv\Scripts\yt-dlp.exe') -and -not (Get-Command yt-dlp -ErrorAction SilentlyContinue)) {
    Write-Host "Warning: yt-dlp not found. Video downloads will fail. Run setup.ps1 again." -ForegroundColor Yellow
    Write-Host ""
}

# Frontend port comes from the "dev" script in frontend/package.json
$frontendPort = 3000
$devScript = (Get-Content 'frontend\package.json' -Raw | ConvertFrom-Json).scripts.dev
if ($devScript -match '-p\s+(\d+)') { $frontendPort = [int]$Matches[1] }

# ------------------------------------------
# Start both servers
# ------------------------------------------
Write-Host "Starting backend server..."
$backend = Start-Process -FilePath $venvPython `
    -ArgumentList '-m', 'uvicorn', 'api:app', '--reload', '--port', '8000' `
    -WorkingDirectory (Join-Path $PSScriptRoot 'backend') `
    -NoNewWindow -PassThru

Start-Sleep -Seconds 2

Write-Host "Starting frontend server..."
$frontend = Start-Process -FilePath 'npm.cmd' `
    -ArgumentList 'run', 'dev' `
    -WorkingDirectory (Join-Path $PSScriptRoot 'frontend') `
    -NoNewWindow -PassThru

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "         OpenClip is running!"               -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Frontend:  http://localhost:$frontendPort" -ForegroundColor Cyan
Write-Host "  Backend:   http://localhost:8000"          -ForegroundColor Cyan
Write-Host "  API Docs:  http://localhost:8000/docs"     -ForegroundColor Cyan
Write-Host ""
Write-Host "  Backend PID:  $($backend.Id)"
Write-Host "  Frontend PID: $($frontend.Id)"
Write-Host ""
Write-Host "Press Ctrl+C to stop both servers."
Write-Host ""

# uvicorn's --reload parent stays alive even if the app fails to start,
# so check that the backend actually answers. The first start can be slow
# while PyTorch / Whisper / MediaPipe load, so allow up to 3 minutes.
Write-Host "Waiting for the backend to finish starting..."
$ProgressPreference = 'SilentlyContinue'
$backendUp = $false
$deadline = (Get-Date).AddMinutes(3)
while ((Get-Date) -lt $deadline -and -not $backend.HasExited) {
    try {
        Invoke-WebRequest 'http://127.0.0.1:8000/docs' -UseBasicParsing -TimeoutSec 3 | Out-Null
        $backendUp = $true
        break
    } catch { Start-Sleep -Seconds 1 }
}
if ($backendUp) {
    Write-Host "Backend is up." -ForegroundColor Green
} else {
    Write-Host "Warning: backend is not responding on port 8000. Check the errors above." -ForegroundColor Yellow
}
Write-Host ""

# ------------------------------------------
# Wait; stop both process trees on Ctrl+C or if either server exits
# ------------------------------------------
try {
    while (-not $backend.HasExited -and -not $frontend.HasExited) {
        Start-Sleep -Seconds 1
    }
    if ($backend.HasExited)  { Write-Host "Backend stopped." -ForegroundColor Red }
    if ($frontend.HasExited) { Write-Host "Frontend stopped." -ForegroundColor Red }
} finally {
    Write-Host ""
    Write-Host "Shutting down..."
    foreach ($p in @($backend, $frontend)) {
        if ($p -and -not $p.HasExited) {
            # /T kills the whole tree (uvicorn reloader worker, next dev children)
            & taskkill.exe /PID $p.Id /T /F 2>&1 | Out-Null
        }
    }
}
