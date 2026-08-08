"""Verifica construções SQL conhecidas como incompatíveis com PostgreSQL."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IGNORADOS = {
    ROOT / "scripts" / "database" / "migrar_sqlite_para_postgresql.py",
    ROOT / "scripts" / "maintenance" / "diagnostico.py",
    ROOT / "scripts" / "maintenance" / "verificar_release.py",
}
PADROES = {
    "IFNULL": re.compile(r"\bIFNULL\s*\(", re.I),
    "julianday": re.compile(r"\bjulianday\s*\(", re.I),
    "DATE('now')": re.compile(r"\bdate\s*\(\s*['\"]now['\"]", re.I),
    "datetime('now')": re.compile(r"\bdatetime\s*\(\s*['\"]now['\"]", re.I),
    "last_insert_rowid": re.compile(r"\blast_insert_rowid\s*\(", re.I),
    "INSERT OR REPLACE": re.compile(r"\bINSERT\s+OR\s+REPLACE\b", re.I),
    "LIMIT ?, ?": re.compile(r"\bLIMIT\s+\?\s*,\s*\?", re.I),
    "COALESCE texto/timestamp": re.compile(r"COALESCE\s*\([^,]+,\s*CURRENT_TIMESTAMP\s*\)", re.I),
}

problemas: list[str] = []
for arquivo in ROOT.rglob("*.py"):
    if arquivo in IGNORADOS or arquivo == Path(__file__).resolve() or any(p in {".git", "__pycache__"} for p in arquivo.parts):
        continue
    texto = arquivo.read_text(encoding="utf-8", errors="replace")
    for numero, linha in enumerate(texto.splitlines(), 1):
        for nome, padrao in PADROES.items():
            if padrao.search(linha):
                problemas.append(f"{arquivo.relative_to(ROOT)}:{numero}: {nome}: {linha.strip()}")

if problemas:
    print("Incompatibilidades SQL encontradas:")
    print("\n".join(problemas))
    raise SystemExit(1)

print("Verificação SQL concluída: nenhuma incompatibilidade crítica conhecida encontrada.")
