# KarSaathi: one-command local run (Windows PowerShell).
#   .\run.ps1            build the UI if needed, start API + UI on http://127.0.0.1:8000
#   .\run.ps1 -Reseed    reset the demo data first
#   .\run.ps1 -Dev       API on :8000 and Vite dev server on :5173 (hot reload)
param([switch]$Reseed, [switch]$Dev)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

# The seeded story (Oct 2026 return, Nov e-way bills) is built around this date.
if (-not $env:KARSAATHI_TODAY) { $env:KARSAATHI_TODAY = "2026-11-16" }

Push-Location "$root\backend"
pip install -q -r requirements.txt
if ($Reseed -or -not (Test-Path "data\karsaathi.db")) { python -m app.seed }
Pop-Location

Push-Location "$root\frontend"
if (-not (Test-Path "node_modules")) { npm install --no-fund --no-audit }
if ($Dev) {
  Start-Process -FilePath "npm" -ArgumentList "run", "dev" -WorkingDirectory "$root\frontend"
} elseif (-not (Test-Path "dist\index.html")) {
  npm run build
}
Pop-Location

Push-Location "$root\backend"
Write-Host "KarSaathi on http://127.0.0.1:8000  (Claude: $(if ($env:ANTHROPIC_API_KEY) {'on'} else {'off, set ANTHROPIC_API_KEY to enable'}))"
python -m uvicorn app.main:app --port 8000
Pop-Location
