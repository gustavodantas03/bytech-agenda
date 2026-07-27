"""Rotas do módulo agenda."""

from datetime import date, datetime, timedelta

from flask import jsonify

from core import *  # noqa: F401,F403


STATUS_PERMITIDOS = {
    "agendado",
    "confirmado",
    "em_atendimento",
    "finalizado",
    "cancelado",
    "faltou",
}


def _consultar_resumo_agenda(conn, empresa_id, data_filtro, funcionario_id=None):
    """Calcula os indicadores da agenda respeitando a empresa e o filtro."""
    sql = """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN status = 'agendado' THEN 1 ELSE 0 END) AS agendados,
            SUM(CASE WHEN status = 'confirmado' THEN 1 ELSE 0 END) AS confirmados,
            SUM(CASE WHEN status = 'em_atendimento' THEN 1 ELSE 0 END) AS em_atendimento,
            SUM(CASE WHEN status = 'finalizado' THEN 1 ELSE 0 END) AS finalizados,
            SUM(CASE WHEN status = 'cancelado' THEN 1 ELSE 0 END) AS cancelados,
            SUM(CASE WHEN status = 'faltou' THEN 1 ELSE 0 END) AS faltaram,
            COALESCE(
                SUM(
                    CASE
                        WHEN status NOT IN ('cancelado', 'faltou')
                        THEN COALESCE(valor_total, 0)
                        ELSE 0
                    END
                ),
                0
            ) AS previsao
        FROM agendamentos
        WHERE empresa_id = ?
          AND data = ?
    """
    params = [empresa_id, data_filtro]

    if funcionario_id:
        sql += " AND funcionario_id = ?"
        params.append(funcionario_id)

    linha = conn.execute(sql, params).fetchone()

    return {
        "total": int(linha["total"] or 0),
        "agendados": int(linha["agendados"] or 0),
        "confirmados": int(linha["confirmados"] or 0),
        "em_atendimento": int(linha["em_atendimento"] or 0),
        "finalizados": int(linha["finalizados"] or 0),
        "cancelados": int(linha["cancelados"] or 0),
        "faltaram": int(linha["faltaram"] or 0),
        "previsao": float(linha["previsao"] or 0),
    }


