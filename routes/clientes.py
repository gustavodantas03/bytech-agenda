"""Rotas do módulo CRM de clientes."""

from core import *  # noqa: F401,F403


def _validar_cliente_form(conn, empresa_id, cliente_id=None):
    nome = request.form.get("nome", "").strip()
    telefone = normalizar_telefone(request.form.get("telefone", ""))
    email = request.form.get("email", "").strip().lower()
    data_nascimento = request.form.get("data_nascimento", "").strip()
    instagram = request.form.get("instagram", "").strip()
    observacoes = request.form.get("observacoes", "").strip()

    if not nome or not telefone:
        return None, "Nome e WhatsApp são obrigatórios."

    if len(telefone) < 10 or len(telefone) > 13:
        return None, "Informe um WhatsApp válido com DDD."

    if data_nascimento:
        try:
            datetime.strptime(data_nascimento, "%Y-%m-%d")
        except ValueError:
            return None, "A data de nascimento informada é inválida."

    sql = "SELECT id FROM clientes WHERE empresa_id = ? AND telefone = ?"
    parametros = [empresa_id, telefone]
    if cliente_id is not None:
        sql += " AND id != ?"
        parametros.append(cliente_id)

    if conn.execute(sql, tuple(parametros)).fetchone():
        return None, "Já existe outro cliente com este WhatsApp."

    return {
        "nome": nome,
        "telefone": telefone,
        "email": email or None,
        "data_nascimento": data_nascimento or None,
        "instagram": instagram or None,
        "observacoes": observacoes or None,
    }, None


@app.route("/admin/crm")
@login_required
@recurso_required("crm")
def admin_crm_dashboard():
    empresa_id = session["empresa_id"]
    hoje = date.today()
    limite_inativo = (hoje - timedelta(days=60)).isoformat()
    mes_dia = hoje.strftime("-%m-%d")

    conn = get_connection()
    indicadores = conn.execute(
        """
        SELECT
            COUNT(*) AS total_clientes,
            SUM(CASE WHEN COALESCE(ativo, 1) = 1 THEN 1 ELSE 0 END) AS ativos,
            SUM(CASE WHEN criado_em >= date('now', '-30 days') THEN 1 ELSE 0 END) AS novos_30_dias,
            SUM(CASE WHEN data_nascimento IS NOT NULL AND substr(data_nascimento, 5, 6) = ? THEN 1 ELSE 0 END) AS aniversariantes_hoje
        FROM clientes
        WHERE empresa_id = ?
        """,
        (mes_dia, empresa_id),
    ).fetchone()

    comportamento = conn.execute(
        """
        SELECT
            COUNT(*) AS clientes_com_visita,
            SUM(CASE WHEN ultima_visita < ? THEN 1 ELSE 0 END) AS inativos_60_dias,
            SUM(CASE WHEN total_concluidos >= 2 THEN 1 ELSE 0 END) AS recorrentes,
            COALESCE(SUM(total_gasto), 0) AS receita_clientes,
            COALESCE(AVG(CASE WHEN total_concluidos > 0 THEN total_gasto / total_concluidos END), 0) AS ticket_medio
        FROM (
            SELECT c.id,
                   MAX(CASE WHEN a.status IN ('finalizado','concluido') THEN a.data END) AS ultima_visita,
                   SUM(CASE WHEN a.status IN ('finalizado','concluido') THEN 1 ELSE 0 END) AS total_concluidos,
                   SUM(CASE WHEN a.status IN ('finalizado','concluido') THEN COALESCE(a.valor_total,0) ELSE 0 END) AS total_gasto
            FROM clientes c
            LEFT JOIN agendamentos a ON a.cliente_id = c.id
            WHERE c.empresa_id = ? AND COALESCE(c.ativo, 1) = 1
            GROUP BY c.id
        ) dados
        """,
        (limite_inativo, empresa_id),
    ).fetchone()

    recentes = conn.execute(
        """
        SELECT c.id, c.nome, c.telefone, c.criado_em,
               COUNT(CASE WHEN a.status IN ('finalizado','concluido') THEN 1 END) AS atendimentos,
               MAX(CASE WHEN a.status IN ('finalizado','concluido') THEN a.data END) AS ultima_visita
        FROM clientes c
        LEFT JOIN agendamentos a ON a.cliente_id = c.id
        WHERE c.empresa_id = ?
        GROUP BY c.id
        ORDER BY c.criado_em DESC
        LIMIT 8
        """,
        (empresa_id,),
    ).fetchall()

    aniversariantes = conn.execute(
        """
        SELECT id, nome, telefone, data_nascimento
        FROM clientes
        WHERE empresa_id = ? AND COALESCE(ativo,1) = 1
          AND data_nascimento IS NOT NULL
          AND substr(data_nascimento, 6, 2) = strftime('%m', 'now')
        ORDER BY substr(data_nascimento, 9, 2), nome COLLATE NOCASE
        LIMIT 10
        """,
        (empresa_id,),
    ).fetchall()
    conn.close()

    return render_template(
        "admin/crm_dashboard.html",
        indicadores=indicadores,
        comportamento=comportamento,
        recentes=recentes,
        aniversariantes=aniversariantes,
    )


