$root = Resolve-Path (Join-Path $PSScriptRoot "../..")
docker compose -f (Join-Path $root "docker/docker-compose.evolution.yml") stop
