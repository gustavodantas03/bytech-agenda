"""Vincula uma instância Evolution já existente a uma empresa do Bytech Agenda."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from database import get_connection
from services.evolution_api import garantir_configuracao_empresa

parser = argparse.ArgumentParser()
parser.add_argument("--empresa-id", type=int, required=True)
parser.add_argument("--instancia", required=True)
args = parser.parse_args()
conn = get_connection()
garantir_configuracao_empresa(conn, args.empresa_id)
conn.execute("UPDATE whatsapp_configuracoes SET instance_name=?, atualizado_em=CURRENT_TIMESTAMP WHERE empresa_id=?", (args.instancia.strip(), args.empresa_id))
conn.commit(); conn.close()
print(f"Empresa {args.empresa_id} vinculada à instância {args.instancia}.")
