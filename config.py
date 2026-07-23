"""Configurações centrais do Bytech Agenda."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

class Config:
    SECRET_KEY = os.getenv("BYTECH_SECRET_KEY", "bytech-dev-altere-em-producao")
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024
    UPLOAD_FOLDER = str(BASE_DIR / "static" / "uploads" / "logos")
