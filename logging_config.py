"""Configuração central de logs do Bytech Agenda."""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configurar_logs() -> None:
    nivel = getattr(logging, os.getenv("BYTECH_LOG_LEVEL", "INFO").upper(), logging.INFO)
    log_dir = Path(os.getenv("BYTECH_LOG_DIR", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    formato = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    root = logging.getLogger()
    root.setLevel(nivel)
    if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        arquivo = RotatingFileHandler(
            log_dir / "bytech_agenda.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        arquivo.setFormatter(formato)
        root.addHandler(arquivo)
    if not any(type(h) is logging.StreamHandler for h in root.handlers):
        console = logging.StreamHandler()
        console.setFormatter(formato)
        root.addHandler(console)
