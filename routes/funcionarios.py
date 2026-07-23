"""Rotas do módulo funcionarios."""

from core import *  # noqa: F401,F403

@app.route("/admin/funcionarios", methods=["GET", "POST"])
@login_required
def admin_funcionarios():
    empresa_id = session["empresa_id"]
    conn = get_connection()

    if request.method == "POST":
        from services.recursos import limite_atingido
        limite_excedido, limite, _uso = limite_atingido(conn, empresa_id, "profissionais")
        if limite_excedido:
            conn.close()
            flash(
                f"O plano atual permite até {limite} profissionais ativos.",
                "erro",
            )
            return redirect(url_for("admin_funcionarios"))

        nome = request.form.get("nome", "").strip()
        empresa = conn.execute(
            "SELECT segmento FROM empresas WHERE id = ?",
            (empresa_id,),
        ).fetchone()

        ui_segmento = obter_ui_segmento(
            empresa["segmento"] if empresa else "barbearia"
        )

        cargo = request.form.get(
            "cargo",
            ui_segmento["cargo_padrao"],
        ).strip() or ui_segmento["cargo_padrao"]

        if nome:
            conn.execute(
                "INSERT INTO funcionarios (empresa_id, nome, cargo) VALUES (?, ?, ?)",
                (empresa_id, nome, cargo),
            )
            conn.commit()
            flash("Funcionário cadastrado.", "sucesso")

    funcionarios = conn.execute(
        "SELECT * FROM funcionarios WHERE empresa_id = ? ORDER BY nome",
        (empresa_id,),
    ).fetchall()
    conn.close()

    return render_template("admin/funcionarios.html", funcionarios=funcionarios)


@app.route("/admin/funcionarios/<int:funcionario_id>/editar", methods=["GET", "POST"])
@login_required
def editar_funcionario(funcionario_id):
    empresa_id = session["empresa_id"]
    conn = get_connection()
    funcionario = conn.execute(
        "SELECT * FROM funcionarios WHERE id = ? AND empresa_id = ?",
        (funcionario_id, empresa_id),
    ).fetchone()

    if not funcionario:
        conn.close()
        flash("Funcionário não encontrado.", "erro")
        return redirect(url_for("admin_funcionarios"))

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        empresa = conn.execute(
            "SELECT segmento FROM empresas WHERE id = ?",
            (empresa_id,),
        ).fetchone()

        ui_segmento = obter_ui_segmento(
            empresa["segmento"] if empresa else "barbearia"
        )

        cargo = request.form.get(
            "cargo",
            ui_segmento["cargo_padrao"],
        ).strip() or ui_segmento["cargo_padrao"]
        conn.execute(
            "UPDATE funcionarios SET nome = ?, cargo = ? WHERE id = ? AND empresa_id = ?",
            (nome, cargo, funcionario_id, empresa_id),
        )
        conn.commit()
        conn.close()
        flash("Funcionário atualizado.", "sucesso")
        return redirect(url_for("admin_funcionarios"))

    conn.close()
    return render_template("admin/funcionario_editar.html", funcionario=funcionario)


@app.route("/admin/funcionarios/<int:funcionario_id>/alternar", methods=["POST"])
@login_required
def alternar_funcionario(funcionario_id):
    empresa_id = session["empresa_id"]
    conn = get_connection()
    funcionario = conn.execute(
        "SELECT * FROM funcionarios WHERE id = ? AND empresa_id = ?",
        (funcionario_id, empresa_id),
    ).fetchone()

    if funcionario:
        novo_status = 0 if funcionario["ativo"] else 1
        conn.execute(
            "UPDATE funcionarios SET ativo = ? WHERE id = ?",
            (novo_status, funcionario_id),
        )
        conn.commit()

    conn.close()
    return redirect(url_for("admin_funcionarios"))


@app.route("/admin/funcionarios/<int:funcionario_id>/excluir", methods=["POST"])
@login_required
def excluir_funcionario(funcionario_id):
    empresa_id = session["empresa_id"]
    conn = get_connection()
    possui_agendamento = conn.execute(
        "SELECT id FROM agendamentos WHERE empresa_id = ? AND funcionario_id = ? LIMIT 1",
        (empresa_id, funcionario_id),
    ).fetchone()

    if possui_agendamento:
        conn.close()
        flash("Este funcionário possui agendamentos. Desative-o em vez de excluir.", "erro")
        return redirect(url_for("admin_funcionarios"))

    conn.execute(
        "DELETE FROM funcionarios WHERE id = ? AND empresa_id = ?",
        (funcionario_id, empresa_id),
    )
    conn.commit()
    conn.close()
    flash("Funcionário excluído.", "sucesso")
    return redirect(url_for("admin_funcionarios"))

