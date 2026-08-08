# Correções aplicadas — Bytech Agenda SaaS

## 1. Painel Master e CRM não funcionavam

**Causa:** as rotas `/master`, `/master/empresas`, `/master/financeiro/dashboard`
e `/admin/crm` usavam funções SQL exclusivas do PostgreSQL (`TO_CHAR`,
`DATE_TRUNC`, `generate_series`, `INTERVAL`, `::date`), mas o sistema estava
rodando em SQLite (sem `DATABASE_URL` configurada). Isso derrubava as páginas
com erro 500 — confirmado nos tracebacks de `logs/bytech_agenda.log`.

**Correção:** todas as consultas foram reescritas para calcular datas e
competências (mês/ano) em Python, funcionando igual em SQLite e PostgreSQL.
Arquivos alterados: `core.py`, `routes/master.py`, `routes/clientes.py`.

Testado com requisições reais em: `/master`, `/master/empresas`,
`/master/financeiro/dashboard`, `/admin/crm`, `/admin/crm/inteligencia`,
`/admin/clientes` (todos os filtros) e `/admin/clientes/<id>` (perfil 360º).
Todas retornando 200.

## 2. Mensagem de confirmação só chegava ao clicar "Atualizar status"

**Causa:** o sistema só *enfileira* as mensagens (tabela `whatsapp_fila`).
Quem realmente envia é um worker separado
(`scripts/evolution/executar_worker.py`) que precisa ficar rodando o tempo
todo — e não estava.

**Correção:** adicionado um worker embutido que roda automaticamente dentro
do processo do próprio `app.py`, em uma thread de segundo plano, processando
a fila a cada 60 segundos sozinho. Não é mais necessário clicar em nada nem
rodar um segundo processo/terminal.

Pode ser desligado com `BYTECH_EMBED_WORKER=0` no `.env` caso um dia o
sistema seja publicado com múltiplos processos do Gunicorn (nesse cenário,
use o worker separado para não haver envio duplicado).

## 3. Mensagem de cancelamento nunca era enviada

**Causa:** nenhuma rota do sistema disparava a mensagem de tipo
`cancelamento` quando um agendamento era cancelado.

**Correção:** adicionado o envio automático da mensagem de cancelamento nos
dois pontos em que um agendamento pode ser cancelado:
- botão "Cancelar" (`/admin/agendamentos/<id>/cancelar`)
- troca de status na agenda (`/admin/agendamentos/<id>/status`)

A mesma rota de troca de status também passou a enviar a confirmação
automaticamente quando o status muda para "confirmado" (útil quando o
agendamento é criado manualmente pelo salão, sem passar pela página pública).

## 4. Cliente que manda mensagem para agendar não recebia direcionamento

**Causa:** quando um cliente mandava mensagem para o WhatsApp do
estabelecimento sem ter um agendamento ativo, o bot respondia apenas "Não
encontrei um agendamento ativo... entre em contato com o estabelecimento" —
um beco sem saída.

**Correção:** essa mensagem agora inclui o link direto da página pública de
agendamento da empresa (ex.: `https://sua-url/nome-da-empresa/agendar`). Para
não repetir a mensagem a cada texto do cliente, ela só é reenviada depois de
6 horas.

**Importante:** defina a variável `BYTECH_PUBLIC_URL` no `.env` de produção
com a URL pública onde o sistema está publicado (ex.:
`https://agenda.suaempresa.com.br`), sem barra no final. Sem isso, o link
enviado será relativo (só o caminho `/slug/agendar`), o que não abre
corretamente dentro do WhatsApp.

## 5. Senhas salvas em texto puro (correção de segurança)

**Causa:** login do admin e do master comparavam a senha digitada diretamente
com o valor salvo no banco — ou seja, as senhas de todas as contas ficavam
gravadas em texto puro. Qualquer acesso ao banco (vazamento, backup mal
guardado, etc.) expunha a senha de login de todos os seus clientes.

**Correção:** todas as senhas agora são salvas com hash seguro
(`pbkdf2:sha256`, via Werkzeug). Pontos alterados:
- Login do admin (`/admin/login`) e do master (`/master/login`).
- Troca de senha pelo próprio usuário (`/admin/minha-conta`).
- Criação de nova empresa e reset de senha pelo painel master.
- Seed inicial do banco (usuário demo `admin/admin123` e master
  `bytech/trocar123`).

**Migração automática e transparente:** contas que já existiam com senha em
texto puro (como as que você já cadastrou) continuam funcionando
normalmente — no próximo login bem-sucedido de cada usuário, o sistema
detecta que a senha ainda não está em hash e a converte automaticamente no
banco, sem exigir nenhuma ação manual sua nem dos seus clientes.

