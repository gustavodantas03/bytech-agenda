# Auditoria técnica RC1 — Bytech Agenda

Base auditada: **RC1.2.0 — UX e Onboarding**  
Data: 28/07/2026

## Resumo executivo

A aplicação compila e o banco SQLite está íntegro, mas **ainda não deve ser publicada em produção**. Foram encontrados bloqueadores de segurança e de operação que precisam ser corrigidos antes da VPS.

### Resultado atual

- Compilação Python: **aprovada**
- Integridade do banco: **aprovada**
- Tabelas essenciais: **presentes**
- Rotas identificadas: **75**
- Rotas POST identificadas: **41**
- Templates: **37**
- CSS: **10 arquivos**
- JavaScript: **17 arquivos**
- Bancos `.db` dentro do pacote: **4**

## Bloqueadores de publicação — prioridade crítica

### 1. Senhas armazenadas e comparadas em texto puro

As rotas de login e conta consultam e atualizam a coluna `senha` diretamente. Isso precisa ser migrado para hash seguro com Werkzeug (`generate_password_hash` e `check_password_hash`).

Arquivos afetados:

- `routes/auth.py`
- `routes/conta.py`
- `routes/master.py`
- tabela `usuarios`
- tabela `usuarios_master`

**Risco:** vazamento completo das senhas em caso de acesso ao banco.

### 2. Ausência de proteção CSRF

Não há implementação ou referência a CSRF, apesar de existirem 41 rotas POST.

**Risco:** ações administrativas podem ser disparadas por páginas externas enquanto o usuário está autenticado.

### 3. Chave secreta padrão insegura

`config.py` mantém fallback fixo:

`bytech-dev-altere-em-producao`

Em produção, a aplicação deve recusar a inicialização quando `BYTECH_SECRET_KEY` não estiver definida.

### 4. Credencial global da Evolution exposta por empresa

O módulo atual salva `base_url` e `api_key` na tabela `whatsapp_configuracoes` de cada empresa e permite alteração pelo administrador da empresa.

Isso diverge do fluxo definido para o produto:

- a Bytech configura a Evolution uma vez na VPS;
- o cliente conecta apenas o próprio número por QR Code;
- URL e API Key devem ficar fora da área da empresa.

**Correção recomendada:** mover URL/API Key para variáveis de ambiente ou configuração exclusiva do SuperAdmin e manter por empresa somente `instance_name`, status, telefone e QR Code.

### 5. SQLite em produção multiempresa com worker concorrente

O sistema web e `processar_comunicacao.py` podem gravar simultaneamente no SQLite. Isso aumenta o risco de `database is locked`, principalmente com agenda, financeiro e fila de mensagens.

**Recomendação:** publicar já com PostgreSQL ou, no mínimo, tratar SQLite apenas como ambiente de demonstração/teste.

## Pendências altas

### 6. Quatro bancos incluídos no pacote

Existem:

- `bytech_agenda.db`
- `bytech_copia.db`
- `bytech_copia2.db`
- `bytech_copia3.db`

Isso aumenta o risco de executar ou migrar o banco errado. O pacote de produção deve conter apenas uma estratégia clara de criação/migração, sem cópias históricas.

### 7. Banco de produção dentro do ZIP

O banco atual acompanha o código. Para deploy, dados e aplicação devem ser separados. Backup também não deve ser distribuído junto do sistema.

### 8. Imports globais em 13 arquivos

Há uso recorrente de:

`from core import *`

Isso dificulta manutenção, testes, análise de dependências e pode mascarar conflitos de nomes.

### 9. Sem migrações versionadas

As tabelas são criadas/ajustadas por código, mas não há ferramenta de migração versionada. Para produção, alterações de esquema precisam ser rastreáveis e reversíveis.

### 10. Evolution API ainda não foi validada ponta a ponta

O código possui integração, fila e processador, mas o projeto ainda precisa ser testado contra uma instância real da Evolution:

1. criar instância;
2. gerar QR Code;
3. conectar número;
4. enviar teste;
5. criar agendamento;
6. confirmar envio;
7. disparar lembrete de 24h;
8. disparar lembrete de 2h;
9. validar nova tentativa em falha;
10. confirmar prevenção de duplicidade.

## Pendências médias

### 11. Divergência visual ainda possível

Foram encontrados:

- 24 atributos `style` inline;
- 8 blocos JavaScript inline;
- 10 arquivos CSS;
- 17 arquivos JS.

Isso explica parte das divergências visuais e de cache. A padronização ainda não está concluída.

### 12. Assistente do WhatsApp mistura área técnica e área do cliente

O template informa que a Bytech configura a infraestrutura, porém exibe URL e API Key ao administrador da empresa. O texto e o comportamento precisam seguir o mesmo modelo.

### 13. Dependências não instaladas no ambiente auditado

O verificador indicou ausência de Flask/Werkzeug no ambiente atual. A sintaxe foi validada, mas não foi possível executar testes funcionais completos do Flask nesta auditoria.

## Ordem recomendada de correção

### RC1.3.1 — Segurança obrigatória

1. Migrar senhas para hash.
2. Implementar CSRF em todos os formulários POST.
3. Tornar `BYTECH_SECRET_KEY` obrigatória em produção.
4. Configurar cookies de sessão seguros.
5. Adicionar limite de tentativas no login.

### RC1.3.2 — Arquitetura da Evolution

1. Remover URL/API Key da configuração por empresa.
2. Colocar credenciais globais em variáveis de ambiente.
3. Gerar instância automaticamente por empresa.
4. Exibir ao cliente somente QR Code, conexão, teste e automações.
5. Testar fluxo real com Evolution.

### RC1.3.3 — Banco e deploy

1. Migrar SQLite para PostgreSQL.
2. Criar migrações versionadas.
3. Remover bancos de cópia do pacote.
4. Preparar Gunicorn + Nginx + systemd/Docker.
5. Criar backup automático.

### RC1.3.4 — Testes finais

1. Fluxo público de agendamento.
2. Agenda administrativa.
3. CRM e Inteligência CRM.
4. Financeiro e fidelidade.
5. Comunicação e lembretes.
6. SuperAdmin e isolamento entre empresas.
7. Responsividade.
8. Teste de restauração de backup.

## Decisão de publicação

**Status: NÃO LIBERADO PARA PRODUÇÃO.**

O sistema está suficientemente avançado para entrar em fase de correção final, mas os itens 1 a 5 são bloqueadores. A primeira implementação deve ser a **RC1.3.1 — Segurança obrigatória**.
