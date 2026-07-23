"""Diagnóstico de instalação do Bytech Agenda.

Executar com: py diagnostico.py
Retorna mensagens amigáveis para dependências, arquivos, banco e rotas.
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

DEPENDENCIAS = {
    "flask": "Flask",
    "werkzeug": "Werkzeug",
    "openpyxl": "openpyxl",
    "reportlab": "reportlab",
}

ARQUIVOS_OBRIGATORIOS = [
    "app.py",
    "core.py",
    "config.py",
    "database.py",
    "requirements.txt",
    "routes/relatorios.py",
    "static/js/agenda.js",
    "static/css/agenda-premium.css",
    "templates/admin/agenda.html",
    "templates/master/dashboard.html",
]


def falhar(mensagem: str) -> None:
    print(f"[ERRO] {mensagem}")
    raise SystemExit(1)


def verificar_dependencias() -> None:
    ausentes = [pacote for modulo, pacote in DEPENDENCIAS.items() if importlib.util.find_spec(modulo) is None]
    if ausentes:
        falhar(
            "Dependências ausentes: " + ", ".join(ausentes)
            + "\nExecute: py -m pip install -r requirements.txt"
        )
    print("[OK] Dependências Python instaladas.")


def verificar_arquivos() -> None:
    ausentes = [item for item in ARQUIVOS_OBRIGATORIOS if not (BASE_DIR / item).exists()]
    if ausentes:
        falhar("Arquivos obrigatórios ausentes: " + ", ".join(ausentes))
    print("[OK] Estrutura principal do projeto encontrada.")


def verificar_banco() -> None:
    from database import init_db, DB_PATH

    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        tabelas = {linha[0] for linha in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    obrigatorias = {"empresas", "usuarios", "clientes", "servicos", "funcionarios", "agendamentos"}
    faltando = sorted(obrigatorias - tabelas)
    if faltando:
        falhar("Tabelas ausentes no banco: " + ", ".join(faltando))
    print(f"[OK] Banco inicializado em: {DB_PATH}")


def verificar_flask() -> None:
    import app as app_module

    flask_app = app_module.app
    regras = list(flask_app.url_map.iter_rules())
    if not regras:
        falhar("Nenhuma rota Flask foi registrada.")

    with flask_app.test_client() as client:
        resposta = client.get("/static/js/agenda.js")
        if resposta.status_code != 200:
            falhar(f"Arquivo estático agenda.js retornou HTTP {resposta.status_code}.")

    print(f"[OK] Flask iniciou e registrou {len(regras)} rotas.")


def main() -> None:
    print("=== Diagnóstico Bytech Agenda ===")
    verificar_dependencias()
    verificar_arquivos()
    verificar_banco()
    verificar_flask()
    print("\nSistema validado. Você já pode executar: py app.py")


if __name__ == "__main__":
    try:
        main()
    except ImportError as exc:
        falhar(f"Falha ao importar módulo: {exc}")
    except Exception as exc:
        print(f"[ERRO] Falha inesperada: {exc}")
        raise
