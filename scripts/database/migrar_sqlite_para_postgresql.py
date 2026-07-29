"""Migra os dados do SQLite legado para PostgreSQL.

Uso:
  set DATABASE_URL=postgresql://bytech:senha@localhost:5432/bytech_agenda
  py scripts/database/migrar_sqlite_para_postgresql.py
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL.startswith(("postgresql://", "postgres://")):
    raise SystemExit("Defina DATABASE_URL apontando para o PostgreSQL antes de executar.")

try:
    import psycopg
    from psycopg import sql
except ImportError as exc:
    raise SystemExit("Instale as dependências: pip install -r requirements.txt") from exc

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database import init_db

SQLITE_PATH = Path(
    os.getenv("SQLITE_SOURCE", PROJECT_ROOT / "database" / "bytech_agenda.db")
)

if not SQLITE_PATH.exists():
    raise SystemExit(f"Banco SQLite não encontrado: {SQLITE_PATH}")

print("1/5 Criando/atualizando a estrutura PostgreSQL...")
init_db()

sqlite_conn = sqlite3.connect(SQLITE_PATH)
sqlite_conn.row_factory = sqlite3.Row
pg_conn = psycopg.connect(DATABASE_URL)

try:
    sqlite_tables = [
        row["name"] for row in sqlite_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    ]
    pg_tables = {
        row[0] for row in pg_conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'"
        ).fetchall()
    }
    tables = [name for name in sqlite_tables if name in pg_tables]

    print("2/5 Limpando dados iniciais do PostgreSQL...")
    if tables:
        pg_conn.execute(
            sql.SQL("TRUNCATE TABLE {} RESTART IDENTITY CASCADE").format(
                sql.SQL(", ").join(sql.Identifier(t) for t in tables)
            )
        )

    # Ordem que respeita as principais chaves estrangeiras.
    priority = [
        "empresas", "usuarios_master", "planos", "recursos", "configuracoes_financeiras",
        "usuarios", "plano_recursos", "clientes", "servicos", "funcionarios", "agendamentos",
        "agendamento_servicos", "fidelidade_configuracoes", "fidelidade_recompensas",
        "fidelidade_movimentos", "fidelidade_resgates", "cobrancas", "pagamentos",
        "logs_financeiros", "whatsapp_configuracoes", "whatsapp_automacoes", "whatsapp_modelos",
        "whatsapp_historico", "whatsapp_fila", "crm_configuracoes", "crm_campanhas",
    ]
    ordered = [t for t in priority if t in tables] + [t for t in tables if t not in priority]

    print("3/5 Copiando tabelas...")
    total = 0
    for table in ordered:
        sqlite_cols = [row[1] for row in sqlite_conn.execute(f'PRAGMA table_info("{table}")').fetchall()]
        pg_cols = {
            row[0] for row in pg_conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s",
                (table,),
            ).fetchall()
        }
        columns = [c for c in sqlite_cols if c in pg_cols]
        if not columns:
            continue
        rows = sqlite_conn.execute(
            f'SELECT {", ".join(chr(34)+c+chr(34) for c in columns)} FROM "{table}"'
        ).fetchall()
        if not rows:
            print(f"   {table}: 0")
            continue
        query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) ON CONFLICT DO NOTHING").format(
            sql.Identifier(table),
            sql.SQL(", ").join(sql.Identifier(c) for c in columns),
            sql.SQL(", ").join(sql.Placeholder() for _ in columns),
        )
        with pg_conn.cursor() as cursor:
            cursor.executemany(
                query,
                [tuple(row[c] for c in columns) for row in rows],
            )
        total += len(rows)
        print(f"   {table}: {len(rows)}")

    print("4/5 Ajustando sequências...")
    serials = pg_conn.execute("""
        SELECT table_name, column_name,
               pg_get_serial_sequence(format('%I.%I', table_schema, table_name), column_name)
          FROM information_schema.columns
         WHERE table_schema='public'
           AND column_default LIKE 'nextval(%'
    """).fetchall()
    for table, column, sequence in serials:
        if sequence:
            pg_conn.execute(
                sql.SQL("SELECT setval(%s, COALESCE((SELECT MAX({}) FROM {}), 1), true)").format(
                    sql.Identifier(column), sql.Identifier(table)
                ),
                (sequence,),
            )

    pg_conn.commit()
    print(f"5/5 Migração concluída: {total} registros copiados.")
except Exception:
    pg_conn.rollback()
    raise
finally:
    sqlite_conn.close()
    pg_conn.close()
