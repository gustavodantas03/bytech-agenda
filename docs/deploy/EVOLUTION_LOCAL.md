# Evolution API local

Esta etapa sobe uma infraestrutura isolada para testar a integração do Bytech Agenda:

- Evolution API `v2.3.7`;
- PostgreSQL exclusivo da Evolution;
- Redis exclusivo da Evolution;
- volumes persistentes;
- acesso local pela porta `8080`.

O PostgreSQL do Bytech Agenda continua separado no container `bytech-postgres`.

## Iniciar

Na raiz do projeto, execute:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/evolution/iniciar_evolution.ps1
```

Ou manualmente:

```powershell
docker compose -f docker/docker-compose.evolution.yml up -d
```

## Conferir containers

```powershell
docker compose -f docker/docker-compose.evolution.yml ps
```

Devem aparecer:

- `bytech-evolution-api`;
- `bytech-evolution-postgres`;
- `bytech-evolution-redis`.

## Testar a API

```powershell
powershell -ExecutionPolicy Bypass -File scripts/evolution/testar_evolution.ps1
```

A chave local inicial é:

```text
bytech_evolution_local_2026
```

Ela existe apenas para teste local. Antes de publicar, altere `AUTHENTICATION_API_KEY` em `docker/evolution/.env.evolution`.

## Ver logs

```powershell
docker compose -f docker/docker-compose.evolution.yml logs -f evolution-api
```

## Parar sem apagar os dados

```powershell
docker compose -f docker/docker-compose.evolution.yml stop
```

## Remover containers sem apagar volumes

```powershell
docker compose -f docker/docker-compose.evolution.yml down
```

Não use `down -v` depois de conectar o WhatsApp, pois esse comando também remove os volumes persistentes.

## Configuração no Bytech Agenda

Para o teste local:

```env
EVOLUTION_BASE_URL=http://127.0.0.1:8080
EVOLUTION_API_KEY=bytech_evolution_local_2026
```

A criação da instância e a leitura do QR Code serão validadas na próxima etapa, depois que os três containers estiverem saudáveis.
