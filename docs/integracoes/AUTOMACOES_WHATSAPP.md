# Motor de automações do WhatsApp

O servidor Flask e o worker devem funcionar em processos separados.

## Desenvolvimento no Windows

Terminal 1:

```powershell
$env:DATABASE_URL="postgresql://bytech:bytech123@127.0.0.1:5432/bytech_agenda"
$env:EVOLUTION_BASE_URL="http://127.0.0.1:8080"
$env:EVOLUTION_API_KEY="bytech_evolution_local_2026"
py app.py
```

Terminal 2, com as mesmas variáveis:

```powershell
py scripts/evolution/executar_worker.py
```

Também é possível executar `scripts/windows/INICIAR-WORKER-WHATSAPP.bat` depois de definir as variáveis no ambiente do Windows.

## Teste de um ciclo

```powershell
py scripts/evolution/processar_uma_vez.py
```

O ciclo realiza duas operações:

1. cria os lembretes que entram nas janelas de 24 horas e 2 horas;
2. processa as mensagens pendentes, respeitando o limite de tentativas.

Variáveis opcionais:

- `BYTECH_WORKER_INTERVAL`: intervalo entre ciclos, em segundos; mínimo de 15 e padrão de 60;
- `BYTECH_WORKER_BATCH`: quantidade máxima de mensagens por ciclo; padrão de 30.

Em produção, execute apenas uma instância do worker para cada banco de dados.
