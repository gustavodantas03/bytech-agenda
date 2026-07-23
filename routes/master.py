"""Rotas do módulo master."""

from core import *  # noqa: F401,F403
from io import BytesIO
import sqlite3

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
except ImportError:  # O restante do sistema continua funcionando sem PDF.
    A4 = None
    canvas = None

@app.route("/master")
@master_login_required
def master_dashboard():
    from services.financeiro import atualizar_todas_empresas

    conn = get_connection()
    atualizar_todas_empresas(conn)
    resumo = conn.execute("""
        SELECT COUNT(*) total,
            COALESCE(SUM(CASE WHEN ativo=1 THEN 1 ELSE 0 END),0) ativas,
            COALESCE(SUM(CASE WHEN ativo=0 THEN 1 ELSE 0 END),0) bloqueadas,
            COALESCE(SUM(CASE WHEN status_pagamento='em_dia' THEN 1 ELSE 0 END),0) em_dia,
            COALESCE(SUM(CASE WHEN status_pagamento='pendente' THEN 1 ELSE 0 END),0) pendentes,
            COALESCE(SUM(CASE WHEN status_pagamento='inadimplente' THEN 1 ELSE 0 END),0) inadimplentes,
            COALESCE(SUM(mensalidade),0) receita_prevista
        FROM empresas
    """).fetchone()
    recebido_mes = conn.execute("""
        SELECT COALESCE(SUM(valor),0) total FROM pagamentos
        WHERE substr(data_pagamento,1,7)=strftime('%Y-%m','now','localtime')
    """).fetchone()["total"]
    historico = conn.execute("""
        WITH RECURSIVE meses(n, competencia) AS (
            SELECT 5, strftime('%Y-%m','now','localtime','-5 months')
            UNION ALL SELECT n-1, strftime('%Y-%m','now','localtime', printf('-%d months', n-1)) FROM meses WHERE n>0
        )
        SELECT competencia,
          COALESCE((SELECT SUM(valor) FROM cobrancas WHERE cobrancas.competencia=meses.competencia),0) previsto,
          COALESCE((SELECT SUM(valor) FROM pagamentos WHERE substr(data_pagamento,1,7)=meses.competencia),0) recebido
        FROM meses ORDER BY competencia
    """).fetchall()
    empresas_recentes = conn.execute("""
        SELECT id,nome,segmento,plano,status_pagamento FROM empresas ORDER BY id DESC LIMIT 6
    """).fetchall()
    pagamentos_recentes = conn.execute("""
        SELECT p.valor,p.data_pagamento,p.forma_pagamento,e.nome empresa_nome
        FROM pagamentos p JOIN empresas e ON e.id=p.empresa_id
        ORDER BY p.data_pagamento DESC,p.id DESC LIMIT 6
    """).fetchall()
    conn.close()
    return render_template(
        "master/dashboard.html", resumo=resumo, recebido_mes=recebido_mes,
        historico=historico, empresas_recentes=empresas_recentes,
        pagamentos_recentes=pagamentos_recentes,
    )


@app.route("/master/empresas")
@master_login_required
def master_empresas():
    from services.financeiro import atualizar_todas_empresas

    busca = request.args.get("q", "").strip()
    segmento_filtro = request.args.get("segmento", "").strip().lower()
    status_filtro = request.args.get("status", "").strip().lower()
    conn = get_connection()
    atualizar_todas_empresas(conn)
    condicoes = ["1 = 1"]
    parametros = []
    if busca:
        condicoes.append("(LOWER(e.nome) LIKE LOWER(?) OR LOWER(e.slug) LIKE LOWER(?) OR LOWER(COALESCE(u.usuario, '')) LIKE LOWER(?))")
        termo = f"%{busca}%"
        parametros.extend([termo, termo, termo])
    if segmento_filtro in SEGMENTOS:
        condicoes.append("e.segmento = ?")
        parametros.append(segmento_filtro)
    if status_filtro == "ativas":
        condicoes.append("e.ativo = 1")
    elif status_filtro == "bloqueadas":
        condicoes.append("e.ativo = 0")
    elif status_filtro in ("em_dia", "pendente", "inadimplente"):
        condicoes.append("e.status_pagamento = ?")
        parametros.append(status_filtro)
    empresas = conn.execute(f"""
        SELECT e.*, u.usuario,
            (SELECT COUNT(*) FROM funcionarios f WHERE f.empresa_id=e.id) total_funcionarios,
            (SELECT COUNT(*) FROM servicos s WHERE s.empresa_id=e.id) total_servicos,
            (SELECT COUNT(*) FROM clientes c WHERE c.empresa_id=e.id) total_clientes,
            (SELECT COUNT(*) FROM agendamentos a WHERE a.empresa_id=e.id) total_agendamentos,
            (SELECT id FROM cobrancas c WHERE c.empresa_id=e.id AND c.status!='paga' ORDER BY c.vencimento LIMIT 1) cobranca_aberta_id
        FROM empresas e LEFT JOIN usuarios u ON u.empresa_id=e.id
        WHERE {' AND '.join(condicoes)}
        ORDER BY CASE e.status_pagamento WHEN 'inadimplente' THEN 1 WHEN 'pendente' THEN 2 ELSE 3 END, e.ativo DESC,e.nome COLLATE NOCASE
    """, tuple(parametros)).fetchall()
    resumo = conn.execute("""
        SELECT COUNT(*) total,COALESCE(SUM(CASE WHEN ativo=1 THEN 1 ELSE 0 END),0) ativas,
        COALESCE(SUM(CASE WHEN ativo=0 THEN 1 ELSE 0 END),0) bloqueadas,
        COALESCE(SUM(CASE WHEN status_pagamento='em_dia' THEN 1 ELSE 0 END),0) em_dia,
        COALESCE(SUM(CASE WHEN status_pagamento='pendente' THEN 1 ELSE 0 END),0) pendentes,
        COALESCE(SUM(CASE WHEN status_pagamento='inadimplente' THEN 1 ELSE 0 END),0) inadimplentes,
        COALESCE(SUM(mensalidade),0) receita_prevista FROM empresas
    """).fetchone()
    recebido_mes = conn.execute("SELECT COALESCE(SUM(valor),0) total FROM pagamentos WHERE substr(data_pagamento,1,7)=strftime('%Y-%m','now','localtime')").fetchone()["total"]
    historico = conn.execute("""WITH RECURSIVE meses(n, competencia) AS (SELECT 5,strftime('%Y-%m','now','localtime','-5 months') UNION ALL SELECT n-1,strftime('%Y-%m','now','localtime',printf('-%d months',n-1)) FROM meses WHERE n>0) SELECT competencia,COALESCE((SELECT SUM(valor) FROM cobrancas WHERE cobrancas.competencia=meses.competencia),0) previsto,COALESCE((SELECT SUM(valor) FROM pagamentos WHERE substr(data_pagamento,1,7)=meses.competencia),0) recebido FROM meses ORDER BY competencia""").fetchall()
    conn.close()
    return render_template("master/empresas.html", empresas=empresas,resumo=resumo,recebido_mes=recebido_mes,historico=historico,segmentos=SEGMENTOS,busca=busca,segmento_filtro=segmento_filtro,status_filtro=status_filtro)


