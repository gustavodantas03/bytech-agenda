"""Webhooks públicos de integrações externas."""
import hmac
import os
from flask import jsonify, request

from core import app
from services.conversation_service import processar_webhook


@app.route("/api/webhooks/evolution/<instance_name>", methods=["POST"])
def webhook_evolution(instance_name):
    token_configurado=os.getenv("EVOLUTION_WEBHOOK_TOKEN","").strip()
    token_recebido=(request.args.get("token") or request.headers.get("X-Webhook-Token") or "").strip()
    if token_configurado and not hmac.compare_digest(token_configurado,token_recebido):
        return jsonify({"erro":"Token inválido."}),401
    payload=request.get_json(silent=True) or {}
    resultado=processar_webhook(payload,instance_name)
    status=int(resultado.pop("status",200))
    return jsonify(resultado),status