@app.route("/admin/clientes")
@login_required
@recurso_required("crm")
def admin_clientes():
    empresa_id = session["empresa_id"]
    busca = request.args.get("q", "").strip()
    filtro = request.args.get("filtro", "todos").strip().lower()
    filtros_validos = {"todos", "ativos", "inativos", "vip", "recompensas", "aniversariantes"}
    if filtro not in filtros_validos:
        filtro = "todos"

    conn = get_connection()
    condicoes = ["c.empresa_id = ?"]
    parametros = [empresa_id]

    if busca:
        telefone_busca = normalizar_telefone(busca)
        condicoes.append("(LOWER(c.nome) LIKE LOWER(?) OR c.telefone LIKE ? OR LOWER(COALESCE(c.email,'')) LIKE LOWER(?) OR LOWER(COALESCE(c.instagram,'')) LIKE LOWER(?))")
        parametros.extend([f"%{busca}%", f"%{telefone_busca or busca}%", f"%{busca}%", f"%{busca}%"])

    if filtro == "ativos":
        condicoes.append("COALESCE(c.ativo,1) = 1")
    elif filtro == "inativos":
        condicoes.append("COALESCE(c.ativo,1) = 0")
    elif filtro == "vip":
        condicoes.append("(c.pontos_fidelidade >= 7 OR c.recompensas_disponiveis > 0)")
    elif filtro == "recompensas":
        condicoes.append("c.recompensas_disponiveis > 0")
    elif filtro == "aniversariantes":
        condicoes.append("c.data_nascimento IS NOT NULL AND substr(c.data_nascimento, 6, 2) = strftime('%m','now')")

    where_sql = " AND ".join(condicoes)
    clientes = conn.execute(
        f"""
        SELECT c.*,
               SUM(CASE WHEN a.status IN ('finalizado','concluido') THEN 1 ELSE 0 END) AS total_concluidos,
               MAX(CASE WHEN a.status IN ('finalizado','concluido') THEN a.data END) AS ultima_visita,
               SUM(CASE WHEN a.status IN ('finalizado','concluido') THEN COALESCE(a.valor_total,0) ELSE 0 END) AS total_gasto
        FROM clientes c
        LEFT JOIN agendamentos a ON a.cliente_id = c.id
        WHERE {where_sql}
        GROUP BY c.id
        ORDER BY COALESCE(c.ativo,1) DESC, c.recompensas_disponiveis DESC, c.pontos_fidelidade DESC, c.nome COLLATE NOCASE
        """,
        tuple(parametros),
    ).fetchall()

    resumo = conn.execute(
        """
        SELECT COUNT(*) AS total_clientes,
               SUM(CASE WHEN COALESCE(ativo,1)=1 THEN 1 ELSE 0 END) AS total_ativos,
               SUM(CASE WHEN pontos_fidelidade >= 7 OR recompensas_disponiveis > 0 THEN 1 ELSE 0 END) AS total_vip,
               COALESCE(SUM(recompensas_disponiveis),0) AS recompensas_pendentes
        FROM clientes WHERE empresa_id = ?
        """,
        (empresa_id,),
    ).fetchone()
    conn.close()
    return render_template("admin/clientes.html", clientes=clientes, resumo=resumo, busca=busca, filtro=filtro)


