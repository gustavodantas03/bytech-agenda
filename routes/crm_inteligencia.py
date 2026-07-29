"""Inteligência de relacionamento, segmentação e campanhas do CRM."""

from core import *  # noqa: F401,F403


ALVOS_VALIDOS = {"todos", "vip", "inativos", "aniversariantes", "risco"}


def _config_crm(conn, empresa_id):
    config = conn.execute(
        "SELECT * FROM crm_configuracoes WHERE empresa_id=?",
        (empresa_id,),
    ).fetchone()
    if not config:
        conn.execute(
            "INSERT INTO crm_configuracoes (empresa_id) VALUES (?)",
            (empresa_id,),
        )
        conn.commit()
        config = conn.execute(
            "SELECT * FROM crm_configuracoes WHERE empresa_id=?",
            (empresa_id,),
        ).fetchone()
    return config


def _segmento_sql(config):
    inativo = int(config["dias_inatividade"] or 60)
    risco = max(1, int(config["dias_risco"] or 30))
    vip_valor = float(config["vip_valor_minimo"] or 500)
    vip_visitas = int(config["vip_visitas_minimas"] or 8)
    return inativo, risco, vip_valor, vip_visitas


@app.route("/admin/crm/inteligencia")
@login_required
@recurso_required("crm")
def admin_crm_inteligencia():
    empresa_id = session["empresa_id"]
    janela = request.args.get("janela", "mes")
    if janela not in {"hoje", "semana", "mes"}:
        janela = "mes"

    conn = get_connection()
    config = _config_crm(conn, empresa_id)
    dias_inatividade, dias_risco, vip_valor, vip_visitas = _segmento_sql(config)

    base = conn.execute(
        """
        SELECT c.id,c.nome,c.telefone,c.email,c.data_nascimento,c.instagram,c.ativo,
               c.pontos_fidelidade,c.criado_em,
               MAX(CASE WHEN a.status IN ('finalizado','concluido') THEN a.data END) ultima_visita,
               SUM(CASE WHEN a.status IN ('finalizado','concluido') THEN 1 ELSE 0 END) visitas,
               SUM(CASE WHEN a.status IN ('finalizado','concluido') THEN COALESCE(a.valor_total,0) ELSE 0 END) total_gasto
        FROM clientes c
        LEFT JOIN agendamentos a ON a.cliente_id=c.id
        WHERE c.empresa_id=? AND COALESCE(c.ativo,1)=1
        GROUP BY c.id
        """,
        (empresa_id,),
    ).fetchall()

    hoje = date.today()
    clientes = []
    for row in base:
        item = dict(row)
        ultima = None
        if item.get("ultima_visita"):
            try:
                ultima = datetime.strptime(item["ultima_visita"][:10], "%Y-%m-%d").date()
            except (ValueError, TypeError):
                ultima = None
        dias_sem_visita = (hoje - ultima).days if ultima else None
        item["dias_sem_visita"] = dias_sem_visita
        item["vip"] = float(item.get("total_gasto") or 0) >= vip_valor or int(item.get("visitas") or 0) >= vip_visitas
        item["inativo_crm"] = dias_sem_visita is not None and dias_sem_visita >= dias_inatividade
        item["risco"] = dias_sem_visita is not None and dias_risco <= dias_sem_visita < dias_inatividade
        clientes.append(item)

    aniversariantes = []
    for item in clientes:
        nascimento = item.get("data_nascimento")
        if not nascimento:
            continue
        try:
            nasc = datetime.strptime(nascimento[:10], "%Y-%m-%d").date()
            aniversario = nasc.replace(year=hoje.year)
        except ValueError:
            continue
        delta = (aniversario - hoje).days
        if delta < 0:
            try:
                aniversario = nasc.replace(year=hoje.year + 1)
                delta = (aniversario - hoje).days
            except ValueError:
                continue
        limite = 0 if janela == "hoje" else 7 if janela == "semana" else 31
        if 0 <= delta <= limite:
            copia = dict(item)
            copia["aniversario_em"] = delta
            aniversariantes.append(copia)
    aniversariantes.sort(key=lambda x: (x["aniversario_em"], x["nome"].lower()))

    vips = sorted([c for c in clientes if c["vip"]], key=lambda x: (-float(x.get("total_gasto") or 0), x["nome"].lower()))
    inativos = sorted([c for c in clientes if c["inativo_crm"]], key=lambda x: (-(x["dias_sem_visita"] or 0), x["nome"].lower()))
    risco = sorted([c for c in clientes if c["risco"]], key=lambda x: (-(x["dias_sem_visita"] or 0), x["nome"].lower()))

    campanhas = conn.execute(
        """SELECT *,
                  CASE WHEN ativo=1 AND (data_inicio IS NULL OR data_inicio<=CURRENT_DATE)
                              AND (data_fim IS NULL OR data_fim>=CURRENT_DATE) THEN 1 ELSE 0 END em_andamento
           FROM crm_campanhas WHERE empresa_id=?
           ORDER BY ativo DESC, criado_em DESC""",
        (empresa_id,),
    ).fetchall()

    campanhas_resumo = conn.execute(
        """SELECT COUNT(*) total,
                  SUM(CASE WHEN ativo=1 THEN 1 ELSE 0 END) ativas,
                  SUM(CASE WHEN status='rascunho' THEN 1 ELSE 0 END) rascunhos
           FROM crm_campanhas WHERE empresa_id=?""",
        (empresa_id,),
    ).fetchone()
    conn.close()

    indicadores = {
        "total": len(clientes),
        "vips": len(vips),
        "inativos": len(inativos),
        "risco": len(risco),
        "aniversariantes": len(aniversariantes),
        "campanhas_ativas": int(campanhas_resumo["ativas"] or 0),
    }

    return render_template(
        "admin/crm_inteligencia.html",
        config=config,
        indicadores=indicadores,
        aniversariantes=aniversariantes[:20],
        vips=vips[:20],
        inativos=inativos[:20],
        risco=risco[:20],
        campanhas=campanhas,
        janela=janela,
    )


