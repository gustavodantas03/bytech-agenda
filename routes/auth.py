"""Rotas do módulo auth."""

from core import *  # noqa: F401,F403

@app.route("/master/login", methods=["GET", "POST"])
def master_login():
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        senha = request.form.get("senha", "").strip()

        conn = get_connection()

        master = conn.execute(
            "SELECT * FROM usuarios_master WHERE usuario = ?",
            (usuario,),
        ).fetchone()

        minutos_restantes = minutos_bloqueio_restante(master)
        if minutos_restantes:
            conn.close()
            flash(
                f"Muitas tentativas incorretas. Tente novamente em {minutos_restantes} minuto(s).",
                "erro",
            )
            return render_template("master/login.html")

        if master and senha_confere(senha, master["senha"]):
            if not eh_hash_de_senha(master["senha"]):
                conn.execute(
                    "UPDATE usuarios_master SET senha = ? WHERE id = ?",
                    (gerar_hash_senha(senha), master["id"]),
                )
                conn.commit()

            limpar_falhas_login(conn, "usuarios_master", master["id"])
            conn.close()
            session.clear()
            session["master_id"] = master["id"]

            return redirect(url_for("master_dashboard"))

        if master:
            bloqueou = registrar_falha_login(
                conn, "usuarios_master", master["id"], valor_linha(master, "tentativas_falhas", 0)
            )
            conn.close()
            if bloqueou:
                flash(
                    f"Muitas tentativas incorretas. Acesso bloqueado por {BLOQUEIO_LOGIN_MINUTOS} minutos.",
                    "erro",
                )
                return render_template("master/login.html")
        else:
            conn.close()

        flash("Usuário ou senha inválidos.", "erro")

    return render_template("master/login.html")


@app.route("/master/sair")
def master_sair():
    session.clear()
    return redirect(url_for("master_login"))


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        senha = request.form.get("senha", "").strip()

        conn = get_connection()
        conta = conn.execute(
            "SELECT * FROM usuarios WHERE usuario = ?",
            (usuario,),
        ).fetchone()

        minutos_restantes = minutos_bloqueio_restante(conta)
        if minutos_restantes:
            conn.close()
            flash(
                f"Muitas tentativas incorretas. Tente novamente em {minutos_restantes} minuto(s).",
                "erro",
            )
            return render_template("admin/login.html")

        if conta and senha_confere(senha, conta["senha"]):
            if not valor_linha(conta, "ativo", 1):
                conn.close()
                flash(
                    "Este usuário foi desativado. Fale com o responsável da empresa.",
                    "erro",
                )
                return render_template("admin/login.html")

            if not eh_hash_de_senha(conta["senha"]):
                conn.execute(
                    "UPDATE usuarios SET senha = ? WHERE id = ?",
                    (gerar_hash_senha(senha), conta["id"]),
                )
                conn.commit()

            limpar_falhas_login(conn, "usuarios", conta["id"])

            from services.financeiro import atualizar_empresa_financeiro
            atualizar_empresa_financeiro(conn, conta["empresa_id"])
            conn.commit()
            empresa = conn.execute(
                "SELECT * FROM empresas WHERE id = ?", (conta["empresa_id"],)
            ).fetchone()
            conn.close()
            if empresa and empresa["bloqueado_financeiro"]:
                flash(
                    "Acesso temporariamente bloqueado por pendência financeira. Entre em contato com a Bytech.",
                    "erro",
                )
                return render_template("admin/login.html")
            if empresa and empresa["bloqueio_manual"]:
                flash("Acesso bloqueado pelo administrador da plataforma.", "erro")
                return render_template("admin/login.html")

            session.clear()
            session["empresa_id"] = conta["empresa_id"]
            session["usuario_id"] = conta["id"]
            session["nome_usuario"] = valor_linha(conta, "nome") or conta["usuario"]
            session["papel"] = valor_linha(conta, "papel") or "proprietario"
            try:
                session["permissoes"] = json.loads(valor_linha(conta, "permissoes") or "[]")
            except (TypeError, ValueError):
                session["permissoes"] = []
            return redirect(url_for("admin_dashboard"))

        if conta:
            bloqueou = registrar_falha_login(
                conn, "usuarios", conta["id"], valor_linha(conta, "tentativas_falhas", 0)
            )
            conn.close()
            if bloqueou:
                flash(
                    f"Muitas tentativas incorretas. Acesso bloqueado por {BLOQUEIO_LOGIN_MINUTOS} minutos.",
                    "erro",
                )
                return render_template("admin/login.html")
        else:
            conn.close()

        flash("Usuário ou senha inválidos.", "erro")

    return render_template("admin/login.html")


@app.route("/admin/sair")
def admin_sair():
    session.clear()
    return redirect(url_for("admin_login"))