Também ajustei a tela "empresa criada" do painel master: ela ainda mostra a
senha provisória para você copiar e enviar ao cliente, mas agora isso é feito
sem nunca ler a senha (nem o hash dela) de volta do banco — ela é exibida
uma única vez, na hora da criação.

Testado: login com senha em hash, login com senha antiga em texto puro
(confirmando a migração automática), senha incorreta sendo rejeitada, troca
de senha pela conta, e criação de nova empresa pelo master — todos os
cenários se comportaram corretamente.

## 6. PostgreSQL em produção

Você perguntou se valeria a pena usar PostgreSQL na VPS — vale, e o sistema
já foi desenhado para isso (o SQLite é só o fallback usado em
desenvolvimento local). Revisei a camada de compatibilidade
(`PostgresConnection` em `database.py`) e não encontrei mais nenhum ponto
cego: a tradução de `INSERT OR IGNORE`, `GROUP_CONCAT`, `AUTOINCREMENT` e os
placeholders `?`→`%s` já funciona corretamente para os dois bancos, e todas
as consultas que corrigi nas seções 1 e 3 usam apenas sintaxe compatível com
ambos.

Para migrar seus dados atuais (SQLite) para o PostgreSQL da VPS, já existe
um script pronto: `scripts/database/migrar_sqlite_para_postgresql.py`. Ele
também é compatível com a correção de senha — as senhas antigas migram como
estão e são convertidas para hash automaticamente no primeiro login de cada
usuário, sem trabalho extra.

## 7. Gestão de equipe com permissões por usuário (novo)

Você perguntou onde criar um segundo usuário do plano Essencial — não
existia essa tela. Construí do zero, em "Minha Conta → Gerenciar usuários
da equipe" (`/admin/equipe`):

- **Dois papéis por usuário:**
  - **Proprietário** — acesso total, incluindo gerenciar a própria equipe.
    Sua conta atual foi migrada automaticamente para este papel.
  - **Colaborador** — acesso só às áreas que você marcar: Agenda, Clientes/CRM,
    Fidelidade, Serviços, Profissionais, Comunicação (WhatsApp), Relatórios
    e Dados do estabelecimento.
- **Menu lateral se adapta**: um colaborador só vê no menu as seções que
  pode acessar.
- **Bloqueio no back-end**, não só visual: mesmo que o colaborador digite a
  URL de uma área não liberada, o sistema bloqueia e redireciona.
- **Respeita o limite do plano** (`limite_usuarios` de cada plano — 2 no
  Essencial, ilimitado no Profissional/Premium). Ao atingir o limite, criar
  ou reativar um usuário fica bloqueado com uma mensagem explicando.
- **Usuário pode ser desativado sem ser excluído** (fica bloqueado, libera
  vaga no plano, mas o histórico dele continua no sistema).
- **Proteções contra erro humano**: não deixa a empresa ficar sem nenhum
  proprietário ativo, e não deixa você desativar o próprio usuário logado.
- Só o **proprietário** acessa a tela de equipe — um colaborador nunca
  consegue criar outro usuário para si mesmo com mais acesso.

Testado de ponta a ponta: criação de colaborador, login com permissão
restrita (bloqueado corretamente nas áreas não liberadas), edição de
permissões, limite do plano sendo respeitado, e as proteções contra
autodesativação e "empresa sem proprietário".

## 8. Segurança: CSRF, cookies e bloqueio por tentativas de login (novo)

Três reforços de segurança pedidos por você, implementados sem depender de
bibliotecas externas (o ambiente não tinha acesso à internet para instalar
pacotes novos, então tudo foi feito com o que já vem no Flask/Werkzeug):

- **Proteção CSRF em todo formulário e ação do painel admin/master** —
  cada sessão recebe um token único; toda ação que muda dados (criar,
  editar, excluir, cancelar, etc.) exige esse token, seja num campo oculto
  do formulário, seja no header `X-CSRFToken` (usado pelas chamadas via
  JavaScript, como a agenda). Isso impede que outro site force o navegador
  de alguém já logado a executar uma ação sem que a pessoa perceba. A
  página pública de agendamento e o webhook da Evolution API ficam de fora
  dessa exigência (não fazem sentido nesse contexto, já que não usam sessão
  autenticada de dono de empresa).
- **Cookie de sessão mais seguro** — `HttpOnly` (nunca acessível via
  JavaScript) e `SameSite=Lax` (não é enviado em requisições disparadas por
  outros sites) já estão ativos. O flag `Secure` (exige HTTPS) fica pronto
  para ativar assim que o domínio da Hostinger estiver com certificado
  configurado — basta colocar `BYTECH_FORCE_HTTPS=1` no `.env`.
