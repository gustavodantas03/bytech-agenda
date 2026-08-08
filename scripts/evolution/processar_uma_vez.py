"""Executa um único ciclo do motor de automações para diagnóstico."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database import init_db  # noqa: E402
from services.scheduler_service import executar_ciclo  # noqa: E402


if __name__ == "__main__":
    init_db()
    print(json.dumps(executar_ciclo(), ensure_ascii=False, indent=2))
