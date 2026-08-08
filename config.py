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
    # URL pública onde o sistema está publicado (sem barra no final).
    # Usada para montar links de agendamento enviados por WhatsApp.
    PUBLIC_URL = os.getenv("BYTECH_PUBLIC_URL", "").strip().rstrip("/")

    # --- Segurança do cookie de sessão ---
    # HTTPONLY: o cookie nunca fica acessível via JavaScript (protege contra XSS).
    SESSION_COOKIE_HTTPONLY = True
    # SAMESITE=Lax: o navegador não envia o cookie em requisições disparadas
    # por outros sites, o que já bloqueia a maior parte dos ataques CSRF.
    SESSION_COOKIE_SAMESITE = "Lax"
    # SECURE: o cookie só é enviado por HTTPS. Fica desligado por padrão para
    # não travar o login em desenvolvimento local (http://127.0.0.1). Na VPS,
    # depois que o domínio e o HTTPS estiverem funcionando, defina
    # BYTECH_FORCE_HTTPS=1 no .env para ativar.
    SESSION_COOKIE_SECURE = os.getenv("BYTECH_FORCE_HTTPS", "0") == "1"
