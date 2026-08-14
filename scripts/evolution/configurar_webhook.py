"""Configura na Evolution o webhook da instância vinculada à empresa."""
import json
import os
import sys
from pathlib import Path
from urllib import request, error

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database import get_connection, init_db
from services.evolution_api import obter_configuracao_global, garantir_configuracao_empresa


def main():
    if len(sys.argv) < 3:
        print("Uso: py scripts/evolution/configurar_webhook.py <empresa_id> <url_publica>")
        print("Exemplo: py scripts/evolution/configurar_webhook.py 1 https://dominio.com")
        raise SystemExit(2)

    empresa_id = int(sys.argv[1])
    publica = sys.argv[2].rstrip("/")

    desenvolvimento = (
        publica.startswith("http://host.docker.internal")
        or publica.startswith("http://127.0.0.1")
        or publica.startswith("http://localhost")
    )

    if not desenvolvimento and not publica.startswith("https://"):
        raise SystemExit("A URL pública do webhook deve começar com https://")

    init_db()
    conn = get_connection()
    try:
        empresa = conn.execute("SELECT id FROM empresas WHERE id=?", (empresa_id,)).fetchone()
        if not empresa:
            raise SystemExit(f"Empresa {empresa_id} não encontrada.")
        garantir_configuracao_empresa(conn, empresa_id)
        conn.commit()
        config = conn.execute(
            "SELECT * FROM whatsapp_configuracoes WHERE empresa_id=?", (empresa_id,)
        ).fetchone()
    finally:
        conn.close()

    if not config:
        raise SystemExit("Não foi possível criar a configuração WhatsApp da empresa.")

    base, key, _ = obter_configuracao_global()
    token = os.getenv("EVOLUTION_WEBHOOK_TOKEN", "").strip()
    url = f"{publica}/api/webhooks/evolution/{config['instance_name']}"
    if token:
        url += f"?token={token}"

    payload = {
        "webhook": {
            "enabled": True,
            "url": url,
            "webhookByEvents": False,
            "webhookBase64": False,
            "events": ["MESSAGES_UPSERT"],
        }
    }

    req = request.Request(
        f"{base}/webhook/set/{config['instance_name']}",
        data=json.dumps(payload).encode(),
        headers={"apikey": key, "Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=20) as resp:
            print(resp.read().decode())
    except error.HTTPError as exc:
        print(exc.read().decode())
        raise

    print("Webhook configurado:", url)


if __name__ == "__main__":
    main()
