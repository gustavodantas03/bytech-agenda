# Evolution API no Bytech Agenda

A infraestrutura da Evolution é global e controlada pela Bytech. Cada empresa guarda somente o nome interno da própria instância.

## Desenvolvimento local

1. Inicie a Evolution:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/evolution/iniciar_evolution.ps1
```

2. Inicie o Bytech Agenda já com as variáveis globais carregadas:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/evolution/iniciar_bytech_com_evolution.ps1
```

3. No painel da empresa, abra **Comunicação → WhatsApp** e clique em **Conectar WhatsApp**.

## Instância já conectada

Para aproveitar a instância local `bytech-agenda`, vincule-a à empresa desejada:

```powershell
py scripts/evolution/vincular_instancia_existente.py --empresa-id 1 --instancia bytech-agenda
```

Troque o ID conforme a empresa usada no teste. Depois reinicie o Bytech Agenda e atualize o status na tela do WhatsApp.

## Variáveis de produção

```env
EVOLUTION_BASE_URL=https://evolution.seudominio.com.br
EVOLUTION_API_KEY=uma-chave-longa-e-segura
EVOLUTION_TIMEOUT=15
```

Essas credenciais não são exibidas ao cliente.
