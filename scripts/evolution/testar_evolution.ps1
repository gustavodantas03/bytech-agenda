param(
    [string]$BaseUrl = "http://127.0.0.1:8080",
    [string]$ApiKey = "bytech_evolution_local_2026"
)

$ErrorActionPreference = "Stop"
Write-Host "1/2 Testando saúde da API..." -ForegroundColor Cyan
try {
    $health = Invoke-RestMethod -Uri "$BaseUrl/server/ok" -Method Get -TimeoutSec 15
    $health | ConvertTo-Json -Depth 8
} catch {
    Write-Host "A rota /server/ok não respondeu. Tentando /health..." -ForegroundColor Yellow
    $health = Invoke-RestMethod -Uri "$BaseUrl/health" -Method Get -TimeoutSec 15
    $health | ConvertTo-Json -Depth 8
}

Write-Host "2/2 Testando autenticação e listagem de instâncias..." -ForegroundColor Cyan
$instances = Invoke-RestMethod -Uri "$BaseUrl/instance/fetchInstances" -Method Get -Headers @{ apikey = $ApiKey } -TimeoutSec 20
$instances | ConvertTo-Json -Depth 10
Write-Host "Evolution API acessível e chave aceita." -ForegroundColor Green
