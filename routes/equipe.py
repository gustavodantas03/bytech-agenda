"""Rotas do módulo equipe: gestão dos usuários (logins) da empresa.

Só o proprietário pode acessar estas rotas (ver core.apenas_proprietario).
Isso evita que um colaborador crie outro usuário para si mesmo com mais
permissões do que deveria ter.
"""

from core import *  # noqa: F401,F403


def _permissoes_validas(valores):
    return [v for v in valores if v in PERMISSOES_DISPONIVEIS]


def _tem_outro_proprietario_ativo(conn, empresa_id, usuario_id):
    total = conn.execute(
        """
        SELECT COUNT(*) total FROM usuarios
        WHERE empresa_id = ? AND papel = 'proprietario' AND ativo = 1 AND id != ?
        """,
        (empresa_id, usuario_id),
    ).fetchone()["total"]
    return total > 0


@app.route("/admin/equipe")
@login_required
@apenas_proprietario
def admin_equipe():
    empresa_id = session["empresa_id"]
    conn = get_connection()

    from services.recursos import uso_do_plano
    uso = uso_do_plano(conn, empresa_id)

    linhas = conn.execute(
        """
        SELECT id, usuario, nome, papel, permissoes, ativo, criado_em
        FROM usuarios
        WHERE empresa_id = ?
        ORDER BY (papel = 'proprietario') DESC, ativo DESC, COALESCE(nome, usuario)
        """,
        (empresa_id,),
    ).fetchall()
    conn.close()

    membros = []
    for linha in linhas:
        item = dict(linha)
        try:
            perms = json.loads(item["permissoes"] or "[]")
        except (TypeError, ValueError):
            perms = []
        item["permissoes_rotulos"] = [PERMISSOES_DISPONIVEIS.get(p, p) for p in perms]
        membros.append(item)

    return render_template(
        "admin/equipe.html",
        membros=membros,
        uso=uso,
    )


