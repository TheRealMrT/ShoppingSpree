# ── Boodschappen start.ps1 ──────────────────────────────────────
# Run from the boodschappen/ directory:  .\scripts\start.ps1
# ────────────────────────────────────────────────────────────────

$ErrorActionPreference = "Continue"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectDir = Split-Path -Parent $scriptDir
Set-Location $projectDir

Write-Host "=== Boodschappen ===" -ForegroundColor Green
Write-Host "Projectmap: $projectDir"

# ── Ollama (optioneel) ───────────────────────────────────────────
$ollamaJob = $null
$ollamaCmd = Get-Command ollama -ErrorAction SilentlyContinue
if ($ollamaCmd) {
    Write-Host "`nOllama gevonden. Starten in achtergrond..." -ForegroundColor Cyan
    $ollamaJob = Start-Job -ScriptBlock { ollama serve } -Name "OllamaServe"
    Write-Host "Ollama gestart (Job ID: $($ollamaJob.Id))"
    # Sla job-ID op voor stop.ps1
    $ollamaJob.Id | Out-File -FilePath ".ollama_job_id" -Encoding utf8
} else {
    Write-Host "`nOllama niet gevonden, overgeslagen." -ForegroundColor Yellow
    if (Test-Path ".ollama_job_id") { Remove-Item ".ollama_job_id" }
}

# ── Uvicorn ──────────────────────────────────────────────────────
Write-Host "`nBoodschappen starten op http://localhost:8000 ..." -ForegroundColor Green

# Controleer of uvicorn beschikbaar is
$uvicornCmd = Get-Command uvicorn -ErrorAction SilentlyContinue
if (-not $uvicornCmd) {
    # Probeer via Python module
    $uvicornAvailable = python -m uvicorn --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "uvicorn niet gevonden. Installeer dependencies:" -ForegroundColor Red
        Write-Host "  pip install -r requirements.txt"
        exit 1
    }
    $uvicornExe = "python -m uvicorn"
} else {
    $uvicornExe = "uvicorn"
}

# Start uvicorn als achtergrond-job en sla PID op
$uvicornJob = Start-Job -ScriptBlock {
    param($dir)
    Set-Location $dir
    uvicorn main:app --reload --port 8000
} -ArgumentList $projectDir -Name "BoodschappenApp"

$uvicornJob.Id | Out-File -FilePath ".uvicorn_job_id" -Encoding utf8
Write-Host "Uvicorn gestart (Job ID: $($uvicornJob.Id))"

# Wacht even totdat de server klaar is
Write-Host "Even wachten..." -ForegroundColor Yellow
Start-Sleep -Seconds 3

# ── Browser openen ────────────────────────────────────────────────
Write-Host "`nBrowser openen..." -ForegroundColor Cyan
Start-Process "http://localhost:8000"

Write-Host "`n✅ App draait op http://localhost:8000" -ForegroundColor Green
Write-Host "   Stop met: .\scripts\stop.ps1`n"

# Laat de output van uvicorn zien
Write-Host "--- Server logs (Ctrl+C om dit venster te minimaliseren) ---" -ForegroundColor DarkGray
Receive-Job -Job $uvicornJob -Wait -AutoRemoveJob