@app.route("/admin/agenda")
@login_required
def admin_agenda():
    empresa_id = session["empresa_id"]
    data_filtro = request.args.get("data", date.today().isoformat())
    funcionario_id = request.args.get("funcionario_id", type=int)

    try:
        data_selecionada = date.fromisoformat(data_filtro)
    except ValueError:
        data_selecionada = date.today()
        data_filtro = data_selecionada.isoformat()

    conn = get_connection()

    funcionarios = conn.execute(
        """
        SELECT *
        FROM funcionarios
        WHERE empresa_id = ?
          AND ativo = 1
        ORDER BY nome
        """,
        (empresa_id,),
    ).fetchall()

    sql = """
        SELECT
            a.*,
            COALESCE(
                (
                    SELECT GROUP_CONCAT(s2.nome, ' + ')
                    FROM agendamento_servicos ags
                    JOIN servicos s2 ON s2.id = ags.servico_id
                    WHERE ags.agendamento_id = a.id
                ),
                s.nome
            ) AS servico_nome,
            f.nome AS funcionario_nome
        FROM agendamentos a
        JOIN servicos s ON s.id = a.servico_id
        LEFT JOIN funcionarios f ON f.id = a.funcionario_id
        WHERE a.empresa_id = ?
          AND a.data = ?
    """
    params = [empresa_id, data_filtro]

    if funcionario_id:
        sql += " AND a.funcionario_id = ?"
        params.append(funcionario_id)

    sql += " ORDER BY a.hora, f.nome, a.cliente_nome"

    agendamentos = conn.execute(sql, params).fetchall()
    resumo = _consultar_resumo_agenda(
        conn,
        empresa_id,
        data_filtro,
        funcionario_id,
    )

    # Capacidade diária baseada nos horários padrão atualmente oferecidos
    # pelo sistema (09:00 às 18:00, intervalos de 40 minutos).
    total_slots_por_profissional = len(gerar_horarios())
    profissionais_considerados = 1 if funcionario_id else max(len(funcionarios), 1)
    capacidade_total = total_slots_por_profissional * profissionais_considerados
    ocupados_validos = sum(
        1 for item in agendamentos
        if item["status"] not in ("cancelado", "faltou")
    )
    horarios_livres = max(capacidade_total - ocupados_validos, 0)
    taxa_ocupacao = round((ocupados_validos / capacidade_total) * 100) if capacidade_total else 0

    resumo["capacidade_total"] = capacidade_total
    resumo["horarios_livres"] = horarios_livres
    resumo["taxa_ocupacao"] = taxa_ocupacao

    ocupacao_profissionais = []
    for profissional in funcionarios:
        itens_profissional = [
            item for item in agendamentos
            if item["funcionario_id"] == profissional["id"]
            and item["status"] not in ("cancelado", "faltou")
        ]
        ocupados = len(itens_profissional)
        percentual = round((ocupados / total_slots_por_profissional) * 100) if total_slots_por_profissional else 0
        ocupacao_profissionais.append({
            "id": profissional["id"],
            "nome": profissional["nome"],
            "ocupados": ocupados,
            "livres": max(total_slots_por_profissional - ocupados, 0),
            "percentual": min(percentual, 100),
        })

    agora_hora = datetime.now().strftime("%H:%M") if data_selecionada == date.today() else "00:00"
    proximos = [
        item for item in agendamentos
        if item["status"] not in ("finalizado", "cancelado", "faltou")
        and item["hora"] >= agora_hora
    ][:4]

    conn.close()

    hoje = date.today()
    nomes_dias = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
    nomes_meses = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
    data_extenso = f"{nomes_dias[data_selecionada.weekday()]}, {data_selecionada.day} de {nomes_meses[data_selecionada.month - 1]}"

    return render_template(
        "admin/agenda.html",
        agendamentos=agendamentos,
        funcionarios=funcionarios,
        data_filtro=data_filtro,
        funcionario_id=funcionario_id,
        resumo=resumo,
        data_anterior=(data_selecionada - timedelta(days=1)).isoformat(),
        data_seguinte=(data_selecionada + timedelta(days=1)).isoformat(),
        data_hoje=hoje.isoformat(),
        data_amanha=(hoje + timedelta(days=1)).isoformat(),
        data_extenso=data_extenso,
        ocupacao_profissionais=ocupacao_profissionais,
        proximos=proximos,
    )


@app.route(
    "/admin/agendamentos/<int:agendamento_id>/status",
    methods=["POST"],
)
@login_required
def atualizar_status_agendamento(agendamento_id):
    empresa_id = session["empresa_id"]

    dados = request.get_json(silent=True) or request.form
    novo_status = str(dados.get("status", "")).strip().lower()
    funcionario_id = dados.get("funcionario_id")

    try:
        funcionario_id = int(funcionario_id) if funcionario_id else None
    except (TypeError, ValueError):
        funcionario_id = None

    if novo_status not in STATUS_PERMITIDOS:
        return jsonify(
            sucesso=False,
            mensagem="Status inválido.",
        ), 400

    conn = get_connection()

    agendamento = conn.execute(
        """
        SELECT id, data
        FROM agendamentos
        WHERE id = ?
          AND empresa_id = ?
        """,
        (agendamento_id, empresa_id),
    ).fetchone()

    if not agendamento:
        conn.close()
        return jsonify(
            sucesso=False,
            mensagem="Agendamento não encontrado.",
        ), 404

    conn.execute(
        """
        UPDATE agendamentos
        SET status = ?
        WHERE id = ?
          AND empresa_id = ?
        """,
        (novo_status, agendamento_id, empresa_id),
    )
    conn.commit()

    resumo = _consultar_resumo_agenda(
        conn,
        empresa_id,
        agendamento["data"],
        funcionario_id,
    )

    total_profissionais = 1 if funcionario_id else conn.execute(
        "SELECT COUNT(*) AS total FROM funcionarios WHERE empresa_id = ? AND ativo = 1",
        (empresa_id,),
    ).fetchone()["total"] or 1
    capacidade_total = len(gerar_horarios()) * total_profissionais
    ocupados_validos = resumo["total"] - resumo["cancelados"] - resumo["faltaram"]
    resumo["capacidade_total"] = capacidade_total
    resumo["horarios_livres"] = max(capacidade_total - ocupados_validos, 0)
    resumo["taxa_ocupacao"] = round((ocupados_validos / capacidade_total) * 100) if capacidade_total else 0
    conn.close()

    return jsonify(
        sucesso=True,
        mensagem="Status atualizado com sucesso.",
        status=novo_status,
        resumo=resumo,
    )



