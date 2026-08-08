## RC2.6.0 — WhatsApp bidirecional

- Webhook público da Evolution com token opcional e proteção contra eventos duplicados.
- Respostas 1, 2 e 3 confirmam, iniciam reagendamento ou cancelam.
- Reagendamento completo por data e horário disponíveis.
- Sessões persistentes de conversa por empresa e telefone.
- Histórico de mensagens recebidas e respostas automáticas.
- Script para configurar o webhook da instância na Evolution.

# Changelog

## RC1.3.4 — Compatibilidade CRM e relatórios

- Corrigido `HAVING` que referenciava o alias `ultima_visita`, não permitido pelo PostgreSQL.
- Corrigida comparação entre `clientes.criado_em` (texto legado) e parâmetros de data nos relatórios.
- Mantida compatibilidade com SQLite e PostgreSQL usando datas ISO (`YYYY-MM-DD`).


## RC1.3.2

- Corrigida a chamada incompatível de `executemany()` no script de migração para psycopg 3.
- Adicionado `executemany()` à camada de compatibilidade PostgreSQL.
- Organizados documentos em `docs/`.
- Organizados scripts em `scripts/`.
- Movido o Docker Compose para `docker/`.
- Removidos caches Python do pacote.

## RC1.3.3 — Compatibilidade SQL PostgreSQL

- Tradução automática de `GROUP_CONCAT(...)` para `STRING_AGG(...)` na conexão PostgreSQL.
- Mantida a compatibilidade das mesmas consultas com o fallback SQLite.
- Adicionado verificador estático em `scripts/maintenance/verificar_sql_postgresql.py`.
- Corrigido o erro 500 do Dashboard causado por `UndefinedFunction: group_concat`.

## RC1.3.5 — Infraestrutura Evolution local

- adicionada Evolution API v2.3.7 em Docker;
- adicionados PostgreSQL e Redis exclusivos para a Evolution;
- adicionados volumes persistentes e healthchecks;
- adicionados scripts PowerShell para iniciar, testar e parar;
- adicionada documentação em `docs/deploy/EVOLUTION_LOCAL.md`.

## RC2.3.0 - Integração Evolution no painel
- credenciais globais por variáveis de ambiente;
- cliente final não vê URL ou API Key;
- criação automática de instância por empresa;
- QR Code e status no painel;
- desconexão e mensagem de teste;
- consulta automática de status;
- scripts para ambiente local e vínculo de instância existente.

## RC2.3.2 — Identidade e navegação do agendamento

- Aplicado o ícone oficial do Bytech Agenda no painel administrativo, SuperAdmin, logins, favicon e fallback das páginas públicas.
- A seta da página de agendamento agora retorna à etapa anterior.
- Na primeira etapa, a seta retorna à página inicial da empresa.
- Respostas do usuário são atualizadas ao refazer uma etapa, evitando bolhas duplicadas.

## RC2.4 — Validação nativa da Evolution
- Sincronização do status da instância no painel.
- Leitura e armazenamento do número, nome e foto do WhatsApp conectado.
- Registro da resposta da Evolution no histórico de mensagens de teste.
- Bloqueio do teste quando a instância não estiver conectada.
- Atualização visual automática do perfil e da última sincronização.

## RC2.5.0 — Motor de automações do WhatsApp
- Adicionado worker separado do Flask para processar confirmações e lembretes sem bloquear o agendamento.
- Adicionado ciclo automático de geração dos lembretes de 24 horas e 2 horas.
- Adicionadas retentativas progressivas para mensagens pendentes na fila existente.
- Adicionados scripts para execução contínua e diagnóstico de um único ciclo.
- O agendamento público agora vincula corretamente o registro ao CRM por `cliente_id`.
- O telefone do cliente é normalizado antes de ser salvo e enviado ao WhatsApp.

## RC2.7.0 - Estabilização e operação
- Migrações versionadas com tabela `schema_migrations`.
- Índices adicionais para PostgreSQL.
- Logs rotativos e endpoint `/health`.
- Webhook com validação de HTTPS e criação automática da configuração.
- Backup/restauração PostgreSQL e testes de fumaça.
