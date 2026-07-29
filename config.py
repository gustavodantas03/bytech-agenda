"""Configurações centrais do Bytech Agenda."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

class Config:
    APP_VERSION = os.getenv("BYTECH_APP_VERSION", "RC2.3.0-EVOLUTION")
    SECRET_KEY = os.getenv("BYTECH_SECRET_KEY", "bytech-dev-altere-em-producao")
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024
    UPLOAD_FOLDER = str(BASE_DIR / "static" / "uploads" / "logos")
    DATABASE_URL = os.getenv("DATABASE_URL", "")