@app.route("/admin/clientes/<int:cliente_id>/resumo", methods=["GET"])
@login_required
@recurso_required("crm")
def resumo_cliente_agenda(cliente_id):
    """Retorna o resumo CRM do cliente para o painel lateral da agenda."""
    empresa_id = session["empresa_id"]
    conn = get_connection()

    cliente = conn.execute(
        """
        SELECT *
        FROM clientes
        WHERE id = ?
          AND empresa_id = ?
        """,
        (cliente_id, empresa_id),
    ).fetchone()

    if not cliente:
        conn.close()
        return jsonify(
            sucesso=False,
            mensagem="Cliente não encontrado.",
        ), 404

    estatisticas = conn.execute(
        """
        SELECT
            COUNT(CASE WHEN status IN ('finalizado', 'concluido') THEN 1 END)
                AS total_visitas,
            COALESCE(
                SUM(
                    CASE
                        WHEN status IN ('finalizado', 'concluido')
                        THEN valor_total
                        ELSE 0
                    END
                ),
                0
            ) AS total_gasto,
            MAX(
                CASE
                    WHEN status IN ('finalizado', 'concluido')
                    THEN data
                END
            ) AS ultima_visita
        FROM agendamentos
        WHERE empresa_id = ?
          AND cliente_id = ?
        """,
        (empresa_id, cliente_id),
    ).fetchone()

    servico_favorito = conn.execute(
        """
        SELECT s.nome, COUNT(*) AS quantidade
        FROM agendamentos a
        JOIN servicos s ON s.id = a.servico_id
        WHERE a.empresa_id = ?
          AND a.cliente_id = ?
          AND a.status IN ('finalizado', 'concluido')
        GROUP BY s.id, s.nome
        ORDER BY quantidade DESC, s.nome COLLATE NOCASE
        LIMIT 1
        """,
        (empresa_id, cliente_id),
    ).fetchone()

    profissional_favorito = conn.execute(
        """
        SELECT f.nome, COUNT(*) AS quantidade
        FROM agendamentos a
        JOIN funcionarios f ON f.id = a.funcionario_id
        WHERE a.empresa_id = ?
          AND a.cliente_id = ?
          AND a.status IN ('finalizado', 'concluido')
        GROUP BY f.id, f.nome
        ORDER BY quantidade DESC, f.nome COLLATE NOCASE
        LIMIT 1
        """,
        (empresa_id, cliente_id),
    ).fetchone()

    historico = conn.execute(
        """
        SELECT
            a.id,
            a.data,
            a.hora,
            a.status,
            a.valor_total,
            a.duracao_total,
            COALESCE(
                (
                    SELECT GROUP_CONCAT(s2.nome, ' + ')
                    FROM agendamento_servicos ags
                    JOIN servicos s2 ON s2.id = ags.servico_id
                    WHERE ags.agendamento_id = a.id
                ),
                s.nome
            ) AS servico_nome,
            f.nome AS funcionario_nome
        FROM agendamentos a
        JOIN servicos s ON s.id = a.servico_id
        LEFT JOIN funcionarios f ON f.id = a.funcionario_id
        WHERE a.empresa_id = ?
          AND a.cliente_id = ?
        ORDER BY a.data DESC, a.hora DESC
        LIMIT 8
        """,
        (empresa_id, cliente_id),
    ).fetchall()

    conn.close()

    total_visitas = int(estatisticas["total_visitas"] or 0)
    total_gasto = float(estatisticas["total_gasto"] or 0)
    ticket_medio = total_gasto / total_visitas if total_visitas else 0

    return jsonify(
        sucesso=True,
        cliente={
            "id": cliente["id"],
            "nome": cliente["nome"],
            "telefone": cliente["telefone"],
            "email": cliente["email"],
            "data_nascimento": cliente["data_nascimento"],
            "instagram": cliente["instagram"],
            "observacoes": cliente["observacoes"],
            "pontos_fidelidade": int(cliente["pontos_fidelidade"] or 0),
            "recompensas_disponiveis": int(
                cliente["recompensas_disponiveis"] or 0
            ),
            "criado_em": cliente["criado_em"],
            "total_visitas": total_visitas,
            "total_gasto": total_gasto,
            "ticket_medio": ticket_medio,
            "ultima_visita": estatisticas["ultima_visita"],
            "servico_favorito": (
                servico_favorito["nome"] if servico_favorito else None
            ),
            "profissional_favorito": (
                profissional_favorito["nome"]
                if profissional_favorito
                else None
            ),
        },
        historico=[dict(item) for item in historico],
    )


