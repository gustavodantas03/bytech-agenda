"""Rotas do módulo publico."""

from core import *  # noqa: F401,F403

@app.route("/")
def index():
    return redirect(url_for("landing", slug="demo"))


@app.route("/<slug>")
def landing(slug):
    conn = get_connection()
    empresa = conn.execute(
        "SELECT * FROM empresas WHERE slug = ? AND ativo = 1", (slug,)
    ).fetchone()

    if not empresa:
        conn.close()
        return "Empresa não encontrada.", 404

    servicos = conn.execute(
        "SELECT * FROM servicos WHERE empresa_id = ? AND ativo = 1 ORDER BY nome",
        (empresa["id"],),
    ).fetchall()
    conn.close()

    ui = obter_ui_segmento(
        empresa["segmento"] if "segmento" in empresa.keys() else "barbearia"
    )

    return render_template(
        "landing.html",
        empresa=empresa,
        servicos=servicos,
        ui=ui,
    )


@app.route("/<slug>/agendar")
def agendar(slug):
    conn = get_connection()
    empresa = conn.execute(
        "SELECT * FROM empresas WHERE slug = ? AND ativo = 1", (slug,)
    ).fetchone()

    if not empresa:
        conn.close()
        return "Empresa não encontrada.", 404

    servicos = conn.execute(
        "SELECT * FROM servicos WHERE empresa_id = ? AND ativo = 1 ORDER BY nome",
        (empresa["id"],),
    ).fetchall()

    funcionarios = conn.execute(
        "SELECT * FROM funcionarios WHERE empresa_id = ? AND ativo = 1 ORDER BY nome",
        (empresa["id"],),
    ).fetchall()
    conn.close()

    datas = []
    atual = date.today()
    while len(datas) < 7:
        if atual.weekday() != 6:
            datas.append({"valor": atual.isoformat(), "texto": atual.strftime("%d/%m/%Y")})
        atual += timedelta(days=1)

    return render_template(
        "agendar.html",
        empresa=empresa,
        servicos=servicos,
        funcionarios=funcionarios,
        datas=datas,
        ui=obter_ui_segmento(
            empresa["segmento"]
            if "segmento" in empresa.keys()
            else "barbearia"
        ),
    )


@app.route("/api/<slug>/horarios")
def horarios_disponiveis(slug):
    data = request.args.get("data")
    funcionario_id = request.args.get("funcionario_id", type=int)
    duracao_total = request.args.get("duracao_total", default=40, type=int)

    if not data or not funcionario_id:
        return jsonify({"erro": "Data ou profissional não informado."}), 400

    if duracao_total < 1 or duracao_total > 480:
        return jsonify({"erro": "Duração total inválida."}), 400

    try:
        data_obj = date.fromisoformat(data)
    except ValueError:
        return jsonify({"erro": "Data inválida."}), 400

    conn = get_connection()
    empresa = conn.execute(
        "SELECT * FROM empresas WHERE slug = ? AND ativo = 1", (slug,)
    ).fetchone()

    if not empresa:
        conn.close()
        return jsonify({"erro": "Empresa não encontrada."}), 404

    funcionario = conn.execute(
        "SELECT id FROM funcionarios WHERE id = ? AND empresa_id = ? AND ativo = 1",
        (funcionario_id, empresa["id"]),
    ).fetchone()

    if not funcionario:
        conn.close()
        return jsonify({"erro": "Profissional inválido."}), 400

    agendamentos_existentes = conn.execute(
        """
        SELECT hora, COALESCE(duracao_total, 40) AS duracao_total
        FROM agendamentos
        WHERE empresa_id = ?
          AND funcionario_id = ?
          AND data = ?
          AND status != 'cancelado'
        """,
        (empresa["id"], funcionario_id, data),
    ).fetchall()
    conn.close()

    horarios_do_dia = gerar_horarios_do_dia(empresa, data_obj)
    if not horarios_do_dia:
        # Empresa fechada nesse dia da semana (ou fora do horário configurado).
        return jsonify({"horarios": []})

    fechamento = datetime.strptime(
        obter_horarios_funcionamento(empresa)[str(data_obj.weekday())]["fechamento"],
        "%H:%M",
    )
    livres = []

    for hora in horarios_do_dia:
        inicio_candidato = datetime.strptime(hora, "%H:%M")
        fim_candidato = inicio_candidato + timedelta(minutes=duracao_total)

        if fim_candidato > fechamento:
            continue

        tem_conflito = False
        for existente in agendamentos_existentes:
            inicio_existente = datetime.strptime(existente["hora"], "%H:%M")
            fim_existente = inicio_existente + timedelta(
                minutes=existente["duracao_total"] or 40
            )

            if inicio_candidato < fim_existente and fim_candidato > inicio_existente:
                tem_conflito = True
                break

        if not tem_conflito:
            livres.append(hora)

    return jsonify({"horarios": livres})


