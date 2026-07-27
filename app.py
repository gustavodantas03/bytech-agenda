"""Ponto de entrada do Bytech Agenda."""

from core import app

# A importação registra as rotas no Flask.
from routes import auth  # noqa: F401
from routes import master  # noqa: F401
from routes import clientes  # noqa: F401
from routes import fidelidade  # noqa: F401
from routes import publico  # noqa: F401
from routes import conta  # noqa: F401
from routes import dashboard  # noqa: F401
from routes import servicos  # noqa: F401
from routes import funcionarios  # noqa: F401
from routes import agenda  # noqa: F401
from routes import relatorios  # noqa: F401
from routes import crm_inteligencia  # noqa: F401
from routes import whatsapp  # noqa: F401


if __name__ == "__main__":
    import os

    debug = os.getenv("BYTECH_DEBUG", "0") == "1"
    app.run(debug=debug)