- **Bloqueio por tentativas de login erradas** — depois de 5 tentativas
  seguidas com senha errada (tanto no login do admin quanto no do master),
  a conta fica bloqueada por 15 minutos, mesmo que a senha certa seja usada
  durante esse período. Isso dificulta ataques de força bruta contra os
  logins dos seus clientes.

Testado: geração e validação do token CSRF em formulário e via header
JavaScript (bloqueando corretamente sem o token e liberando com o token
certo, incluindo o fluxo real de cancelamento de agendamento pela agenda),
e o bloqueio automático após 5 tentativas erradas — confirmando que nem a
senha correta destrava o acesso durante o período de bloqueio.

## 9. Horário de funcionamento configurável (novo)

Você reparou que não dava pra ajustar o horário de agendamento — o sistema
usava um horário fixo no código (09h às 18h, a cada 40 minutos) em 4 lugares
diferentes, inclusive na página pública onde o cliente marca horário. O
campo "Horário de funcionamento" que já existia em "Meu Espaço" era só
texto informativo — não controlava os horários realmente oferecidos.

**Corrigido e construído do zero:** nova seção em "Minha Conta → Meu Espaço
→ Horário de funcionamento", onde você configura, por dia da semana:
- Se o estabelecimento abre naquele dia (aberto/fechado)
- Horário de abertura e fechamento
- Duração de cada horário oferecido (ex.: 30, 40 ou 60 minutos)

Isso passou a valer automaticamente:
- Na página pública de agendamento (o problema principal que você reportou)
  — inclusive respeitando o fim do expediente ao calcular se um serviço
  mais longo ainda cabe antes de fechar.
- No formulário interno de criar agendamento manual — a lista de horários
  se atualiza sozinha quando você muda a data.
- Nos cálculos de capacidade/ocupação da agenda e do dashboard.

**Compatibilidade:** nenhuma empresa que ainda não configurar nada é
afetada — o padrão continua sendo 09h às 18h todo dia, exatamente como
funcionava antes.

Testado: configurei um cenário real (segunda a sexta até 20h, sábado até
14h, domingo fechado) e confirmei que a página pública passou a oferecer
exatamente esses horários — inclusive bloqueando agendamento no domingo — e
que o formulário interno de novo agendamento reflete o mesmo horário.

## 10. Correção de bug: erro 500 no login em banco recém-migrado

Você reportou um erro 500 ao tentar logar depois de reinstalar numa
máquina nova. O erro era `IndexError: No item with that key` na proteção
de bloqueio por tentativas de login (item 8 desta lista) — ela tentava ler
colunas novas (`bloqueado_ate`, `tentativas_falhas`) antes da migração
automática do banco ter tido chance de aplicá-las por completo.

Corrigido em duas camadas:
- Toda leitura dessas colunas agora usa um acesso seguro que nunca quebra
  a página, mesmo que a coluna ainda não exista naquele momento.
- Toda gravação (registrar/limpar tentativas de login) agora tolera um
  banco ainda não migrado, sem derrubar o login — a proteção contra força
  bruta volta a valer normalmente assim que a migração for concluída (o que
  já acontece sozinho, automaticamente, no próximo início do sistema).

De brinde, encontrei e corrigi o mesmo tipo de erro em outra função nova
(`valor_linha`) que também não estava acessível corretamente entre os
arquivos — mesma causa raiz, mesma correção.

Testado simulando exatamente o pior cenário possível (tabela `usuarios`
sem nenhuma das colunas novas, requisição de login chegando antes da
migração aplicar): o login funciona normalmente, sem erro 500.

---

## O que revisar antes de lançar

1. **Configurar `.env` de produção** com base no `.env.example` atualizado —
   especialmente `DATABASE_URL` (recomendado usar PostgreSQL na VPS),
   `BYTECH_SECRET_KEY` (troque o valor padrão de desenvolvimento),
   `BYTECH_PUBLIC_URL` e as credenciais da Evolution API.
2. **Migrar os dados atuais para o PostgreSQL** com
   `scripts/database/migrar_sqlite_para_postgresql.py` (veja a seção 6
   acima) depois de configurar o banco na VPS da Hostinger.
3. **Conectar o WhatsApp** no painel de Comunicação (gerar QR code) para que
   os envios realmente saiam — isso não foi alterado nesta correção, apenas
   o dispatcher automático de mensagens.
4. Todas as correções foram testadas localmente (SQLite) com requisições
   reais simuladas, incluindo o fluxo completo de webhook do WhatsApp, o
   ciclo do worker de mensagens e os fluxos de login/troca de senha.
   Recomendo um teste manual final no seu ambiente antes do lançamento.
