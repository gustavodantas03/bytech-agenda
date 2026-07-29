# Bytech Agenda — RC1.1.0 Design System

Esta entrega inicia a padronização visual real do sistema sem alterar regras de negócio.

## Implementado

- Nova camada global `static/css/design-system.css`.
- Padrão único para cabeçalhos, painéis, botões, campos, tabelas, alertas, indicadores, abas e badges.
- Compatibilidade visual aplicada às telas existentes sem exigir reescrita imediata.
- Correções específicas para Inteligência CRM e Comunicação/WhatsApp.
- Componentes Jinja reutilizáveis em `templates/admin/components/ui.html`.
- Versão visível atualizada para `RC1.1.0`.
- Cache dos estilos atualizado.

## Validação visual

1. Extraia em uma pasta nova.
2. Inicie o sistema.
3. Confirme `RC1.1.0` no rodapé do menu lateral.
4. No navegador, pressione `Ctrl + F5`.
5. Revise Dashboard, Agenda, CRM → Inteligência CRM e Comunicação → WhatsApp.

## Observação

Esta é a fundação do design system. As próximas entregas podem migrar cada template para os macros reutilizáveis sem quebrar as páginas atuais.
