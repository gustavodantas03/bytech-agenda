"""Rotas do módulo auth."""

from core import *  # noqa: F401,F403

@app.route("/master/login", methods=["GET", "POST"])
def master_login():
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        senha = request.form.get("senha", "").strip()

        conn = get_connection()

        master = conn.execute(
            """
            SELECT *
            FROM usuarios_master
            WHERE usuario = ?
              AND senha = ?
            """,
            (usuario, senha),
        ).fetchone()

        conn.close()

        if master:
            session.clear()
            session["master_id"] = master["id"]

            return redirect(url_for("master_dashboard"))

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
            "SELECT * FROM usuarios WHERE usuario = ? AND senha = ?",
            (usuario, senha),
        ).fetchone()

        if conta:
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
            session["empresa_id"] = conta["empresa_id"]
            session["usuario_id"] = conta["id"]
            return redirect(url_for("admin_dashboard"))

        conn.close()

        flash("Usuário ou senha inválidos.", "erro")

    return render_template("admin/login.html")


@app.route("/admin/sair")
def admin_sair():
    session.clear()
    return redirect(url_for("admin_login"))

