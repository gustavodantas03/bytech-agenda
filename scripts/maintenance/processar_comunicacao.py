"""Processador leve de lembretes e fila do Bytech Agenda.

Uso local/teste:
    python processar_comunicacao.py --once

Produção:
    python processar_comunicacao.py
"""
import argparse
import logging
import time

from database import init_db
from services.communication_queue import gerar_lembretes, processar_fila


def executar_ciclo():
    lembretes = gerar_lembretes()
    fila = processar_fila()
    logging.info("Lembretes=%s | Fila=%s", lembretes, fila)
    return {"lembretes": lembretes, "fila": fila}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Executa um único ciclo e encerra")
    parser.add_argument("--intervalo", type=int, default=60, help="Intervalo entre ciclos em segundos")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    init_db()
    while True:
        try:
            executar_ciclo()
        except Exception:
            logging.exception("Falha isolada no processador de comunicação")
        if args.once:
            break
        time.sleep(max(args.intervalo, 30))


if __name__ == "__main__":
    main()
