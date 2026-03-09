# ── Boodschappen stop.ps1 ───────────────────────────────────────
# Stopt uvicorn en (optioneel) ollama serve
# ────────────────────────────────────────────────────────────────

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectDir = Split-Path -Parent $scriptDir
Set-Location $projectDir

Write-Host "=== Boodschappen stoppen ===" -ForegroundColor Yellow

# ── Uvicorn job ──────────────────────────────────────────────────
if (Test-Path ".uvicorn_job_id") {
    $jobId = [int](Get-Content ".uvicorn_job_id")
    $job = Get-Job -Id $jobId -ErrorAction SilentlyContinue
    if ($job) {
        Stop-Job -Job $job
        Remove-Job -Job $job -Force
        Write-Host "Uvicorn job gestopt (ID: $jobId)" -ForegroundColor Green
    } else {
        Write-Host "Uvicorn job $jobId niet gevonden (al gestopt?)" -ForegroundColor Yellow
    }
    Remove-Item ".uvicorn_job_id"
} else {
    Write-Host "Geen uvicorn job gevonden." -ForegroundColor Yellow
}

# Probeer ook direct Python/uvicorn processen te stoppen
Get-Process -Name "python", "python3", "uvicorn" -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowTitle -eq "" } |
    ForEach-Object {
        Write-Host "Stopzetten: $($_.Name) (PID $($_.Id))"
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }

# ── Ollama job ────────────────────────────────────────────────────
if (Test-Path ".ollama_job_id") {
    $jobId = [int](Get-Content ".ollama_job_id")
    $job = Get-Job -Id $jobId -ErrorAction SilentlyContinue
    if ($job) {
        Stop-Job -Job $job
        Remove-Job -Job $job -Force
        Write-Host "Ollama job gestopt (ID: $jobId)" -ForegroundColor Green
    }
    Remove-Item ".ollama_job_id"
}

# Probeer ook ollama process direct te stoppen
Get-Process -Name "ollama" -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "Ollama stoppen (PID $($_.Id))"
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}

Write-Host "`n✅ Klaar." -ForegroundColor Green
