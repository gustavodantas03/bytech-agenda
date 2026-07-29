# RC2.4 — Validação nativa da Evolution

## Objetivo
Validar pelo painel do Bytech Agenda o ciclo: consultar conexão, sincronizar perfil, enviar mensagem de teste e registrar a resposta no histórico.

## Execução local
1. Mantenha PostgreSQL e Evolution API ativos.
2. Defina `DATABASE_URL`, `EVOLUTION_BASE_URL` e `EVOLUTION_API_KEY`.
3. Execute `py app.py`.
4. Acesse `/admin/comunicacao/whatsapp`.
5. Atualize o status e envie uma mensagem de teste.

## Critérios de aceite
- Status exibido como conectado.
- Número/nome do perfil exibidos quando retornados pela Evolution.
- Mensagem recebida no telefone de destino.
- Envio registrado no histórico, incluindo resposta da API.