@app.route("/admin/agendamentos/<int:agendamento_id>/cliente-resumo", methods=["GET"])
@login_required
@recurso_required("crm")
def resumo_cliente_por_agendamento(agendamento_id):
    """Resolve o cliente pelo agendamento e devolve o mesmo resumo do CRM."""
    empresa_id = session["empresa_id"]
    conn = get_connection()

    agendamento = conn.execute(
        """
        SELECT id, cliente_id, cliente_nome, cliente_telefone
        FROM agendamentos
        WHERE id = ?
          AND empresa_id = ?
        """,
        (agendamento_id, empresa_id),
    ).fetchone()

    if not agendamento:
        conn.close()
        return jsonify(sucesso=False, mensagem="Agendamento não encontrado."), 404

    cliente_id = agendamento["cliente_id"]

    if not cliente_id:
        telefone = normalizar_telefone(agendamento["cliente_telefone"] or "")
        cliente = conn.execute(
            """
            SELECT id
            FROM clientes
            WHERE empresa_id = ?
              AND telefone = ?
            LIMIT 1
            """,
            (empresa_id, telefone),
        ).fetchone()

        if cliente:
            cliente_id = cliente["id"]
        else:
            cursor = conn.execute(
                """
                INSERT INTO clientes (empresa_id, nome, telefone)
                VALUES (?, ?, ?)
                """,
                (
                    empresa_id,
                    agendamento["cliente_nome"],
                    telefone or f"sem-telefone-{agendamento_id}",
                ),
            )
            cliente_id = cursor.lastrowid

        conn.execute(
            """
            UPDATE agendamentos
            SET cliente_id = ?
            WHERE id = ?
              AND empresa_id = ?
            """,
            (cliente_id, agendamento_id, empresa_id),
        )
        conn.commit()

    conn.close()
    return resumo_cliente_agenda(cliente_id)


@app.route("/admin/agendamentos/<int:agendamento_id>/cancelar", methods=["POST"])
@login_required
def cancelar_agendamento(agendamento_id):
    empresa_id = session["empresa_id"]
    conn = get_connection()
    conn.execute(
        """
        UPDATE agendamentos
        SET status = 'cancelado'
        WHERE id = ?
          AND empresa_id = ?
        """,
        (agendamento_id, empresa_id),
    )
    conn.commit()
    conn.close()
    return redirect(request.referrer or url_for("admin_agenda"))