@app.route("/master/empresas/nova", methods=["GET", "POST"])
@master_login_required
def master_nova_empresa():
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        slug = request.form.get("slug", "").strip().lower()
        telefone = request.form.get("telefone", "").strip()
        instagram = request.form.get("instagram", "").strip()
        endereco = request.form.get("endereco", "").strip()
        maps_url = request.form.get("maps_url", "").strip()
        horario_texto = request.form.get("horario_texto", "").strip()
        descricao = request.form.get("descricao", "").strip()
        usuario = request.form.get("usuario", "").strip()
        senha = request.form.get("senha", "").strip()
        segmento = request.form.get(
            "segmento",
            "barbearia",
        ).strip().lower()
        plano_id = request.form.get("plano_id", "").strip()
        plano_registro = None
        try:
            mensalidade = float(request.form.get("mensalidade", "0").replace(",", ".") or 0)
        except ValueError:
            mensalidade = 0
        try:
            dia_vencimento = int(request.form.get("dia_vencimento", "10") or 10)
        except ValueError:
            dia_vencimento = 10
        status_pagamento = "em_dia"
        proximo_vencimento = request.form.get("proximo_vencimento", "").strip() or None
        ultimo_pagamento = request.form.get("ultimo_pagamento", "").strip() or None
        tolerancia_dias = int(request.form.get("tolerancia_dias", "5") or 5)
        bloquear_apos_dias = int(request.form.get("bloquear_apos_dias", "15") or 15)

        if segmento not in SEGMENTOS:
            flash("Segmento inválido.", "erro")
            return redirect(url_for("master_nova_empresa"))

        if not all([nome, slug, usuario, senha]):
            flash("Preencha os campos obrigatórios.", "erro")
            return redirect(url_for("master_nova_empresa"))

        slug = "-".join(slug.split())
        config = obter_config_segmento(segmento)

        conn = get_connection()
        if plano_id:
            plano_registro = conn.execute("SELECT * FROM planos WHERE id = ? AND ativo = 1", (plano_id,)).fetchone()
        if not plano_registro:
            plano_registro = conn.execute("SELECT * FROM planos WHERE ativo = 1 ORDER BY valor, id LIMIT 1").fetchone()
        plano = plano_registro["nome"] if plano_registro else "Essencial"
        if mensalidade <= 0 and plano_registro:
            mensalidade = float(plano_registro["valor"] or 0)

        slug_existente = conn.execute(
            "SELECT id FROM empresas WHERE slug = ?",
            (slug,),
        ).fetchone()

        usuario_existente = conn.execute(
            "SELECT id FROM usuarios WHERE usuario = ?",
            (usuario,),
        ).fetchone()

        if slug_existente:
            conn.close()
            flash("Este link já está sendo utilizado.", "erro")
            return redirect(url_for("master_nova_empresa"))

        if usuario_existente:
            conn.close()
            flash("Este usuário já está sendo utilizado.", "erro")
            return redirect(url_for("master_nova_empresa"))

        try:
            cursor = conn.execute(
                """
                INSERT INTO empresas (
                    nome, slug, telefone, instagram, endereco, maps_url, descricao,
                    segmento, template_admin, template_cliente, cor_principal,
                    cor_secundaria, cor_botao, cor_sidebar, horario_texto, plano,
                    plano_id, mensalidade, dia_vencimento, status_pagamento,
                    proximo_vencimento, ultimo_pagamento, tolerancia_dias,
                    bloquear_apos_dias, ativo
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, 1
                )
                """,
                (
                    nome, slug, telefone, instagram, endereco, maps_url,
                    descricao or "Agende seu horário de forma rápida e simples.",
                    segmento, config["template_admin"], config["template_cliente"],
                    config["cor_principal"], config["cor_secundaria"],
                    config["cor_botao"], config["cor_sidebar"], horario_texto, plano,
                    plano_registro["id"] if plano_registro else None, mensalidade,
                    dia_vencimento, status_pagamento, proximo_vencimento,
                    ultimo_pagamento, tolerancia_dias, bloquear_apos_dias,
                ),
            )

            empresa_id = cursor.lastrowid
            if plano_registro:
                conn.execute("UPDATE empresas SET plano_id = ? WHERE id = ?", (plano_registro["id"], empresa_id))

            conn.execute(
                """
                INSERT INTO usuarios (
                    empresa_id,
                    usuario,
                    senha
                )
                VALUES (?, ?, ?)
                """,
                (
                    empresa_id,
                    usuario,
                    senha,
                ),
            )

            conn.executemany(
                """
                INSERT INTO servicos (
                    empresa_id,
                    nome,
                    valor,
                    duracao,
                    ativo
                )
                VALUES (?, ?, ?, ?, 1)
                """,
                [
                    (
                        empresa_id,
                        nome_servico,
                        valor,
                        duracao,
                    )
                    for nome_servico, valor, duracao
                    in config["servicos"]
                ],
            )

            conn.executemany(
                """
                INSERT INTO funcionarios (
                    empresa_id,
                    nome,
                    cargo,
                    ativo
                )
                VALUES (?, ?, ?, 1)
                """,
                [
                    (
                        empresa_id,
                        nome_funcionario,
                        cargo,
                    )
                    for nome_funcionario, cargo
                    in config["funcionarios"]
                ],
            )

            conn.commit()

        except sqlite3.Error as erro:
            conn.rollback()
            print(
                "Erro ao criar empresa:",
                erro,
            )

            flash(
                "Não foi possível criar a empresa.",
                "erro",
            )

            return redirect(url_for("master_nova_empresa"))

        finally:
            conn.close()

        flash(
            (
                f"{config['nome']} criada com sucesso. "
                f"Link: /{slug}"
            ),
            "sucesso",
        )

        return redirect(
            url_for(
                "master_empresa_criada",
                empresa_id=empresa_id,
            )
        )

    conn = get_connection()
    planos = conn.execute("SELECT * FROM planos WHERE ativo = 1 ORDER BY valor, nome").fetchall()
    conn.close()
    return render_template(
        "master/empresa_nova.html",
        segmentos=SEGMENTOS,
        planos=planos,
    )


