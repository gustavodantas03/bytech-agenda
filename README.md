# Bytech Agenda

Sistema SaaS de agendamento, CRM, financeiro, fidelidade e comunicação.

## Estrutura principal

```text
app.py                     Entrada da aplicação
core.py                    Configuração do Flask e registro de rotas
config.py                  Configurações gerais
database.py                Camada compatível com PostgreSQL/SQLite
routes/                     Rotas da aplicação
services/                   Regras de negócio e integrações
templates/                  Telas HTML
static/                     CSS, JavaScript, sons e uploads
database/                   Banco SQLite de origem e arquivos legados
docker/                     Ambiente PostgreSQL local
docs/                       Documentação organizada
scripts/                    Migração, diagnóstico e manutenção
```

## PostgreSQL local

```powershell
docker compose -f docker/docker-compose.postgres.yml up -d
$env:DATABASE_URL="postgresql://bytech:bytech123@127.0.0.1:5432/bytech_agenda"
py -m pip install -r requirements.txt
py scripts/database/migrar_sqlite_para_postgresql.py
py app.py
```

Para recriar somente o PostgreSQL de teste:

```powershell
docker compose -f docker/docker-compose.postgres.yml down -v
docker compose -f docker/docker-compose.postgres.yml up -d
```

O SQLite em `database/bytech_agenda.db` deve ser preservado até a conferência completa dos dados migrados.