@app.route("/admin/agendamentos/novo", methods=["GET", "POST"])
@login_required
def novo_agendamento():
    empresa_id = session["empresa_id"]

    conn = get_connection()

    servicos = conn.execute(
        """
        SELECT *
        FROM servicos
        WHERE empresa_id = ?
          AND ativo = 1
        ORDER BY nome
        """,
        (empresa_id,),
    ).fetchall()

    funcionarios = conn.execute(
        """
        SELECT *
        FROM funcionarios
        WHERE empresa_id = ?
          AND ativo = 1
        ORDER BY nome
        """,
        (empresa_id,),
    ).fetchall()

    if request.method == "POST":
        from services.recursos import limite_atingido
        limite_excedido, limite, _uso = limite_atingido(conn, empresa_id, "agendamentos")
        if limite_excedido:
            conn.close()
            flash(
                f"O limite mensal de {limite} agendamentos do plano foi atingido.",
                "erro",
            )
            return redirect(url_for("admin_agenda"))

        cliente_nome = request.form.get("cliente_nome", "").strip()
        cliente_telefone = normalizar_telefone(
            request.form.get("cliente_telefone", "")
        )
        servico_id = request.form.get("servico_id", type=int)
        funcionario_id = request.form.get("funcionario_id", type=int)
        data = request.form.get("data", "").strip()
        hora = request.form.get("hora", "").strip()

        if not all([
            cliente_nome,
            cliente_telefone,
            servico_id,
            funcionario_id,
            data,
            hora,
        ]):
            conn.close()
            flash("Preencha todos os campos.", "erro")
            return redirect(url_for("novo_agendamento"))

        servico = conn.execute(
            """
            SELECT id
            FROM servicos
            WHERE id = ?
              AND empresa_id = ?
              AND ativo = 1
            """,
            (servico_id, empresa_id),
        ).fetchone()

        funcionario = conn.execute(
            """
            SELECT id
            FROM funcionarios
            WHERE id = ?
              AND empresa_id = ?
              AND ativo = 1
            """,
            (funcionario_id, empresa_id),
        ).fetchone()

        if not servico or not funcionario:
            conn.close()
            flash("Serviço ou profissional inválido.", "erro")
            return redirect(url_for("novo_agendamento"))

        horario_ocupado = conn.execute(
            """
            SELECT id
            FROM agendamentos
            WHERE empresa_id = ?
              AND funcionario_id = ?
              AND data = ?
              AND hora = ?
              AND status != 'cancelado'
            LIMIT 1
            """,
            (empresa_id, funcionario_id, data, hora),
        ).fetchone()

        if horario_ocupado:
            conn.close()
            flash(
                "Este horário já está ocupado para esse profissional.",
                "erro",
            )
            return redirect(url_for("novo_agendamento"))

        try:
            servico_dados = conn.execute(
                """
                SELECT valor, duracao
                FROM servicos
                WHERE id = ?
                  AND empresa_id = ?
                """,
                (servico_id, empresa_id),
            ).fetchone()

            cliente = conn.execute(
                """
                SELECT id
                FROM clientes
                WHERE empresa_id = ?
                  AND telefone = ?
                """,
                (empresa_id, cliente_telefone),
            ).fetchone()

            if cliente:
                cliente_id = cliente["id"]
                conn.execute(
                    """
                    UPDATE clientes
                    SET nome = ?, atualizado_em = CURRENT_TIMESTAMP
                    WHERE id = ?
                      AND empresa_id = ?
                    """,
                    (cliente_nome, cliente_id, empresa_id),
                )
            else:
                cursor_cliente = conn.execute(
                    """
                    INSERT INTO clientes (
                        empresa_id,
                        nome,
                        telefone
                    )
                    VALUES (?, ?, ?)
                    """,
                    (empresa_id, cliente_nome, cliente_telefone),
                )
                cliente_id = cursor_cliente.lastrowid

            cursor = conn.execute(
                """
                INSERT INTO agendamentos (
                    empresa_id,
                    cliente_id,
                    cliente_nome,
                    cliente_telefone,
                    servico_id,
                    funcionario_id,
                    data,
                    hora,
                    status,
                    duracao_total,
                    valor_total
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    empresa_id,
                    cliente_id,
                    cliente_nome,
                    cliente_telefone,
                    servico_id,
                    funcionario_id,
                    data,
                    hora,
                    "agendado",
                    int(servico_dados["duracao"] or 40),
                    float(servico_dados["valor"] or 0),
                ),
            )

            conn.execute(
                """
                INSERT INTO agendamento_servicos (
                    agendamento_id,
                    servico_id
                )
                VALUES (?, ?)
                """,
                (cursor.lastrowid, servico_id),
            )

            agendamento_id = cursor.lastrowid
            enviar_confirmacao = request.form.get("enviar_confirmacao") == "1"
            conn.commit()
            conn.close()

            if enviar_confirmacao:
                try:
                    from services.evolution_api import enviar_mensagem_agendamento
                    resultado_whatsapp = enviar_mensagem_agendamento(empresa_id, agendamento_id, "confirmacao")
                    if not resultado_whatsapp.ok and resultado_whatsapp.error != "Automação desativada.":
                        flash("Agendamento salvo, mas a confirmação do WhatsApp não foi enviada. Consulte Comunicação → Histórico.", "alerta")
                except Exception:
                    flash("Agendamento salvo, mas ocorreu uma falha isolada no módulo WhatsApp.", "alerta")

            flash("Agendamento cadastrado com sucesso.", "sucesso")

            return redirect(
                url_for(
                    "admin_agenda",
                    data=data,
                    funcionario_id=funcionario_id,
                )
            )

        except sqlite3.IntegrityError:
            conn.close()
            flash("Este horário acabou de ser ocupado.", "erro")
            return redirect(url_for("novo_agendamento"))

    conn.close()

    return render_template(
        "admin/agendamento_novo.html",
        servicos=servicos,
        funcionarios=funcionarios,
        horarios=gerar_horarios(),
        data_hoje=date.today().isoformat(),
    )