@app.route("/admin/equipe/novo", methods=["GET", "POST"])
@login_required
@apenas_proprietario
def admin_equipe_novo():
    empresa_id = session["empresa_id"]
    conn = get_connection()

    from services.recursos import limite_atingido
    limite_excedido, limite, _uso = limite_atingido(conn, empresa_id, "usuarios")

    if request.method == "POST":
        if limite_excedido:
            conn.close()
            flash(
                f"Seu plano atual permite até {limite} usuário(s) ativo(s). "
                "Fale com a Bytech para aumentar esse limite.",
                "erro",
            )
            return redirect(url_for("admin_equipe"))

        nome = request.form.get("nome", "").strip()
        usuario = request.form.get("usuario", "").strip().lower()
        senha = request.form.get("senha", "").strip()
        papel = request.form.get("papel", "colaborador").strip()
        if papel not in ("proprietario", "colaborador"):
            papel = "colaborador"
        permissoes = _permissoes_validas(request.form.getlist("permissoes"))

        if not nome or not usuario or not senha:
            conn.close()
            flash("Preencha nome, usuário e senha.", "erro")
            return redirect(url_for("admin_equipe_novo"))

        if len(senha) < 6:
            conn.close()
            flash("A senha deve ter pelo menos 6 caracteres.", "erro")
            return redirect(url_for("admin_equipe_novo"))

        existente = conn.execute(
            "SELECT id FROM usuarios WHERE usuario = ?", (usuario,)
        ).fetchone()
        if existente:
            conn.close()
            flash(
                f'O nome de usuário "{usuario}" já está em uso. Escolha outro.',
                "erro",
            )
            return redirect(url_for("admin_equipe_novo"))

        conn.execute(
            """
            INSERT INTO usuarios (empresa_id, usuario, senha, nome, papel, permissoes, ativo)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            (
                empresa_id,
                usuario,
                gerar_hash_senha(senha),
                nome,
                papel,
                json.dumps(permissoes if papel == "colaborador" else []),
            ),
        )
        conn.commit()
        conn.close()

        flash(f'Usuário "{usuario}" criado com sucesso.', "sucesso")
        return redirect(url_for("admin_equipe"))

    conn.close()
    return render_template(
        "admin/equipe_form.html",
        membro=None,
        limite_excedido=limite_excedido,
        limite=limite,
        permissoes_disponiveis=PERMISSOES_DISPONIVEIS,
    )


@app.route("/admin/equipe/<int:usuario_id>/editar", methods=["GET", "POST"])
@login_required
@apenas_proprietario
def admin_equipe_editar(usuario_id):
    empresa_id = session["empresa_id"]
    conn = get_connection()

    membro = conn.execute(
        "SELECT * FROM usuarios WHERE id = ? AND empresa_id = ?",
        (usuario_id, empresa_id),
    ).fetchone()

    if not membro:
        conn.close()
        flash("Usuário não encontrado.", "erro")
        return redirect(url_for("admin_equipe"))

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        papel = request.form.get("papel", "colaborador").strip()
        if papel not in ("proprietario", "colaborador"):
            papel = "colaborador"
        permissoes = _permissoes_validas(request.form.getlist("permissoes"))
        nova_senha = request.form.get("nova_senha", "").strip()
        ativo = 1 if request.form.get("ativo") == "on" else 0

        vai_perder_papel_ou_ficar_inativo = (
            membro["papel"] == "proprietario" and (papel != "proprietario" or not ativo)
        )
        if vai_perder_papel_ou_ficar_inativo and not _tem_outro_proprietario_ativo(
            conn, empresa_id, usuario_id
        ):
            conn.close()
            flash(
                "A empresa precisa ter pelo menos um proprietário ativo.",
                "erro",
            )
            return redirect(url_for("admin_equipe_editar", usuario_id=usuario_id))

        if usuario_id == session.get("usuario_id") and not ativo:
            conn.close()
            flash(
                "Você não pode desativar o usuário com o qual está logado agora.",
                "erro",
            )
            return redirect(url_for("admin_equipe_editar", usuario_id=usuario_id))

        if not nome:
            conn.close()
            flash("Informe o nome do usuário.", "erro")
            return redirect(url_for("admin_equipe_editar", usuario_id=usuario_id))

        if nova_senha and len(nova_senha) < 6:
            conn.close()
            flash("A nova senha deve ter pelo menos 6 caracteres.", "erro")
            return redirect(url_for("admin_equipe_editar", usuario_id=usuario_id))

        permissoes_json = json.dumps(permissoes if papel == "colaborador" else [])

        if nova_senha:
            conn.execute(
                """
                UPDATE usuarios
                SET nome = ?, papel = ?, permissoes = ?, ativo = ?, senha = ?
                WHERE id = ? AND empresa_id = ?
                """,
                (
                    nome,
                    papel,
                    permissoes_json,
                    ativo,
                    gerar_hash_senha(nova_senha),
                    usuario_id,
                    empresa_id,
                ),
            )
        else:
            conn.execute(
                """
                UPDATE usuarios
                SET nome = ?, papel = ?, permissoes = ?, ativo = ?
                WHERE id = ? AND empresa_id = ?
                """,
                (nome, papel, permissoes_json, ativo, usuario_id, empresa_id),
            )

        conn.commit()
        conn.close()

        # Se o usuário editado é quem está logado, atualiza a sessão na hora.
        if usuario_id == session.get("usuario_id"):
            session["nome_usuario"] = nome
            session["papel"] = papel
            session["permissoes"] = permissoes if papel == "colaborador" else []

        flash("Usuário atualizado com sucesso.", "sucesso")
        return redirect(url_for("admin_equipe"))

    conn.close()

    membro_dict = dict(membro)
    try:
        membro_dict["permissoes_lista"] = json.loads(membro["permissoes"] or "[]")
    except (TypeError, ValueError):
        membro_dict["permissoes_lista"] = []

    return render_template(
        "admin/equipe_form.html",
        membro=membro_dict,
        limite_excedido=False,
        limite=None,
        permissoes_disponiveis=PERMISSOES_DISPONIVEIS,
    )


@app.route("/admin/equipe/<int:usuario_id>/alternar", methods=["POST"])
@login_required
@apenas_proprietario
def admin_equipe_alternar(usuario_id):
    empresa_id = session["empresa_id"]
    conn = get_connection()

    membro = conn.execute(
        "SELECT * FROM usuarios WHERE id = ? AND empresa_id = ?",
        (usuario_id, empresa_id),
    ).fetchone()

    if not membro:
        conn.close()
        flash("Usuário não encontrado.", "erro")
        return redirect(url_for("admin_equipe"))

    novo_status = 0 if membro["ativo"] else 1

    if membro["papel"] == "proprietario" and novo_status == 0:
        if not _tem_outro_proprietario_ativo(conn, empresa_id, usuario_id):
            conn.close()
            flash(
                "A empresa precisa ter pelo menos um proprietário ativo.",
                "erro",
            )
            return redirect(url_for("admin_equipe"))

    if usuario_id == session.get("usuario_id") and novo_status == 0:
        conn.close()
        flash(
            "Você não pode desativar o usuário com o qual está logado agora.",
            "erro",
        )
        return redirect(url_for("admin_equipe"))

    if novo_status == 1:
        from services.recursos import limite_atingido
        limite_excedido, limite, _uso = limite_atingido(conn, empresa_id, "usuarios")
        if limite_excedido:
            conn.close()
            flash(
                f"Seu plano atual permite até {limite} usuário(s) ativo(s). "
                "Desative outro usuário ou fale com a Bytech para aumentar o limite.",
                "erro",
            )
            return redirect(url_for("admin_equipe"))

    conn.execute(
        "UPDATE usuarios SET ativo = ? WHERE id = ? AND empresa_id = ?",
        (novo_status, usuario_id, empresa_id),
    )
    conn.commit()
    conn.close()

    flash("Usuário ativado." if novo_status else "Usuário desativado.", "sucesso")
    return redirect(url_for("admin_equipe"))
