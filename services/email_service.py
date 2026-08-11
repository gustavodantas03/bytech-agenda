"""Envio simples de e-mail via SMTP (usado para notificar novos leads)."""
from __future__ import annotations

import os
import smtplib
from email.mime.text import MIMEText


def enviar_email_lead(assunto: str, corpo: str) -> bool:
    host = os.getenv("BYTECH_SMTP_HOST", "").strip()
    porta = int(os.getenv("BYTECH_SMTP_PORT", "465") or 465)
    usuario = os.getenv("BYTECH_SMTP_USER", "").strip()
    senha = os.getenv("BYTECH_SMTP_PASSWORD", "").strip()
    destino = os.getenv("BYTECH_SMTP_TO", "").strip()

    if not (host and usuario and senha and destino):
        return False

    msg = MIMEText(corpo, "plain", "utf-8")
    msg["Subject"] = assunto
    msg["From"] = usuario
    msg["To"] = destino

    try:
        with smtplib.SMTP_SSL(host, porta, timeout=15) as servidor:
            servidor.login(usuario, senha)
            servidor.sendmail(usuario, [destino], msg.as_string())
        return True
    except Exception:
        return False
