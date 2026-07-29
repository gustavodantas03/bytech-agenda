"""Rotas e indicadores do dashboard administrativo."""

from datetime import date, datetime, timedelta

from core import *  # noqa: F401,F403


@app.route("/admin/api/ultimo-agendamento")
@login_required
def admin_ultimo_agendamento():
    empresa_id = session["empresa_id"]

    conn = get_connection()
    ultimo = conn.execute(
        """
        SELECT
            a.id,
            a.cliente_nome,
            a.cliente_telefone,
            a.data,
            a.hora,
            a.status,
            COALESCE(
                (
                    SELECT GROUP_CONCAT(s2.nome, ' + ')
                    FROM agendamento_servicos ags
                    JOIN servicos s2
                        ON s2.id = ags.servico_id
                    WHERE ags.agendamento_id = a.id
                ),
                s.nome
            ) AS servico_nome,
            f.nome AS funcionario_nome
        FROM agendamentos a
        JOIN servicos s
            ON s.id = a.servico_id
        LEFT JOIN funcionarios f
            ON f.id = a.funcionario_id
        WHERE a.empresa_id = ?
        ORDER BY a.id DESC
        LIMIT 1
        """,
        (empresa_id,),
    ).fetchone()
    conn.close()

    if not ultimo:
        return jsonify({"id": 0})

    return jsonify({
        "id": ultimo["id"],
        "cliente_nome": ultimo["cliente_nome"],
        "cliente_telefone": ultimo["cliente_telefone"],
        "servico_nome": ultimo["servico_nome"],
        "funcionario_nome": ultimo["funcionario_nome"] or "Sem profissional",
        "data": ultimo["data"],
        "hora": ultimo["hora"],
        "status": ultimo["status"],
    })