@app.route("/master/empresas/<int:empresa_id>/criada")
@master_login_required
def master_empresa_criada(empresa_id):
    conn = get_connection()

    empresa = conn.execute(
        """
        SELECT
            e.*,
            u.usuario,
            u.senha
        FROM empresas e
        LEFT JOIN usuarios u
            ON u.empresa_id = e.id
        WHERE e.id = ?
        """,
        (empresa_id,),
    ).fetchone()

    conn.close()

    if not empresa:
        flash("Empresa não encontrada.", "erro")
        return redirect(url_for("master_empresas"))

    return render_template(
        "master/empresa_criada.html",
        empresa=empresa,
    )


@app.route(
    "/master/empresas/<int:empresa_id>/alternar",
    methods=["POST"],
)
@master_login_required
def master_alternar_empresa(empresa_id):
    conn = get_connection()

    empresa = conn.execute(
        "SELECT * FROM empresas WHERE id = ?",
        (empresa_id,),
    ).fetchone()

    if empresa:
        novo_bloqueio_manual = 0 if empresa["bloqueio_manual"] else 1
        novo_status = 0 if (novo_bloqueio_manual or empresa["bloqueado_financeiro"]) else 1

        conn.execute(
            """
            UPDATE empresas
            SET ativo = ?, bloqueio_manual = ?
            WHERE id = ?
            """,
            (novo_status, novo_bloqueio_manual, empresa_id),
        )

        conn.commit()

    conn.close()

    return redirect(url_for("master_empresas"))


