$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "../..")
$compose = Join-Path $root "docker/docker-compose.evolution.yml"
$envFile = Join-Path $root "docker/evolution/.env.evolution"
$envExample = Join-Path $root "docker/evolution/.env.evolution.example"

if (-not (Test-Path $envFile)) {
    Copy-Item $envExample $envFile
    Write-Host "Arquivo .env.evolution criado a partir do exemplo." -ForegroundColor Yellow
}

docker compose -f $compose up -d
if ($LASTEXITCODE -ne 0) { throw "Falha ao iniciar a Evolution API." }

Write-Host "Aguardando os containers..." -ForegroundColor Cyan
Start-Sleep -Seconds 12
docker compose -f $compose ps
Write-Host "Evolution API: http://127.0.0.1:8080" -ForegroundColor Green
