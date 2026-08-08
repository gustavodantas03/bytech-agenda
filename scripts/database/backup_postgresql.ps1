param(
    [string]$Destino = ".\\backups",
    [int]$RetencaoDias = 14
)
$ErrorActionPreference = "Stop"
if (-not $env:DATABASE_URL) { throw "Defina DATABASE_URL antes de executar o backup." }
New-Item -ItemType Directory -Force -Path $Destino | Out-Null
$data = Get-Date -Format "yyyyMMdd_HHmmss"
$arquivo = Join-Path $Destino "bytech_agenda_$data.dump"
pg_dump --format=custom --no-owner --no-acl --file=$arquivo $env:DATABASE_URL
if ($LASTEXITCODE -ne 0) { throw "pg_dump falhou com código $LASTEXITCODE" }
Get-ChildItem $Destino -Filter "bytech_agenda_*.dump" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$RetencaoDias) } |
    Remove-Item -Force
Write-Host "Backup criado: $arquivo"
