"""Checklist técnico executável antes de publicar o Bytech Agenda."""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = ROOT / "database" / "bytech_agenda.db"
FAIL = 0


def check(ok: bool, label: str, detail: str = "") -> None:
    global FAIL
    status = "OK" if ok else "FALHA"
    print(f"[{status}] {label}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAIL += 1


print("=== Bytech Agenda · Release Candidate ===")
check(sys.version_info >= (3, 11), "Python 3.11 ou superior", sys.version.split()[0])
check(DB.exists(), "Banco principal encontrado", str(DB))
check(os.getenv("BYTECH_SECRET_KEY", "") not in ("", "bytech-dev-altere-em-producao"),
      "BYTECH_SECRET_KEY segura", "defina uma chave forte na VPS")
check(os.getenv("BYTECH_DEBUG", "0") != "1", "Modo debug desativado")

for rel in [
    "app.py", "core.py", "database.py", "templates/admin/base.html",
    "templates/admin/whatsapp.html", "static/css/whatsapp.css",
    "static/js/whatsapp.js", "processar_comunicacao.py",
]:
    check((ROOT / rel).exists(), f"Arquivo obrigatório: {rel}")

if DB.exists():
    try:
        conn = sqlite3.connect(DB)
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        check(integrity == "ok", "Integridade do SQLite", integrity)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {
            "empresas", "usuarios", "clientes", "agendamentos", "servicos",
            "funcionarios", "whatsapp_configuracoes", "whatsapp_modelos",
            "whatsapp_automacoes", "whatsapp_historico", "whatsapp_fila",
        }
        missing = sorted(required - tables)
        check(not missing, "Tabelas essenciais", ", ".join(missing) if missing else "completas")
        conn.close()
    except Exception as exc:
        check(False, "Leitura do banco", str(exc))

try:
    import flask  # noqa: F401
    import werkzeug  # noqa: F401
    check(True, "Dependências Flask/Werkzeug")
except Exception:
    check(False, "Dependências Flask/Werkzeug", "execute: py -m pip install -r requirements.txt")

print("\nResultado:", "APROVADO" if FAIL == 0 else f"{FAIL} pendência(s)")
raise SystemExit(1 if FAIL else 0)