@app.route("/admin")
@login_required
def admin_dashboard():
    empresa_id = session["empresa_id"]
    usuario_id = session.get("usuario_id")

    hoje_data = date.today()
    hoje_iso = hoje_data.isoformat()
    inicio_mes = hoje_data.replace(day=1).isoformat()

    if hoje_data.month == 12:
        inicio_proximo_mes = hoje_data.replace(
            year=hoje_data.year + 1,
            month=1,
            day=1,
        ).isoformat()
    else:
        inicio_proximo_mes = hoje_data.replace(
            month=hoje_data.month + 1,
            day=1,
        ).isoformat()

    conn = get_connection()

    empresa = conn.execute(
        "SELECT * FROM empresas WHERE id = ?",
        (empresa_id,),
    ).fetchone()

    conta = None
    if usuario_id:
        conta = conn.execute(
            """
            SELECT *
            FROM usuarios
            WHERE id = ? AND empresa_id = ?
            """,
            (usuario_id, empresa_id),
        ).fetchone()

    agendamentos = conn.execute(
        """
        SELECT
            a.*,
            COALESCE(
                (
                    SELECT GROUP_CONCAT(s2.nome, ' + ')
                    FROM agendamento_servicos ags
                    JOIN servicos s2
                        ON s2.id = ags.servico_id
                    WHERE ags.agendamento_id = a.id
                ),
                s.nome
            ) AS servico_nome,
            f.nome AS funcionario_nome
        FROM agendamentos a
        JOIN servicos s
            ON s.id = a.servico_id
        LEFT JOIN funcionarios f
            ON f.id = a.funcionario_id
        WHERE a.empresa_id = ?
          AND a.data = ?
        ORDER BY a.hora, f.nome
        """,
        (empresa_id, hoje_iso),
    ).fetchall()

    total = conn.execute(
        """
        SELECT COUNT(*) AS total
        FROM agendamentos
        WHERE empresa_id = ?
        """,
        (empresa_id,),
    ).fetchone()["total"]

    total_funcionarios = conn.execute(
        """
        SELECT COUNT(*) AS total
        FROM funcionarios
        WHERE empresa_id = ? AND ativo = 1
        """,
        (empresa_id,),
    ).fetchone()["total"]

    total_clientes = conn.execute(
        """
        SELECT COUNT(*) AS total
        FROM clientes
        WHERE empresa_id = ?
        """,
        (empresa_id,),
    ).fetchone()["total"]

    recompensas_pendentes = conn.execute(
        """
        SELECT COALESCE(SUM(recompensas_disponiveis), 0) AS total
        FROM clientes
        WHERE empresa_id = ?
        """,
        (empresa_id,),
    ).fetchone()["total"]

    faturamento_mes = conn.execute(
        """
        SELECT COALESCE(SUM(valor_total), 0) AS total
        FROM agendamentos
        WHERE empresa_id = ?
          AND data >= ?
          AND data < ?
          AND LOWER(COALESCE(status, 'agendado')) != 'cancelado'
        """,
        (
            empresa_id,
            inicio_mes,
            inicio_proximo_mes,
        ),
    ).fetchone()["total"]

    dados_semana = []
    dias_semana = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]

    for deslocamento in range(6, -1, -1):
        dia = hoje_data - timedelta(days=deslocamento)
        quantidade = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM agendamentos
            WHERE empresa_id = ?
              AND data = ?
              AND LOWER(COALESCE(status, 'agendado')) != 'cancelado'
            """,
            (empresa_id, dia.isoformat()),
        ).fetchone()["total"]

        dados_semana.append({
            "data": dia.isoformat(),
            "dia": dias_semana[dia.weekday()],
            "quantidade": quantidade,
        })

    maior_quantidade = max(
        (item["quantidade"] for item in dados_semana),
        default=0,
    )

    for item in dados_semana:
        item["percentual"] = (
            round(item["quantidade"] / maior_quantidade * 100)
            if maior_quantidade
            else 0
        )

    cliente_destaque = conn.execute(
        """
        SELECT
            nome,
            pontos_fidelidade,
            recompensas_disponiveis
        FROM clientes
        WHERE empresa_id = ?
        ORDER BY
            recompensas_disponiveis DESC,
            pontos_fidelidade DESC,
            atualizado_em DESC
        LIMIT 1
        """,
        (empresa_id,),
    ).fetchone()

    total_servicos = conn.execute(
        """
        SELECT COUNT(*) AS total
        FROM servicos
        WHERE empresa_id = ? AND ativo = 1
        """,
        (empresa_id,),
    ).fetchone()["total"]

    whatsapp_config = conn.execute(
        """
        SELECT base_url, api_key, instance_name, status
        FROM whatsapp_configuracoes
        WHERE empresa_id = ?
        """,
        (empresa_id,),
    ).fetchone()

    conn.close()

    perfil_completo = bool(
        empresa
        and empresa["telefone"]
        and empresa["endereco"]
        and empresa["horario_texto"]
    )
    from services.evolution_api import infraestrutura_evolution_configurada
    whatsapp_configurado = bool(
        whatsapp_config
        and whatsapp_config["instance_name"]
        and whatsapp_config["status"] == "conectado"
        and infraestrutura_evolution_configurada()
    )

    onboarding_etapas = [
        {
            "titulo": "Complete os dados da empresa",
            "descricao": "Telefone, endereço e horário de funcionamento.",
            "concluido": perfil_completo,
            "endpoint": "admin_meu_espaco",
            "acao": "Completar cadastro",
            "icone": "🏢",
        },
        {
            "titulo": "Cadastre os profissionais",
            "descricao": "Adicione quem realizará os atendimentos.",
            "concluido": total_funcionarios > 0,
            "endpoint": "admin_funcionarios",
            "acao": "Cadastrar profissional",
            "icone": "👤",
        },
        {
            "titulo": "Cadastre os serviços",
            "descricao": "Defina preço, duração e serviços disponíveis.",
            "concluido": total_servicos > 0,
            "endpoint": "admin_servicos",
            "acao": "Cadastrar serviço",
            "icone": "✦",
        },
        {
            "titulo": "Conecte o WhatsApp",
            "descricao": "Prepare confirmações e lembretes automáticos.",
            "concluido": whatsapp_configurado,
            "endpoint": "admin_whatsapp",
            "acao": "Configurar WhatsApp",
            "icone": "💬",
        },
    ]
    onboarding_concluidas = sum(1 for etapa in onboarding_etapas if etapa["concluido"])
    onboarding_percentual = round(onboarding_concluidas / len(onboarding_etapas) * 100)
    onboarding_completo = onboarding_concluidas == len(onboarding_etapas)

    hora_atual = datetime.now().hour
    if hora_atual < 12:
        saudacao_texto = "Bom dia"
        saudacao_icone = "☀️"
    elif hora_atual < 18:
        saudacao_texto = "Boa tarde"
        saudacao_icone = "☀️"
    else:
        saudacao_texto = "Boa noite"
        saudacao_icone = "🌙"

    data_extenso = (
        f"{DIAS_SEMANA[hoje_data.weekday()]}, "
        f"{hoje_data.day} de "
        f"{MESES[hoje_data.month - 1]} de "
        f"{hoje_data.year}"
    )

    quantidade_hoje = len(agendamentos)
    if quantidade_hoje == 0:
        mensagem_dia = (
            "Aproveite o dia para divulgar seus serviços "
            "e organizar a agenda."
        )
    elif quantidade_hoje <= 4:
        mensagem_dia = "Sua agenda está tranquila e bem organizada para hoje."
    elif quantidade_hoje <= 10:
        mensagem_dia = "Hoje promete ser um ótimo dia de atendimentos."
    else:
        mensagem_dia = "Dia movimentado! Sua agenda está cheia de oportunidades."

    return render_template(
        "admin/dashboard.html",
        empresa=empresa,
        conta=conta,
        agendamentos=agendamentos,
        total=total,
        total_funcionarios=total_funcionarios,
        total_clientes=total_clientes,
        recompensas_pendentes=recompensas_pendentes,
        faturamento_mes=faturamento_mes,
        dados_semana=dados_semana,
        cliente_destaque=cliente_destaque,
        saudacao=saudacao_texto,
        saudacao_icone=saudacao_icone,
        data_extenso=data_extenso,
        hoje=hoje_iso,
        mensagem_dia=mensagem_dia,
        total_servicos=total_servicos,
        onboarding_etapas=onboarding_etapas,
        onboarding_concluidas=onboarding_concluidas,
        onboarding_percentual=onboarding_percentual,
        onboarding_completo=onboarding_completo,
        whatsapp_configurado=whatsapp_configurado,
    )
