# Evolution Webhook — RC2.6

O endpoint é `POST /api/webhooks/evolution/<instance_name>`.

Para ambiente local, exponha a porta 5000 com um túnel HTTPS. Depois execute:

```powershell
$env:EVOLUTION_WEBHOOK_TOKEN="um-token-seguro"
py scripts/evolution/configurar_webhook.py 1 https://SEU-ENDERECO-PUBLICO
```

A mesma variável `EVOLUTION_WEBHOOK_TOKEN` deve estar definida no processo do Flask.

Fluxos aceitos:
- `1`: confirma o agendamento.
- `2`: solicita nova data e, depois, um horário livre.
- `3`: cancela e libera o horário.

O webhook ignora mensagens enviadas pela própria instância e mensagens de grupos. Eventos repetidos são descartados pelo ID da mensagem.
