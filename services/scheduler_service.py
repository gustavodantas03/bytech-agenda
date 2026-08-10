"""Execução contínua das automações de WhatsApp do Bytech Agenda.

O worker roda separado do servidor Flask. Isso evita duplicidade ao usar Gunicorn
com múltiplos processos e mantém o agendamento público rápido mesmo quando a
Evolution API está temporariamente indisponível.
"""
from __future__ import annotations

import logging
import os
import signal
import time
from dataclasses import dataclass
from datetime import datetime

from services.communication_queue import gerar_lembretes, processar_fila

LOGGER = logging.getLogger("bytech.scheduler")


@dataclass(frozen=True)
class SchedulerConfig:
    intervalo_segundos: int = 60
    lote: int = 30

    @classmethod
    def from_env(cls) -> "SchedulerConfig":
        intervalo = max(15, int(os.getenv("BYTECH_WORKER_INTERVAL", "60")))
        lote = max(1, min(200, int(os.getenv("BYTECH_WORKER_BATCH", "30"))))
        return cls(intervalo_segundos=intervalo, lote=lote)


def executar_ciclo(config: SchedulerConfig | None = None) -> dict:
    """Gera lembretes pendentes e processa um lote da fila."""
    config = config or SchedulerConfig.from_env()
    lembretes = gerar_lembretes(datetime.now())
    fila = processar_fila(limite=config.lote, agora=datetime.now())
    return {"lembretes": lembretes, "fila": fila}


def executar_worker(config: SchedulerConfig | None = None) -> None:
    """Executa o worker até receber CTRL+C ou sinal de encerramento."""
    config = config or SchedulerConfig.from_env()
    encerrando = False

    def _encerrar(_signum, _frame):
        nonlocal encerrando
        encerrando = True

    signal.signal(signal.SIGINT, _encerrar)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _encerrar)

    LOGGER.info(
        "Worker iniciado: intervalo=%ss, lote=%s",
        config.intervalo_segundos,
        config.lote,
    )

    while not encerrando:
        inicio = time.monotonic()
        try:
            resultado = executar_ciclo(config)
            LOGGER.info("Ciclo concluído: %s", resultado)
        except Exception:
            LOGGER.exception("Falha no ciclo do worker; nova tentativa no próximo intervalo.")

        restante = config.intervalo_segundos - (time.monotonic() - inicio)
        while restante > 0 and not encerrando:
            pausa = min(1.0, restante)
            time.sleep(pausa)
            restante -= pausa

    LOGGER.info("Worker encerrado com segurança.")
