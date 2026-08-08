param([Parameter(Mandatory=$true)][string]$Arquivo)
$ErrorActionPreference = "Stop"
if (-not $env:DATABASE_URL) { throw "Defina DATABASE_URL antes de restaurar." }
if (-not (Test-Path $Arquivo)) { throw "Arquivo não encontrado: $Arquivo" }
pg_restore --clean --if-exists --no-owner --no-acl --dbname=$env:DATABASE_URL $Arquivo
if ($LASTEXITCODE -ne 0) { throw "pg_restore falhou com código $LASTEXITCODE" }
Write-Host "Restauração concluída."