@app.route("/api/<slug>/agendamentos", methods=["POST"])
def criar_agendamento(slug):
    dados = request.get_json() or {}
    servico_ids = dados.get("servico_ids") or []

    obrigatorios = [
        "cliente_nome",
        "cliente_telefone",
        "funcionario_id",
        "data",
        "hora",
    ]

    if any(not dados.get(campo) for campo in obrigatorios) or not servico_ids:
        return jsonify({"erro": "Preencha todos os campos e escolha ao menos um serviço."}), 400

    try:
        servico_ids = list(dict.fromkeys(int(item) for item in servico_ids))
    except (TypeError, ValueError):
        return jsonify({"erro": "Lista de serviços inválida."}), 400

    conn = get_connection()
    empresa = conn.execute(
        "SELECT * FROM empresas WHERE slug = ? AND ativo = 1", (slug,)
    ).fetchone()

    if not empresa:
        conn.close()
        return jsonify({"erro": "Empresa não encontrada."}), 404

    from services.recursos import empresa_tem_recurso, limite_atingido
    if not empresa_tem_recurso(conn, empresa["id"], "agenda"):
        conn.close()
        return jsonify({"erro": "O agendamento online não está disponível neste plano."}), 403

    limite_excedido, limite, _uso = limite_atingido(conn, empresa["id"], "agendamentos")
    if limite_excedido:
        conn.close()
        return jsonify({
            "erro": f"A agenda atingiu o limite mensal de {limite} agendamentos. Entre em contato com o estabelecimento."
        }), 403

    placeholders = ",".join("?" for _ in servico_ids)
    servicos = conn.execute(
        f"""
        SELECT *
        FROM servicos
        WHERE id IN ({placeholders})
          AND empresa_id = ?
          AND ativo = 1
        ORDER BY nome
        """,
        (*servico_ids, empresa["id"]),
    ).fetchall()

    funcionario = conn.execute(
        "SELECT * FROM funcionarios WHERE id = ? AND empresa_id = ? AND ativo = 1",
        (dados["funcionario_id"], empresa["id"]),
    ).fetchone()

    if len(servicos) != len(servico_ids) or not funcionario:
        conn.close()
        return jsonify({"erro": "Serviço ou profissional inválido."}), 400

    duracao_total = sum(int(servico["duracao"] or 0) for servico in servicos)
    valor_total = sum(float(servico["valor"] or 0) for servico in servicos)

    inicio_novo = datetime.strptime(dados["hora"], "%H:%M")
    fim_novo = inicio_novo + timedelta(minutes=duracao_total)

    existentes = conn.execute(
        """
        SELECT hora, COALESCE(duracao_total, 40) AS duracao_total
        FROM agendamentos
        WHERE empresa_id = ?
          AND funcionario_id = ?
          AND data = ?
          AND status != 'cancelado'
        """,
        (empresa["id"], funcionario["id"], dados["data"]),
    ).fetchall()

    for existente in existentes:
        inicio_existente = datetime.strptime(existente["hora"], "%H:%M")
        fim_existente = inicio_existente + timedelta(
            minutes=existente["duracao_total"] or 40
        )
        if inicio_novo < fim_existente and fim_novo > inicio_existente:
            conn.close()
            return jsonify({"erro": "Este intervalo de horário acabou de ser ocupado. Escolha outro."}), 409

    try:
        cliente_nome = dados["cliente_nome"].strip()
        cliente_telefone = normalizar_telefone(dados["cliente_telefone"])
        cliente_id = buscar_ou_criar_cliente(
            conn, empresa["id"], cliente_nome, cliente_telefone
        )

        cursor = conn.execute(
            """
            INSERT INTO agendamentos
            (
                empresa_id,
                cliente_id,
                cliente_nome,
                cliente_telefone,
                servico_id,
                funcionario_id,
                data,
                hora,
                duracao_total,
                valor_total
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                empresa["id"],
                cliente_id,
                cliente_nome,
                cliente_telefone,
                servico_ids[0],
                funcionario["id"],
                dados["data"],
                dados["hora"],
                duracao_total,
                valor_total,
            ),
        )
        agendamento_id = cursor.lastrowid

        conn.executemany(
            """
            INSERT INTO agendamento_servicos (agendamento_id, servico_id)
            VALUES (?, ?)
            """,
            [(agendamento_id, servico_id) for servico_id in servico_ids],
        )
        conn.commit()
    except DatabaseIntegrityError:
        conn.rollback()
        conn.close()
        return jsonify({"erro": "Este horário acabou de ser ocupado. Escolha outro."}), 409

    nomes_servicos = [servico["nome"] for servico in servicos]
    conn.close()

    try:
        from services.evolution_api import enviar_mensagem_agendamento
        enviar_mensagem_agendamento(empresa["id"], agendamento_id, "confirmacao")
    except Exception:
        # A indisponibilidade do WhatsApp nunca impede o agendamento público.
        pass

    mensagem = (
        f"Olá! Meu nome é {dados['cliente_nome']}. "
        f"Agendei os serviços: {', '.join(nomes_servicos)} "
        f"com {funcionario['nome']} para {dados['data']} às {dados['hora']}. "
        f"Valor total: R$ {valor_total:.2f}."
    )

    return jsonify({
        "sucesso": True,
        "mensagem": "Agendamento realizado com sucesso.",
        "whatsapp": mensagem,
        "valor_total": valor_total,
        "duracao_total": duracao_total,
    })