@app.route("/admin/crm/inteligencia/configuracoes", methods=["POST"])
@login_required
@recurso_required("crm")
def admin_crm_configuracoes():
    empresa_id = session["empresa_id"]
    try:
        dias_inatividade = max(15, int(request.form.get("dias_inatividade", "60")))
        dias_risco = max(7, int(request.form.get("dias_risco", "30")))
        if dias_risco >= dias_inatividade:
            raise ValueError
        vip_valor = max(0, float(request.form.get("vip_valor_minimo", "500").replace(",", ".")))
        vip_visitas = max(1, int(request.form.get("vip_visitas_minimas", "8")))
    except ValueError:
        flash("Revise os critérios: o risco deve ser menor que a inatividade.", "erro")
        return redirect(url_for("admin_crm_inteligencia"))

    conn = get_connection()
    conn.execute(
        """INSERT INTO crm_configuracoes
           (empresa_id,dias_inatividade,dias_risco,vip_valor_minimo,vip_visitas_minimas,atualizado_em)
           VALUES (?,?,?,?,?,CURRENT_TIMESTAMP)
           ON CONFLICT(empresa_id) DO UPDATE SET
             dias_inatividade=excluded.dias_inatividade,
             dias_risco=excluded.dias_risco,
             vip_valor_minimo=excluded.vip_valor_minimo,
             vip_visitas_minimas=excluded.vip_visitas_minimas,
             atualizado_em=CURRENT_TIMESTAMP""",
        (empresa_id, dias_inatividade, dias_risco, vip_valor, vip_visitas),
    )
    conn.commit(); conn.close()
    flash("Critérios de inteligência atualizados.", "sucesso")
    return redirect(url_for("admin_crm_inteligencia"))


@app.route("/admin/crm/campanhas/nova", methods=["POST"])
@login_required
@recurso_required("crm")
def admin_crm_nova_campanha():
    empresa_id = session["empresa_id"]
    nome = request.form.get("nome", "").strip()
    publico = request.form.get("publico_alvo", "todos").strip().lower()
    mensagem = request.form.get("mensagem", "").strip()
    data_inicio = request.form.get("data_inicio", "").strip() or None
    data_fim = request.form.get("data_fim", "").strip() or None
    status = request.form.get("status", "rascunho")
    if publico not in ALVOS_VALIDOS:
        publico = "todos"
    if status not in {"rascunho", "pronta"}:
        status = "rascunho"
    if not nome or not mensagem:
        flash("Informe o nome e a mensagem da campanha.", "erro")
        return redirect(url_for("admin_crm_inteligencia"))
    if data_inicio and data_fim and data_fim < data_inicio:
        flash("A data final não pode ser anterior à inicial.", "erro")
        return redirect(url_for("admin_crm_inteligencia"))

    conn = get_connection()
    conn.execute(
        """INSERT INTO crm_campanhas
           (empresa_id,nome,publico_alvo,mensagem,data_inicio,data_fim,status,ativo)
           VALUES (?,?,?,?,?,?,?,?)""",
        (empresa_id, nome, publico, mensagem[:1000], data_inicio, data_fim, status, 1 if status == "pronta" else 0),
    )
    conn.commit(); conn.close()
    flash("Campanha cadastrada com sucesso.", "sucesso")
    return redirect(url_for("admin_crm_inteligencia"))


@app.route("/admin/crm/campanhas/<int:campanha_id>/status", methods=["POST"])
@login_required
@recurso_required("crm")
def admin_crm_status_campanha(campanha_id):
    empresa_id = session["empresa_id"]
    conn = get_connection()
    conn.execute(
        """UPDATE crm_campanhas SET ativo=CASE WHEN ativo=1 THEN 0 ELSE 1 END,
           status=CASE WHEN ativo=1 THEN 'rascunho' ELSE 'pronta' END,
           atualizado_em=CURRENT_TIMESTAMP WHERE id=? AND empresa_id=?""",
        (campanha_id, empresa_id),
    )
    conn.commit(); conn.close()
    flash("Status da campanha atualizado.", "sucesso")
    return redirect(url_for("admin_crm_inteligencia"))


@app.route("/admin/crm/campanhas/<int:campanha_id>/excluir", methods=["POST"])
@login_required
@recurso_required("crm")
def admin_crm_excluir_campanha(campanha_id):
    empresa_id = session["empresa_id"]
    conn = get_connection()
    conn.execute("DELETE FROM crm_campanhas WHERE id=? AND empresa_id=?", (campanha_id, empresa_id))
    conn.commit(); conn.close()
    flash("Campanha removida.", "sucesso")
    return redirect(url_for("admin_crm_inteligencia"))