@app.route("/admin/clientes/novo", methods=["GET", "POST"])
@login_required
@recurso_required("crm")
def admin_novo_cliente():
    empresa_id = session["empresa_id"]
    if request.method == "POST":
        conn = get_connection()
        dados, erro = _validar_cliente_form(conn, empresa_id)
        if erro:
            conn.close()
            flash(erro, "erro")
            return render_template("admin/cliente_form.html", cliente=request.form, modo="novo")
        conn.execute(
            """INSERT INTO clientes (empresa_id,nome,telefone,email,data_nascimento,instagram,observacoes,ativo)
               VALUES (?,?,?,?,?,?,?,1)""",
            (empresa_id, dados["nome"], dados["telefone"], dados["email"], dados["data_nascimento"], dados["instagram"], dados["observacoes"]),
        )
        conn.commit()
        conn.close()
        flash("Cliente cadastrado com sucesso.", "sucesso")
        return redirect(url_for("admin_clientes"))
    return render_template("admin/cliente_form.html", cliente={}, modo="novo")


@app.route("/admin/clientes/<int:cliente_id>/editar", methods=["GET", "POST"])
@login_required
@recurso_required("crm")
def admin_editar_cliente(cliente_id):
    empresa_id = session["empresa_id"]
    conn = get_connection()
    cliente = conn.execute("SELECT * FROM clientes WHERE id=? AND empresa_id=?", (cliente_id, empresa_id)).fetchone()
    if not cliente:
        conn.close(); flash("Cliente não encontrado.", "erro"); return redirect(url_for("admin_clientes"))
    if request.method == "POST":
        dados, erro = _validar_cliente_form(conn, empresa_id, cliente_id)
        if erro:
            conn.close(); flash(erro, "erro"); return redirect(url_for("admin_editar_cliente", cliente_id=cliente_id))
        ativo = 1 if request.form.get("ativo", "1") == "1" else 0
        conn.execute(
            """UPDATE clientes SET nome=?,telefone=?,email=?,data_nascimento=?,instagram=?,observacoes=?,ativo=?,atualizado_em=CURRENT_TIMESTAMP
               WHERE id=? AND empresa_id=?""",
            (dados["nome"], dados["telefone"], dados["email"], dados["data_nascimento"], dados["instagram"], dados["observacoes"], ativo, cliente_id, empresa_id),
        )
        conn.commit(); conn.close(); flash("Cliente atualizado com sucesso.", "sucesso")
        return redirect(url_for("admin_clientes"))
    conn.close()
    return render_template("admin/cliente_form.html", cliente=cliente, modo="editar")


