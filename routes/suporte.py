"""Rotas do módulo suporte: formulário de ajuda do cliente e a caixa de
tickets correspondente no painel master. Não depende de e-mail/SMTP —
fica tudo registrado no próprio banco, visível para a Bytech no painel
master."""

from core import *  # noqa: F401,F403


@app.context_processor
def contexto_suporte_master():
    if not session.get("master_id"):
        return {}
    conn = get_connection()
    total = conn.execute(
        "SELECT COUNT(*) total FROM suporte_mensagens WHERE status='aberto'"
    ).fetchone()["total"]
    conn.close()
    return {"contagem_suporte_aberto": total}


@app.route("/admin/suporte", methods=["GET", "POST"])
@login_required
def admin_suporte():
    empresa_id = session["empresa_id"]
    conn = get_connection()

    if request.method == "POST":
        assunto = request.form.get("assunto", "").strip()
        mensagem = request.form.get("mensagem", "").strip()
        telefone_contato = request.form.get("telefone_contato", "").strip()

        if not assunto or not mensagem:
            conn.close()
            flash("Preencha o assunto e a mensagem.", "erro")
            return redirect(url_for("admin_suporte"))

        conn.execute(
            """
            INSERT INTO suporte_mensagens
                (empresa_id, usuario_id, nome_contato, telefone_contato, assunto, mensagem)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                empresa_id,
                session.get("usuario_id"),
                session.get("nome_usuario"),
                telefone_contato,
                assunto,
                mensagem,
            ),
        )
        conn.commit()
        conn.close()
        flash("Mensagem enviada! A Bytech vai te responder por aqui em breve.", "sucesso")
        return redirect(url_for("admin_suporte"))

    mensagens = conn.execute(
        """
        SELECT * FROM suporte_mensagens
        WHERE empresa_id = ?
        ORDER BY criado_em DESC
        """,
        (empresa_id,),
    ).fetchall()
    conn.close()

    return render_template("admin/suporte.html", mensagens=mensagens)


@app.route("/master/suporte")
@master_login_required
def master_suporte():
    conn = get_connection()
    filtro = request.args.get("status", "aberto")

    condicao = ""
    parametros = []
    if filtro in ("aberto", "respondido"):
        condicao = "WHERE s.status = ?"
        parametros.append(filtro)

    mensagens = conn.execute(
        f"""
        SELECT s.*, e.nome AS empresa_nome, e.slug AS empresa_slug
        FROM suporte_mensagens s
        JOIN empresas e ON e.id = s.empresa_id
        {condicao}
        ORDER BY s.criado_em DESC
        """,
        tuple(parametros),
    ).fetchall()

    total_abertos = conn.execute(
        "SELECT COUNT(*) total FROM suporte_mensagens WHERE status='aberto'"
    ).fetchone()["total"]
    conn.close()

    return render_template(
        "master/suporte.html",
        mensagens=mensagens,
        filtro=filtro,
        total_abertos=total_abertos,
    )


@app.route("/master/suporte/<int:mensagem_id>/responder", methods=["POST"])
@master_login_required
def master_suporte_responder(mensagem_id):
    resposta = request.form.get("resposta", "").strip()
    if not resposta:
        flash("Escreva uma resposta antes de enviar.", "erro")
        return redirect(url_for("master_suporte"))

    conn = get_connection()
    conn.execute(
        """
        UPDATE suporte_mensagens
        SET resposta = ?, status = 'respondido', respondido_em = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (resposta, mensagem_id),
    )
    conn.commit()
    conn.close()

    flash("Resposta registrada.", "sucesso")
    return redirect(url_for("master_suporte"))
