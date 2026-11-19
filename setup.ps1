# setup.ps1 - OpenClip setup for Windows (PowerShell 5.1+ or PowerShell 7)
# Checks dependencies, creates .env files and installs Python + Node packages.
#
# Usage (from the repo root):
#   powershell -ExecutionPolicy Bypass -File .\setup.ps1

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

function Write-Ok($msg)   { Write-Host "OK" -ForegroundColor Green -NoNewline; Write-Host " $msg" }
function Write-Bad($msg)  { Write-Host "FAILED" -ForegroundColor Red -NoNewline; Write-Host " $msg" }
function Write-Hint($msg) { Write-Host "  $msg" }

Write-Host "=========================================="
Write-Host "       OpenClip Setup (Windows)"
Write-Host "=========================================="
Write-Host ""

$errors = 0

# ------------------------------------------
# Python >= 3.11
# Try the py launcher first, then python / python3. The WindowsApps
# "python3" alias opens the Microsoft Store instead of running Python,
# so every candidate must actually report a version to count.
# ------------------------------------------
Write-Host -NoNewline "Checking Python version... "
$python = $null
$pythonArgs = @()
$candidates = @(
    @{ exe = 'py';      args = @('-3') },
    @{ exe = 'python';  args = @() },
    @{ exe = 'python3'; args = @() }
)
foreach ($c in $candidates) {
    if (-not (Get-Command $c.exe -ErrorAction SilentlyContinue)) { continue }
    try {
        # No double quotes in the code: Windows PowerShell 5.1 strips them from native args
        $ver = & $c.exe @($c.args + @('-c', 'import sys; print(sys.version_info[0], sys.version_info[1], sep=chr(46))')) 2>$null
    } catch { $ver = $null }
    if ($LASTEXITCODE -eq 0 -and $ver -match '^(\d+)\.(\d+)$') {
        $python = $c.exe
        $pythonArgs = $c.args
        $pyMajor = [int]$Matches[1]
        $pyMinor = [int]$Matches[2]
        break
    }
}
if (-not $python) {
    Write-Bad "(not found)"
    Write-Hint "Install Python 3.11+ from https://www.python.org/downloads/"
    Write-Hint "Tick 'Add python.exe to PATH' in the installer."
    $errors++
} elseif ($pyMajor -gt 3 -or ($pyMajor -eq 3 -and $pyMinor -ge 11)) {
    Write-Ok "(Python $pyMajor.$pyMinor)"
} else {
    Write-Bad "(Python $pyMajor.$pyMinor - 3.11+ required)"
    Write-Hint "https://www.python.org/downloads/"
    $errors++
}

# ------------------------------------------
# Node.js >= 18
# ------------------------------------------
Write-Host -NoNewline "Checking Node.js version... "
if (Get-Command node -ErrorAction SilentlyContinue) {
    $nodeVer = (& node -v).Trim()
    $nodeMajor = [int]($nodeVer.TrimStart('v').Split('.')[0])
    if ($nodeMajor -ge 18) {
        Write-Ok "($nodeVer)"
    } else {
        Write-Bad "($nodeVer - 18+ required)"
        Write-Hint "https://nodejs.org/"
        $errors++
    }
} else {
    Write-Bad "(not found)"
    Write-Hint "Install Node.js 18+ from https://nodejs.org/  (or: winget install OpenJS.NodeJS.LTS)"
    $errors++
}

# ------------------------------------------
# FFmpeg (backend/ffbin.py also finds the winget install location)
# ------------------------------------------
Write-Host -NoNewline "Checking FFmpeg... "
$ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
if (-not $ffmpeg) {
    $winget = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffmpeg.exe'
    if (Test-Path $winget) { $ffmpeg = $winget }
}
if ($ffmpeg) {
    Write-Ok ""
} else {
    Write-Bad "(not found)"
    Write-Hint "Install it with:  winget install Gyan.FFmpeg"
    Write-Hint "then open a new terminal and run setup.ps1 again."
    $errors++
}

Write-Host ""
if ($errors -gt 0) {
    Write-Host "Setup cannot continue: $errors error(s). Fix the issues above and run setup.ps1 again." -ForegroundColor Red
    exit 1
}
Write-Host "All dependencies found!" -ForegroundColor Green
Write-Host ""

# ------------------------------------------
# .env files
# ------------------------------------------
Write-Host "Setting up environment files..."
$envFiles = @(
    @{ src = 'backend\.env.example';  dst = 'backend\.env' },
    @{ src = 'frontend\.env.example'; dst = 'frontend\.env.local' }
)
foreach ($f in $envFiles) {
    if (Test-Path $f.dst) {
        Write-Host "  $($f.dst) already exists"
    } elseif (Test-Path $f.src) {
        Copy-Item $f.src $f.dst
        Write-Host "  Created $($f.dst) from $($f.src)"
    }
}
Write-Host ""

# ------------------------------------------
# Python dependencies (into backend\.venv; includes yt-dlp)
# ------------------------------------------
Write-Host "Installing Python dependencies (this can take several minutes)..."
$venvPython = 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
    Write-Host "  Creating virtual environment..."
    & $python @($pythonArgs + @('-m', 'venv', 'backend\.venv'))
    if ($LASTEXITCODE -ne 0) { Write-Host "Could not create the virtual environment." -ForegroundColor Red; exit 1 }
}
& $venvPython -m pip install --upgrade pip --quiet
& $venvPython -m pip install -r backend\requirements.txt --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "pip install failed. Scroll up for the error." -ForegroundColor Red
    exit 1
}
Write-Host "  Python dependencies installed" -ForegroundColor Green
Write-Host ""

# ------------------------------------------
# Node dependencies
# ------------------------------------------
Write-Host "Installing Node.js dependencies..."
Push-Location frontend
try {
    & npm.cmd install --silent
    if ($LASTEXITCODE -ne 0) { Write-Host "npm install failed." -ForegroundColor Red; exit 1 }
} finally {
    Pop-Location
}
Write-Host "  Node.js dependencies installed" -ForegroundColor Green
Write-Host ""

# ------------------------------------------
# Directories
# ------------------------------------------
New-Item -ItemType Directory -Force -Path tmp, data | Out-Null

Write-Host "=========================================="  -ForegroundColor Green
Write-Host "         Setup Complete!"                     -ForegroundColor Green
Write-Host "=========================================="  -ForegroundColor Green
Write-Host ""
Write-Host "To start OpenClip, run:"
Write-Host ""
Write-Host "  powershell -ExecutionPolicy Bypass -File .\start.ps1"
Write-Host ""