def _data_br(data_iso):
    if not data_iso:
        return None
    try:
        return datetime.strptime(data_iso[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return data_iso


@app.route("/admin/clientes/<int:cliente_id>")
@login_required
@recurso_required("crm")
def admin_perfil_cliente(cliente_id):
    """Visão 360º do cliente com histórico e indicadores de relacionamento."""
    empresa_id = session["empresa_id"]
    status = request.args.get("status", "todos").strip().lower()
    servico_id = request.args.get("servico_id", type=int)
    funcionario_id = request.args.get("funcionario_id", type=int)
    data_inicio = request.args.get("data_inicio", "").strip()
    data_fim = request.args.get("data_fim", "").strip()

    if status not in {"todos", "agendado", "confirmado", "finalizado", "concluido", "cancelado", "faltou"}:
        status = "todos"

    conn = get_connection()
    cliente = conn.execute(
        "SELECT * FROM clientes WHERE id = ? AND empresa_id = ?",
        (cliente_id, empresa_id),
    ).fetchone()
    if not cliente:
        conn.close()
        flash("Cliente não encontrado.", "erro")
        return redirect(url_for("admin_clientes"))

    resumo = conn.execute(
        """
        SELECT
            SUM(CASE WHEN status IN ('finalizado','concluido') THEN 1 ELSE 0 END) AS atendimentos,
            COALESCE(SUM(CASE WHEN status IN ('finalizado','concluido') THEN valor_total ELSE 0 END), 0) AS total_gasto,
            COALESCE(AVG(CASE WHEN status IN ('finalizado','concluido') THEN valor_total END), 0) AS ticket_medio,
            MAX(CASE WHEN status IN ('finalizado','concluido') THEN data END) AS ultima_visita,
            MIN(CASE WHEN status IN ('agendado','confirmado') AND data >= date('now') THEN data END) AS proximo_agendamento,
            MIN(CASE WHEN status IN ('agendado','confirmado') AND data >= date('now') THEN hora END) AS proximo_horario,
            COUNT(*) AS total_registros
        FROM agendamentos
        WHERE empresa_id = ? AND cliente_id = ?
        """,
        (empresa_id, cliente_id),
    ).fetchone()

    favorito_servico = conn.execute(
        """
        SELECT s.nome, COUNT(*) AS quantidade
        FROM agendamentos a
        JOIN servicos s ON s.id = a.servico_id
        WHERE a.empresa_id = ? AND a.cliente_id = ?
          AND a.status IN ('finalizado','concluido')
        GROUP BY s.id, s.nome
        ORDER BY quantidade DESC, s.nome COLLATE NOCASE
        LIMIT 1
        """,
        (empresa_id, cliente_id),
    ).fetchone()

    favorito_profissional = conn.execute(
        """
        SELECT f.nome, COUNT(*) AS quantidade
        FROM agendamentos a
        JOIN funcionarios f ON f.id = a.funcionario_id
        WHERE a.empresa_id = ? AND a.cliente_id = ?
          AND a.status IN ('finalizado','concluido')
        GROUP BY f.id, f.nome
        ORDER BY quantidade DESC, f.nome COLLATE NOCASE
        LIMIT 1
        """,
        (empresa_id, cliente_id),
    ).fetchone()

    intervalo = conn.execute(
        """
        SELECT AVG(julianday(data) - julianday(data_anterior)) AS dias
        FROM (
            SELECT data, LAG(data) OVER (ORDER BY data) AS data_anterior
            FROM agendamentos
            WHERE empresa_id = ? AND cliente_id = ?
              AND status IN ('finalizado','concluido')
        ) visitas
        WHERE data_anterior IS NOT NULL
        """,
        (empresa_id, cliente_id),
    ).fetchone()

    condicoes = ["a.empresa_id = ?", "a.cliente_id = ?"]
    parametros = [empresa_id, cliente_id]
    if status != "todos":
        condicoes.append("a.status = ?")
        parametros.append(status)
    if servico_id:
        condicoes.append("(a.servico_id = ? OR EXISTS (SELECT 1 FROM agendamento_servicos axs WHERE axs.agendamento_id=a.id AND axs.servico_id=?))")
        parametros.extend([servico_id, servico_id])
    if funcionario_id:
        condicoes.append("a.funcionario_id = ?")
        parametros.append(funcionario_id)
    if data_inicio:
        condicoes.append("a.data >= ?")
        parametros.append(data_inicio)
    if data_fim:
        condicoes.append("a.data <= ?")
        parametros.append(data_fim)

    historico = conn.execute(
        f"""
        SELECT a.*, f.nome AS profissional_nome, s.nome AS servico_principal,
               COALESCE((
                   SELECT GROUP_CONCAT(s2.nome, ', ')
                   FROM agendamento_servicos axs
                   JOIN servicos s2 ON s2.id = axs.servico_id
                   WHERE axs.agendamento_id = a.id
                   ORDER BY axs.ordem
               ), s.nome) AS servicos_nomes
        FROM agendamentos a
        LEFT JOIN funcionarios f ON f.id = a.funcionario_id
        LEFT JOIN servicos s ON s.id = a.servico_id
        WHERE {' AND '.join(condicoes)}
        ORDER BY a.data DESC, a.hora DESC, a.id DESC
        """,
        tuple(parametros),
    ).fetchall()

    evolucao = conn.execute(
        """
        SELECT substr(data,1,7) AS mes,
               COUNT(*) AS atendimentos,
               COALESCE(SUM(valor_total),0) AS total
        FROM agendamentos
        WHERE empresa_id = ? AND cliente_id = ?
          AND status IN ('finalizado','concluido')
          AND data >= date('now','-11 months','start of month')
        GROUP BY substr(data,1,7)
        ORDER BY mes
        """,
        (empresa_id, cliente_id),
    ).fetchall()

    servicos = conn.execute(
        "SELECT id,nome FROM servicos WHERE empresa_id=? AND ativo=1 ORDER BY nome COLLATE NOCASE",
        (empresa_id,),
    ).fetchall()
    profissionais = conn.execute(
        "SELECT id,nome FROM funcionarios WHERE empresa_id=? AND ativo=1 ORDER BY nome COLLATE NOCASE",
        (empresa_id,),
    ).fetchall()
    recompensas_fidelidade = conn.execute(
        """SELECT * FROM fidelidade_recompensas
           WHERE empresa_id=? AND ativo=1 AND pontos_necessarios <= ?
           ORDER BY pontos_necessarios, nome COLLATE NOCASE""",
        (empresa_id, int(cliente["pontos_fidelidade"] or 0)),
    ).fetchall()
    movimentos_fidelidade = conn.execute(
        """SELECT * FROM fidelidade_movimentos
           WHERE empresa_id=? AND cliente_id=? ORDER BY id DESC LIMIT 12""",
        (empresa_id, cliente_id),
    ).fetchall()
    config_fidelidade = conn.execute(
        "SELECT * FROM fidelidade_configuracoes WHERE empresa_id=?",
        (empresa_id,),
    ).fetchone()
    conn.close()

    atendimentos = int(resumo["atendimentos"] or 0)
    classificacao = "Novo cliente"
    if atendimentos >= 10 or float(resumo["total_gasto"] or 0) >= 1000:
        classificacao = "Cliente VIP"
    elif atendimentos >= 2:
        classificacao = "Cliente recorrente"
    if resumo["ultima_visita"]:
        try:
            ultima = datetime.strptime(resumo["ultima_visita"][:10], "%Y-%m-%d").date()
            if (date.today() - ultima).days >= 60:
                classificacao = "Cliente inativo"
        except ValueError:
            pass

    return render_template(
        "admin/cliente_perfil.html",
        cliente=cliente,
        resumo=resumo,
        historico=historico,
        favorito_servico=favorito_servico,
        favorito_profissional=favorito_profissional,
        frequencia_dias=round(intervalo["dias"] or 0),
        classificacao=classificacao,
        evolucao=evolucao,
        servicos=servicos,
        profissionais=profissionais,
        recompensas_fidelidade=recompensas_fidelidade,
        movimentos_fidelidade=movimentos_fidelidade,
        config_fidelidade=config_fidelidade,
        filtros={
            "status": status,
            "servico_id": servico_id,
            "funcionario_id": funcionario_id,
            "data_inicio": data_inicio,
            "data_fim": data_fim,
        },
        data_br=_data_br,
    )


@app.route("/admin/clientes/<int:cliente_id>/observacoes", methods=["POST"])
@login_required
@recurso_required("crm")
def admin_salvar_observacoes_cliente(cliente_id):
    empresa_id = session["empresa_id"]
    observacoes = request.form.get("observacoes", "").strip()[:2000]
    conn = get_connection()
    cursor = conn.execute(
        "UPDATE clientes SET observacoes=?, atualizado_em=CURRENT_TIMESTAMP WHERE id=? AND empresa_id=?",
        (observacoes or None, cliente_id, empresa_id),
    )
    conn.commit()
    conn.close()
    if cursor.rowcount:
        flash("Observações atualizadas com sucesso.", "sucesso")
    else:
        flash("Cliente não encontrado.", "erro")
    return redirect(url_for("admin_perfil_cliente", cliente_id=cliente_id))
