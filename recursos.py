"""Regras centralizadas de planos, recursos e limites do SaaS."""

from datetime import date


def obter_plano_empresa(conn, empresa_id):
    return conn.execute(
        """
        SELECT p.*
        FROM empresas e
        LEFT JOIN planos p ON p.id = e.plano_id
        WHERE e.id = ?
        """,
        (empresa_id,),
    ).fetchone()


def obter_recursos_empresa(conn, empresa_id):
    linhas = conn.execute(
        """
        SELECT r.chave
        FROM empresas e
        JOIN plano_recursos pr ON pr.plano_id = e.plano_id
        JOIN recursos r ON r.id = pr.recurso_id
        WHERE e.id = ? AND r.ativo = 1
        ORDER BY r.chave
        """,
        (empresa_id,),
    ).fetchall()
    return {linha["chave"] for linha in linhas}


def empresa_tem_recurso(conn, empresa_id, recurso):
    return recurso in obter_recursos_empresa(conn, empresa_id)


def uso_do_plano(conn, empresa_id):
    plano = obter_plano_empresa(conn, empresa_id)
    inicio_mes = date.today().replace(day=1).isoformat()
    return {
        "plano": plano,
        "profissionais": conn.execute(
            "SELECT COUNT(*) total FROM funcionarios WHERE empresa_id = ? AND ativo = 1",
            (empresa_id,),
        ).fetchone()["total"],
        "usuarios": conn.execute(
            "SELECT COUNT(*) total FROM usuarios WHERE empresa_id = ?",
            (empresa_id,),
        ).fetchone()["total"],
        "agendamentos_mes": conn.execute(
            """
            SELECT COUNT(*) total FROM agendamentos
            WHERE empresa_id = ? AND data >= ? AND status != 'cancelado'
            """,
            (empresa_id, inicio_mes),
        ).fetchone()["total"],
    }


def limite_atingido(conn, empresa_id, tipo):
    uso = uso_do_plano(conn, empresa_id)
    plano = uso["plano"]
    if not plano:
        return False, None, uso

    mapa = {
        "profissionais": "limite_profissionais",
        "usuarios": "limite_usuarios",
        "agendamentos": "limite_agendamentos",
    }
    coluna = mapa.get(tipo)
    if not coluna:
        raise ValueError(f"Tipo de limite desconhecido: {tipo}")

    limite = plano[coluna]
    chave_uso = "agendamentos_mes" if tipo == "agendamentos" else tipo
    atingido = limite is not None and uso[chave_uso] >= limite
    return atingido, limite, uso
