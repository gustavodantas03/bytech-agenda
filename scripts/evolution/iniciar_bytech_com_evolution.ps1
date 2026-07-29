$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "../..")
$envFile = Join-Path $root "docker/evolution/.env.evolution"
if (-not (Test-Path $envFile)) { throw "Arquivo docker/evolution/.env.evolution não encontrado." }
$apiLine = Get-Content $envFile | Where-Object { $_ -match '^AUTHENTICATION_API_KEY=' } | Select-Object -First 1
if (-not $apiLine) { throw "AUTHENTICATION_API_KEY não encontrada no arquivo da Evolution." }
$env:EVOLUTION_BASE_URL = "http://127.0.0.1:8080"
$env:EVOLUTION_API_KEY = ($apiLine -split '=', 2)[1].Trim()
$env:EVOLUTION_TIMEOUT = "15"
Set-Location $root
Write-Host "Evolution configurada para o Bytech Agenda." -ForegroundColor Green
py app.py