@app.route(
    "/master/empresas/<int:empresa_id>/editar",
    methods=["GET", "POST"],
)
@master_login_required
def master_editar_empresa(empresa_id):
    conn = get_connection()

    empresa = conn.execute(
        """
        SELECT
            e.*,
            u.id AS usuario_id,
            u.usuario
        FROM empresas e
        LEFT JOIN usuarios u
            ON u.empresa_id = e.id
        WHERE e.id = ?
        """,
        (empresa_id,),
    ).fetchone()

    if not empresa:
        conn.close()
        flash("Empresa não encontrada.", "erro")
        return redirect(url_for("master_empresas"))

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        slug = request.form.get("slug", "").strip().lower()
        telefone = request.form.get("telefone", "").strip()
        instagram = request.form.get("instagram", "").strip()
        endereco = request.form.get("endereco", "").strip()
        maps_url = request.form.get("maps_url", "").strip()
        horario_texto = request.form.get(
            "horario_texto",
            "",
        ).strip()
        descricao = request.form.get("descricao", "").strip()
        segmento = request.form.get(
            "segmento",
            empresa["segmento"] or "barbearia",
        ).strip().lower()
        usuario = request.form.get("usuario", "").strip()
        nova_senha = request.form.get(
            "nova_senha",
            "",
        ).strip()
        aplicar_paleta = request.form.get(
            "aplicar_paleta"
        ) == "1"
        plano_id = request.form.get("plano_id", "").strip()
        plano_registro = conn.execute("SELECT * FROM planos WHERE id = ?", (plano_id,)).fetchone() if plano_id else None
        plano = plano_registro["nome"] if plano_registro else (empresa["plano"] or "Essencial")
        try:
            mensalidade = float(request.form.get("mensalidade", empresa["mensalidade"] or 0).replace(",", "."))
        except (ValueError, AttributeError):
            mensalidade = float(empresa["mensalidade"] or 0)
        try:
            dia_vencimento = int(request.form.get("dia_vencimento", empresa["dia_vencimento"] or 10))
        except ValueError:
            dia_vencimento = int(empresa["dia_vencimento"] or 10)
        status_pagamento = empresa["status_pagamento"] or "em_dia"
        proximo_vencimento = request.form.get("proximo_vencimento", "").strip() or None
        ultimo_pagamento = request.form.get("ultimo_pagamento", "").strip() or None
        try:
            tolerancia_dias = max(0, int(request.form.get("tolerancia_dias", empresa["tolerancia_dias"] or 5)))
            bloquear_apos_dias = max(tolerancia_dias + 1, int(request.form.get("bloquear_apos_dias", empresa["bloquear_apos_dias"] or 15)))
        except ValueError:
            tolerancia_dias, bloquear_apos_dias = 5, 15

        if segmento not in SEGMENTOS:
            conn.close()
            flash("Segmento inválido.", "erro")
            return redirect(
                url_for(
                    "master_editar_empresa",
                    empresa_id=empresa_id,
                )
            )

        if not all([nome, slug, usuario]):
            conn.close()
            flash(
                "Nome, link e usuário são obrigatórios.",
                "erro",
            )
            return redirect(
                url_for(
                    "master_editar_empresa",
                    empresa_id=empresa_id,
                )
            )

        slug = "-".join(slug.split())

        slug_existente = conn.execute(
            """
            SELECT id
            FROM empresas
            WHERE slug = ?
              AND id != ?
            """,
            (slug, empresa_id),
        ).fetchone()

        usuario_existente = conn.execute(
            """
            SELECT id
            FROM usuarios
            WHERE usuario = ?
              AND empresa_id != ?
            """,
            (usuario, empresa_id),
        ).fetchone()

        if slug_existente:
            conn.close()
            flash(
                "Este link já está sendo utilizado.",
                "erro",
            )
            return redirect(
                url_for(
                    "master_editar_empresa",
                    empresa_id=empresa_id,
                )
            )

        if usuario_existente:
            conn.close()
            flash(
                "Este usuário já está sendo utilizado.",
                "erro",
            )
            return redirect(
                url_for(
                    "master_editar_empresa",
                    empresa_id=empresa_id,
                )
            )

        config = obter_config_segmento(segmento)

        if aplicar_paleta:
            cor_principal = config["cor_principal"]
            cor_secundaria = config["cor_secundaria"]
            cor_botao = config["cor_botao"]
            cor_sidebar = config["cor_sidebar"]
        else:
            cor_principal = request.form.get(
                "cor_principal",
                empresa["cor_principal"],
            ).strip()
            cor_secundaria = request.form.get(
                "cor_secundaria",
                empresa["cor_secundaria"],
            ).strip()
            cor_botao = request.form.get(
                "cor_botao",
                empresa["cor_botao"],
            ).strip()
            cor_sidebar = request.form.get(
                "cor_sidebar",
                empresa["cor_sidebar"],
            ).strip()

        try:
            conn.execute(
                """
                UPDATE empresas
                SET
                    nome = ?,
                    slug = ?,
                    telefone = ?,
                    instagram = ?,
                    endereco = ?,
                    maps_url = ?,
                    horario_texto = ?,
                    descricao = ?,
                    segmento = ?,
                    template_admin = ?,
                    template_cliente = ?,
                    cor_principal = ?,
                    cor_secundaria = ?,
                    cor_botao = ?,
                    cor_sidebar = ?,
                    plano = ?,
                    plano_id = ?,
                    mensalidade = ?,
                    dia_vencimento = ?,
                    status_pagamento = ?,
                    proximo_vencimento = ?,
                    ultimo_pagamento = ?,
                    tolerancia_dias = ?,
                    bloquear_apos_dias = ?
                WHERE id = ?
                """,
                (
                    nome,
                    slug,
                    telefone,
                    instagram,
                    endereco,
                    maps_url,
                    horario_texto,
                    descricao,
                    segmento,
                    config["template_admin"],
                    config["template_cliente"],
                    cor_principal,
                    cor_secundaria,
                    cor_botao,
                    cor_sidebar,
                    plano,
                    plano_registro["id"] if plano_registro else empresa["plano_id"],
                    mensalidade,
                    dia_vencimento,
                    status_pagamento,
                    proximo_vencimento,
                    ultimo_pagamento,
                    tolerancia_dias,
                    bloquear_apos_dias,
                    empresa_id,
                ),
            )

            if empresa["usuario_id"]:
                conn.execute(
                    """
                    UPDATE usuarios
                    SET usuario = ?
                    WHERE id = ?
                    """,
                    (
                        usuario,
                        empresa["usuario_id"],
                    ),
                )

                if nova_senha:
                    conn.execute(
                        """
                        UPDATE usuarios
                        SET senha = ?
                        WHERE id = ?
                        """,
                        (
                            nova_senha,
                            empresa["usuario_id"],
                        ),
                    )
            else:
                conn.execute(
                    """
                    INSERT INTO usuarios (
                        empresa_id,
                        usuario,
                        senha
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        empresa_id,
                        usuario,
                        nova_senha or "trocar123",
                    ),
                )

            conn.commit()

        except sqlite3.Error as erro:
            conn.rollback()
            print("Erro ao editar empresa:", erro)
            conn.close()

            flash(
                "Não foi possível salvar as alterações.",
                "erro",
            )
            return redirect(
                url_for(
                    "master_editar_empresa",
                    empresa_id=empresa_id,
                )
            )

        conn.close()

        flash(
            "Empresa atualizada com sucesso.",
            "sucesso",
        )
        return redirect(url_for("master_empresas"))

    conn.close()

    conn = get_connection()
    planos = conn.execute("SELECT * FROM planos ORDER BY ativo DESC, valor, nome").fetchall()
    conn.close()
    return render_template(
        "master/empresa_editar.html",
        empresa=empresa,
        segmentos=SEGMENTOS,
        planos=planos,
    )


@app.route(
    "/master/empresas/<int:empresa_id>/excluir",
    methods=["POST"],
)
@master_login_required
def master_excluir_empresa(empresa_id):
    confirmacao = request.form.get(
        "confirmacao",
        "",
    ).strip()

    conn = get_connection()

    empresa = conn.execute(
        """
        SELECT id, nome, slug
        FROM empresas
        WHERE id = ?
        """,
        (empresa_id,),
    ).fetchone()

    if not empresa:
        conn.close()
        flash("Empresa não encontrada.", "erro")
        return redirect(url_for("master_empresas"))

    if confirmacao != empresa["nome"]:
        conn.close()
        flash(
            "A confirmação não corresponde ao nome da empresa.",
            "erro",
        )
        return redirect(
            url_for(
                "master_editar_empresa",
                empresa_id=empresa_id,
            )
        )

    try:
        conn.execute(
            """
            DELETE FROM fidelidade_movimentos
            WHERE empresa_id = ?
            """,
            (empresa_id,),
        )

        conn.execute(
            """
            DELETE FROM agendamento_servicos
            WHERE agendamento_id IN (
                SELECT id
                FROM agendamentos
                WHERE empresa_id = ?
            )
            """,
            (empresa_id,),
        )

        conn.execute(
            """
            DELETE FROM agendamentos
            WHERE empresa_id = ?
            """,
            (empresa_id,),
        )

        conn.execute(
            """
            DELETE FROM clientes
            WHERE empresa_id = ?
            """,
            (empresa_id,),
        )

        conn.execute(
            """
            DELETE FROM funcionarios
            WHERE empresa_id = ?
            """,
            (empresa_id,),
        )

        conn.execute(
            """
            DELETE FROM servicos
            WHERE empresa_id = ?
            """,
            (empresa_id,),
        )

        conn.execute(
            """
            DELETE FROM usuarios
            WHERE empresa_id = ?
            """,
            (empresa_id,),
        )

        conn.execute(
            """
            DELETE FROM empresas
            WHERE id = ?
            """,
            (empresa_id,),
        )

        conn.commit()

    except sqlite3.Error as erro:
        conn.rollback()
        print("Erro ao excluir empresa:", erro)
        conn.close()

        flash(
            "Não foi possível excluir a empresa.",
            "erro",
        )
        return redirect(
            url_for(
                "master_editar_empresa",
                empresa_id=empresa_id,
            )
        )

    conn.close()

    flash(
        f"Empresa {empresa['nome']} removida definitivamente.",
        "sucesso",
    )
    return redirect(url_for("master_empresas"))



@app.route("/master/planos")
@master_login_required
def master_planos():
    conn = get_connection()
    planos = conn.execute("SELECT * FROM planos ORDER BY ativo DESC, valor, nome").fetchall()
    recursos_por_plano = {}
    for plano in planos:
        recursos_por_plano[plano["id"]] = conn.execute("""
            SELECT r.* FROM recursos r JOIN plano_recursos pr ON pr.recurso_id=r.id
            WHERE pr.plano_id=? ORDER BY r.nome
        """, (plano["id"],)).fetchall()
    conn.close()
    return render_template("master/planos.html", planos=planos, recursos_por_plano=recursos_por_plano)


def _inteiro_ou_nulo(valor):
    try:
        return int(valor) if str(valor or "").strip() else None
    except ValueError:
        return None


@app.route("/master/planos/novo", methods=["GET", "POST"])
@master_login_required
def master_novo_plano():
    conn = get_connection()
    recursos = conn.execute("SELECT * FROM recursos WHERE ativo=1 ORDER BY nome").fetchall()
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        if not nome:
            conn.close(); flash("Informe o nome do plano.", "erro"); return redirect(url_for("master_novo_plano"))
        try: valor = float(request.form.get("valor", "0").replace(",", ".") or 0)
        except ValueError: valor = 0
        try:
            cursor = conn.execute("""INSERT INTO planos (nome,descricao,valor,limite_profissionais,limite_usuarios,limite_agendamentos,ativo) VALUES (?,?,?,?,?,?,?)""",
                (nome,request.form.get("descricao","").strip(),valor,_inteiro_ou_nulo(request.form.get("limite_profissionais")),_inteiro_ou_nulo(request.form.get("limite_usuarios")),_inteiro_ou_nulo(request.form.get("limite_agendamentos")),1 if request.form.get("ativo") else 0))
            plano_id=cursor.lastrowid
            for recurso_id in request.form.getlist("recursos"):
                conn.execute("INSERT OR IGNORE INTO plano_recursos (plano_id,recurso_id) VALUES (?,?)",(plano_id,recurso_id))
            conn.commit(); conn.close(); flash("Plano criado com sucesso.","sucesso"); return redirect(url_for("master_planos"))
        except sqlite3.IntegrityError:
            conn.rollback(); conn.close(); flash("Já existe um plano com este nome.","erro"); return redirect(url_for("master_novo_plano"))
    conn.close()
    return render_template("master/plano_form.html", plano=None, recursos=recursos, selecionados=set())


@app.route("/master/planos/<int:plano_id>/editar", methods=["GET", "POST"])
@master_login_required
def master_editar_plano(plano_id):
    conn=get_connection(); plano=conn.execute("SELECT * FROM planos WHERE id=?",(plano_id,)).fetchone()
    if not plano:
        conn.close(); flash("Plano não encontrado.","erro"); return redirect(url_for("master_planos"))
    recursos=conn.execute("SELECT * FROM recursos WHERE ativo=1 ORDER BY nome").fetchall()
    if request.method=="POST":
        nome=request.form.get("nome","").strip()
        try: valor=float(request.form.get("valor","0").replace(",",".") or 0)
        except ValueError: valor=0
        try:
            conn.execute("""UPDATE planos SET nome=?,descricao=?,valor=?,limite_profissionais=?,limite_usuarios=?,limite_agendamentos=?,ativo=?,atualizado_em=CURRENT_TIMESTAMP WHERE id=?""",
                (nome,request.form.get("descricao","").strip(),valor,_inteiro_ou_nulo(request.form.get("limite_profissionais")),_inteiro_ou_nulo(request.form.get("limite_usuarios")),_inteiro_ou_nulo(request.form.get("limite_agendamentos")),1 if request.form.get("ativo") else 0,plano_id))
            conn.execute("DELETE FROM plano_recursos WHERE plano_id=?",(plano_id,))
            for recurso_id in request.form.getlist("recursos"):
                conn.execute("INSERT OR IGNORE INTO plano_recursos (plano_id,recurso_id) VALUES (?,?)",(plano_id,recurso_id))
            conn.execute("UPDATE empresas SET plano=?, mensalidade=CASE WHEN mensalidade<=0 THEN ? ELSE mensalidade END WHERE plano_id=?",(nome,valor,plano_id))
            conn.commit(); conn.close(); flash("Plano atualizado com sucesso.","sucesso"); return redirect(url_for("master_planos"))
        except sqlite3.IntegrityError:
            conn.rollback(); conn.close(); flash("Já existe outro plano com este nome.","erro"); return redirect(url_for("master_editar_plano",plano_id=plano_id))
    selecionados={item["recurso_id"] for item in conn.execute("SELECT recurso_id FROM plano_recursos WHERE plano_id=?",(plano_id,)).fetchall()}
    conn.close(); return render_template("master/plano_form.html",plano=plano,recursos=recursos,selecionados=selecionados)


@app.route("/master/financeiro")
@master_login_required
def master_financeiro():
    """Lista e filtra todas as mensalidades da plataforma."""
    from services.financeiro import atualizar_todas_empresas

    conn = get_connection()
    atualizar_todas_empresas(conn)

    busca = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip().lower()
    empresa_id = request.args.get("empresa_id", "").strip()
    plano_id = request.args.get("plano_id", "").strip()
    competencia = request.args.get("competencia", "").strip()

    condicoes = ["1=1"]
    params = []

    if busca:
        termo = f"%{busca}%"
        condicoes.append("(LOWER(e.nome) LIKE LOWER(?) OR LOWER(e.slug) LIKE LOWER(?))")
        params.extend([termo, termo])
    if status in ("aberta", "vencida", "paga", "cancelada"):
        condicoes.append("c.status=?")
        params.append(status)
    if empresa_id.isdigit():
        condicoes.append("c.empresa_id=?")
        params.append(int(empresa_id))
    if plano_id.isdigit():
        condicoes.append("e.plano_id=?")
        params.append(int(plano_id))
    if competencia:
        condicoes.append("c.competencia=?")
        params.append(competencia)

    where_sql = " AND ".join(condicoes)

    cobrancas = conn.execute(
        f"""
        SELECT
            c.*,
            e.nome AS empresa_nome,
            e.slug,
            e.status_pagamento,
            e.dias_atraso,
            e.plano_id,
            COALESCE(p.nome, e.plano, 'Sem plano') AS plano_nome
        FROM cobrancas c
        JOIN empresas e ON e.id = c.empresa_id
        LEFT JOIN planos p ON p.id = e.plano_id
        WHERE {where_sql}
        ORDER BY c.competencia DESC, c.vencimento DESC, e.nome COLLATE NOCASE
        """,
        tuple(params),
    ).fetchall()

    resumo = conn.execute(
        f"""
        SELECT
            COUNT(*) AS total,
            COALESCE(SUM(CASE WHEN c.status='aberta' THEN 1 ELSE 0 END), 0) AS abertas,
            COALESCE(SUM(CASE WHEN c.status='paga' THEN 1 ELSE 0 END), 0) AS pagas,
            COALESCE(SUM(CASE WHEN c.status='vencida' THEN 1 ELSE 0 END), 0) AS vencidas,
            COALESCE(SUM(CASE WHEN c.status='cancelada' THEN 1 ELSE 0 END), 0) AS canceladas,
            COALESCE(SUM(CASE WHEN c.status!='cancelada' THEN COALESCE(c.valor_final, c.valor) ELSE 0 END), 0) AS valor_total,
            COALESCE(SUM(CASE WHEN c.status='paga' THEN COALESCE(c.valor_final, c.valor) ELSE 0 END), 0) AS valor_pago,
            COALESCE(SUM(CASE WHEN c.status IN ('aberta','vencida') THEN COALESCE(c.valor_final, c.valor) ELSE 0 END), 0) AS valor_pendente
        FROM cobrancas c
        JOIN empresas e ON e.id = c.empresa_id
        LEFT JOIN planos p ON p.id = e.plano_id
        WHERE {where_sql}
        """,
        tuple(params),
    ).fetchone()

    pagamentos = conn.execute(
        """
        SELECT p.*, e.nome AS empresa_nome, c.competencia
        FROM pagamentos p
        JOIN empresas e ON e.id = p.empresa_id
        JOIN cobrancas c ON c.id = p.cobranca_id
        ORDER BY p.data_pagamento DESC, p.id DESC
        LIMIT 150
        """
    ).fetchall()

    empresas = conn.execute(
        "SELECT id, nome FROM empresas ORDER BY nome COLLATE NOCASE"
    ).fetchall()
    planos = conn.execute(
        "SELECT id, nome FROM planos ORDER BY nome COLLATE NOCASE"
    ).fetchall()
    conn.close()

    return render_template(
        "master/financeiro.html",
        cobrancas=cobrancas,
        pagamentos=pagamentos,
        resumo=resumo,
        empresas=empresas,
        planos=planos,
        busca=busca,
        status_filtro=status,
        empresa_filtro=empresa_id,
        plano_filtro=plano_id,
        competencia_filtro=competencia,
    )


@app.route("/master/empresas/<int:empresa_id>/financeiro")
@master_login_required
def master_empresa_financeiro(empresa_id):
    from services.financeiro import atualizar_empresa_financeiro
    conn=get_connection(); atualizar_empresa_financeiro(conn,empresa_id); conn.commit()
    empresa=conn.execute("SELECT * FROM empresas WHERE id=?",(empresa_id,)).fetchone()
    if not empresa:
        conn.close(); flash("Empresa não encontrada.","erro"); return redirect(url_for("master_empresas"))
    cobrancas=conn.execute("SELECT * FROM cobrancas WHERE empresa_id=? ORDER BY competencia DESC",(empresa_id,)).fetchall()
    pagamentos=conn.execute("""SELECT p.*,c.competencia FROM pagamentos p JOIN cobrancas c ON c.id=p.cobranca_id
        WHERE p.empresa_id=? ORDER BY p.data_pagamento DESC,p.id DESC""",(empresa_id,)).fetchall()
    logs=conn.execute("SELECT * FROM logs_financeiros WHERE empresa_id=? ORDER BY criado_em DESC,id DESC LIMIT 100",(empresa_id,)).fetchall()
    conn.close(); return render_template("master/empresa_financeiro.html",empresa=empresa,cobrancas=cobrancas,pagamentos=pagamentos,logs=logs)


@app.route("/master/cobrancas/<int:cobranca_id>/pagar", methods=["POST"])
@master_login_required
def master_registrar_pagamento(cobranca_id):
    from services.financeiro import registrar_pagamento
    conn=get_connection()
    try:
        valor=request.form.get("valor_final") or request.form.get("valor")
        desconto=request.form.get("desconto", 0)
        acrescimo=request.form.get("acrescimo", 0)
        data_pagamento=request.form.get("data_pagamento") or date.today().isoformat()
        forma=request.form.get("forma_pagamento","Pix").strip() or "Pix"
        observacoes=request.form.get("observacoes","").strip()
        pagamento_id=registrar_pagamento(
            conn, cobranca_id, valor, data_pagamento, forma, observacoes,
            desconto=desconto, acrescimo=acrescimo,
        )
        conn.commit(); flash("Pagamento registrado, próxima mensalidade gerada e acesso atualizado.","sucesso")
    except (ValueError,sqlite3.Error) as erro:
        conn.rollback(); conn.close(); flash(str(erro),"erro"); return redirect(request.referrer or url_for("master_financeiro"))
    conn.close(); return redirect(url_for("master_recibo",pagamento_id=pagamento_id))


@app.route("/master/pagamentos/<int:pagamento_id>/estornar",methods=["POST"])
@master_login_required
def master_estornar_pagamento(pagamento_id):
    from services.financeiro import estornar_pagamento
    motivo=request.form.get("motivo","").strip()
    if not motivo:
        flash("Informe o motivo do estorno.","erro"); return redirect(request.referrer or url_for("master_financeiro"))
    conn=get_connection()
    try:
        estornar_pagamento(conn,pagamento_id,motivo); conn.commit(); flash("Pagamento estornado e cobrança reaberta.","sucesso")
    except (ValueError,sqlite3.Error) as erro:
        conn.rollback(); flash(str(erro),"erro")
    conn.close(); return redirect(request.referrer or url_for("master_financeiro"))


@app.route("/master/pagamentos/<int:pagamento_id>/recibo")
@master_login_required
def master_recibo(pagamento_id):
    if canvas is None or A4 is None:
        flash("Para emitir o recibo em PDF, instale: py -m pip install reportlab","erro")
        return redirect(url_for("master_financeiro"))
    conn=get_connection(); item=conn.execute("""SELECT p.*,e.nome empresa_nome,e.telefone,e.slug,c.competencia,c.descricao,c.vencimento
        FROM pagamentos p JOIN empresas e ON e.id=p.empresa_id JOIN cobrancas c ON c.id=p.cobranca_id WHERE p.id=?""",(pagamento_id,)).fetchone(); conn.close()
    if not item:
        flash("Recibo não encontrado.","erro"); return redirect(url_for("master_financeiro"))
    buffer=BytesIO(); pdf=canvas.Canvas(buffer,pagesize=A4); w,h=A4
    pdf.setTitle(f"Recibo {item['recibo_numero']}"); pdf.setFont("Helvetica-Bold",20); pdf.drawString(55,h-70,"BYTECH")
    pdf.setFont("Helvetica",11); pdf.drawString(55,h-90,"Recibo de pagamento - Bytech Agenda"); pdf.line(55,h-105,w-55,h-105); y=h-145
    moeda=lambda v: f"R$ {float(v or 0):,.2f}".replace(',', 'X').replace('.', ',').replace('X','.')
    linhas=[("Recibo",item['recibo_numero']),("Empresa",item['empresa_nome']),("Competência",item['competencia']),("Vencimento",item['vencimento']),("Pagamento",item['data_pagamento']),("Forma",item['forma_pagamento'])]
    if float(item['desconto'] or 0) or float(item['acrescimo'] or 0):
        linhas.extend([("Valor original",moeda(item['valor_original'] or item['valor'])),("Desconto",moeda(item['desconto'])),("Acréscimo",moeda(item['acrescimo']))])
    linhas.append(("Valor pago",moeda(item['valor_final'] or item['valor'])))
    for titulo,valor in linhas:
        pdf.setFont("Helvetica-Bold",10); pdf.drawString(55,y,titulo+":"); pdf.setFont("Helvetica",11); pdf.drawString(150,y,str(valor)); y-=28
    if item['observacoes']:
        pdf.setFont("Helvetica-Bold",10); pdf.drawString(55,y,"Observações:"); pdf.setFont("Helvetica",10); pdf.drawString(150,y,str(item['observacoes'])[:75]); y-=35
    if item['estornado']:
        pdf.setFont("Helvetica-Bold",12); pdf.drawString(55,y,"PAGAMENTO ESTORNADO"); y-=25
    pdf.line(55,y,w-55,y); y-=35; pdf.setFont("Helvetica",9); pdf.drawString(55,y,"Pagamento registrado no painel Master do Bytech Agenda."); pdf.drawRightString(w-55,y,datetime.now().strftime("Emitido em %d/%m/%Y às %H:%M")); pdf.save(); buffer.seek(0)
    from flask import send_file
    return send_file(buffer,mimetype="application/pdf",as_attachment=True,download_name=f"recibo-{item['recibo_numero']}.pdf")


@app.route('/master/financeiro/dashboard')
@master_login_required
def master_financeiro_dashboard():
    from services.financeiro import atualizar_todas_empresas
    conn=get_connection(); atualizar_todas_empresas(conn); conn.commit()
    kpis=conn.execute("""
      SELECT
       COALESCE(SUM(CASE WHEN status='paga' AND competencia=strftime('%Y-%m','now','localtime') THEN valor_final ELSE 0 END),0) recebido_mes,
       COALESCE(SUM(CASE WHEN status IN ('aberta','vencida') THEN valor_final ELSE 0 END),0) a_receber,
       COALESCE(SUM(CASE WHEN status='vencida' THEN valor_final ELSE 0 END),0) vencido,
       COALESCE(SUM(CASE WHEN status='paga' THEN valor_final ELSE 0 END),0) recebido_total,
       COALESCE(SUM(CASE WHEN status='paga' THEN 1 ELSE 0 END),0) qtd_pagas
      FROM cobrancas
    """).fetchone()
    inad=conn.execute("SELECT COUNT(*) qtd, COALESCE(SUM(mensalidade),0) valor FROM empresas WHERE status_pagamento='inadimplente'").fetchone()
    historico=conn.execute("""
      WITH RECURSIVE meses(n, competencia) AS (
       SELECT 5, strftime('%Y-%m','now','localtime','-5 months')
       UNION ALL SELECT n-1, strftime('%Y-%m','now','localtime', printf('-%d months',n-1)) FROM meses WHERE n>0)
      SELECT competencia,
       COALESCE((SELECT SUM(valor_final) FROM cobrancas c WHERE c.competencia=meses.competencia),0) previsto,
       COALESCE((SELECT SUM(valor_final) FROM pagamentos p WHERE p.estornado=0 AND substr(p.data_pagamento,1,7)=meses.competencia),0) recebido
      FROM meses ORDER BY competencia
    """).fetchall()
    ultimos=conn.execute("""SELECT p.*,e.nome empresa_nome,c.competencia FROM pagamentos p JOIN empresas e ON e.id=p.empresa_id JOIN cobrancas c ON c.id=p.cobranca_id ORDER BY p.data_pagamento DESC,p.id DESC LIMIT 8""").fetchall()
    proximos=conn.execute("""SELECT c.*,e.nome empresa_nome FROM cobrancas c JOIN empresas e ON e.id=c.empresa_id WHERE c.status='aberta' ORDER BY c.vencimento LIMIT 8""").fetchall()
    por_plano=conn.execute("""SELECT COALESCE(pl.nome,e.plano,'Sem plano') plano,COUNT(*) empresas,COALESCE(SUM(e.mensalidade),0) receita FROM empresas e LEFT JOIN planos pl ON pl.id=e.plano_id GROUP BY COALESCE(pl.nome,e.plano,'Sem plano') ORDER BY receita DESC""").fetchall()
    ticket=(float(kpis['recebido_total'] or 0)/int(kpis['qtd_pagas'] or 1)) if kpis['qtd_pagas'] else 0
    conn.close()
    return render_template('master/financeiro_dashboard.html',kpis=kpis,inad=inad,historico=historico,ultimos=ultimos,proximos=proximos,por_plano=por_plano,ticket=ticket)

@app.route('/master/financeiro/inadimplentes')
@master_login_required
def master_inadimplentes():
    from services.financeiro import atualizar_todas_empresas
    conn=get_connection(); atualizar_todas_empresas(conn); conn.commit()
    itens=conn.execute("""SELECT e.*,COALESCE(SUM(CASE WHEN c.status='vencida' THEN c.valor_final ELSE 0 END),0) valor_devido,COUNT(CASE WHEN c.status='vencida' THEN 1 END) cobrancas_vencidas FROM empresas e LEFT JOIN cobrancas c ON c.empresa_id=e.id WHERE e.status_pagamento='inadimplente' GROUP BY e.id ORDER BY e.dias_atraso DESC,e.nome""").fetchall()
    total=sum(float(x['valor_devido'] or 0) for x in itens)
    conn.close(); return render_template('master/inadimplentes.html',itens=itens,total=total)

@app.route('/master/financeiro/inadimplentes/<int:empresa_id>/bloqueio',methods=['POST'])
@master_login_required
def master_inadimplente_bloqueio(empresa_id):
    conn=get_connection(); empresa=conn.execute('SELECT * FROM empresas WHERE id=?',(empresa_id,)).fetchone()
    if not empresa: conn.close(); flash('Empresa não encontrada.','erro'); return redirect(url_for('master_inadimplentes'))
    bloquear=1 if request.form.get('acao')=='bloquear' else 0
    conn.execute('UPDATE empresas SET bloqueio_manual=?, ativo=? WHERE id=?',(bloquear,0 if bloquear else (0 if empresa['bloqueado_financeiro'] else 1),empresa_id))
    conn.execute("INSERT INTO logs_financeiros (empresa_id,acao,descricao) VALUES (?,?,?)",(empresa_id,'bloqueio_manual','Acesso bloqueado manualmente' if bloquear else 'Bloqueio manual removido'))
    conn.commit(); conn.close(); flash('Acesso atualizado com sucesso.','sucesso'); return redirect(url_for('master_inadimplentes'))

@app.route('/master/financeiro/configuracoes',methods=['GET','POST'])
@master_login_required
def master_configuracoes_financeiras():
    conn=get_connection()
    cfg=conn.execute('SELECT * FROM configuracoes_financeiras WHERE id=1').fetchone()
    if request.method=='POST':
        try:
            vals=(max(1,min(28,int(request.form.get('dia_vencimento_padrao',10)))),max(0,int(request.form.get('tolerancia_dias_padrao',5))),max(0,int(request.form.get('bloquear_apos_dias_padrao',15))),max(0,float(request.form.get('multa_percentual','0').replace(',','.'))),max(0,float(request.form.get('juros_mensal_percentual','0').replace(',','.'))),max(0,float(request.form.get('desconto_antecipacao_percentual','0').replace(',','.'))),request.form.get('forma_pagamento_padrao','Pix').strip() or 'Pix',request.form.get('mensagem_cobranca','').strip())
            conn.execute("""UPDATE configuracoes_financeiras SET dia_vencimento_padrao=?,tolerancia_dias_padrao=?,bloquear_apos_dias_padrao=?,multa_percentual=?,juros_mensal_percentual=?,desconto_antecipacao_percentual=?,forma_pagamento_padrao=?,mensagem_cobranca=?,atualizado_em=CURRENT_TIMESTAMP WHERE id=1""",vals)
            if request.form.get('aplicar_empresas'):
                conn.execute('UPDATE empresas SET dia_vencimento=?,tolerancia_dias=?,bloquear_apos_dias=?',(vals[0],vals[1],vals[2]))
            conn.execute("INSERT INTO logs_financeiros (acao,descricao) VALUES ('configuracoes','Configurações financeiras atualizadas')")
            conn.commit(); flash('Configurações salvas com sucesso.','sucesso')
        except ValueError:
            conn.rollback(); flash('Revise os valores informados.','erro')
        conn.close(); return redirect(url_for('master_configuracoes_financeiras'))
    conn.close(); return render_template('master/configuracoes_financeiras.html',cfg=cfg)
