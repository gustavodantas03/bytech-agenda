# Bytech Agenda RC1.2.0 — UX e primeiros passos

## Entregue
- Checklist inteligente de configuração no Dashboard.
- Progresso automático com quatro etapas: empresa, profissionais, serviços e WhatsApp.
- Ações rápidas no Dashboard.
- Ocultação automática do checklist quando todas as etapas forem concluídas.
- Correção de um `elif` duplicado na rota do Dashboard que poderia impedir a inicialização.
- Novo CSS responsivo isolado em `static/css/dashboard-onboarding.css`.
- Versão atualizada para RC1.2.0.

## Como validar
1. Abra o Dashboard.
2. Confira o cartão “Primeiros passos”.
3. Cadastre os itens pendentes e volte ao Dashboard.
4. Confirme que o percentual aumenta e as etapas mudam para “Concluído”.
5. Após concluir as quatro etapas, o cartão deixa de ser exibido.
