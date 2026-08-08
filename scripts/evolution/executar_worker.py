"""Inicia o worker de confirmações e lembretes do WhatsApp."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database import init_db  # noqa: E402
from services.scheduler_service import executar_worker  # noqa: E402


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    init_db()
    executar_worker()
