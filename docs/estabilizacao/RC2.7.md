# RC2.7 — Estabilização

## Incluído
- migrações versionadas pela tabela `schema_migrations`;
- índices de produção para agenda, clientes e WhatsApp;
- logs rotativos em `logs/bytech_agenda.log`;
- endpoint `GET /health` para monitoramento;
- configuração de webhook com criação automática da configuração da empresa;
- bloqueio de webhook apontando para localhost;
- scripts de backup e restauração PostgreSQL;
- testes básicos de importação e rota de saúde;
- auditoria SQL PostgreSQL ampliada.

## Validação
```powershell
py -m compileall .
py scripts/maintenance/verificar_sql_postgresql.py
py -m unittest discover -s tests -v
```

## Backup
```powershell
$env:DATABASE_URL="postgresql://..."
.\scripts\database\backup_postgresql.ps1
```

## Monitoramento
A VPS ou proxy deve consultar `/health`. HTTP 200 indica banco disponível; HTTP 503 indica falha.
