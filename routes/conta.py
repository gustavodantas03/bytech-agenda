"""Rotas do módulo conta."""

from core import *  # noqa: F401,F403

@app.route("/admin/minha-conta", methods=["GET", "POST"])
@login_required
def admin_minha_conta():
    usuario_id = session["usuario_id"]
    empresa_id = session["empresa_id"]

    conn = get_connection()

    conta = conn.execute(
        """
        SELECT
            id,
            empresa_id,
            usuario,
            senha
        FROM usuarios
        WHERE id = ?
          AND empresa_id = ?
        """,
        (
            usuario_id,
            empresa_id,
        ),
    ).fetchone()

    if not conta:
        conn.close()
        session.clear()

        flash(
            "Não foi possível localizar sua conta.",
            "erro",
        )

        return redirect(url_for("admin_login"))

    if request.method == "POST":
        senha_atual = request.form.get(
            "senha_atual",
            "",
        ).strip()

        nova_senha = request.form.get(
            "nova_senha",
            "",
        ).strip()

        confirmar_senha = request.form.get(
            "confirmar_senha",
            "",
        ).strip()

        if not all([
            senha_atual,
            nova_senha,
            confirmar_senha,
        ]):
            conn.close()

            flash(
                "Preencha todos os campos.",
                "erro",
            )

            return redirect(
                url_for("admin_minha_conta")
            )

        if not senha_confere(senha_atual, conta["senha"]):
            conn.close()

            flash(
                "A senha atual está incorreta.",
                "erro",
            )

            return redirect(
                url_for("admin_minha_conta")
            )

        if len(nova_senha) < 6:
            conn.close()

            flash(
                "A nova senha deve ter pelo menos 6 caracteres.",
                "erro",
            )

            return redirect(
                url_for("admin_minha_conta")
            )

        if nova_senha != confirmar_senha:
            conn.close()

            flash(
                "A nova senha e a confirmação não coincidem.",
                "erro",
            )

            return redirect(
                url_for("admin_minha_conta")
            )

        if nova_senha == senha_atual:
            conn.close()

            flash(
                "A nova senha deve ser diferente da senha atual.",
                "erro",
            )

            return redirect(
                url_for("admin_minha_conta")
            )

        conn.execute(
            """
            UPDATE usuarios
            SET senha = ?
            WHERE id = ?
              AND empresa_id = ?
            """,
            (
                gerar_hash_senha(nova_senha),
                usuario_id,
                empresa_id,
            ),
        )

        conn.commit()
        conn.close()

        flash(
            "Senha alterada com sucesso.",
            "sucesso",
        )

        return redirect(
            url_for("admin_minha_conta")
        )

    conn.close()

    return render_template(
        "admin/minha_conta.html",
        conta=conta,
    )


@app.route("/admin/meu-espaco", methods=["GET", "POST"])
@app.route("/admin/barbearia", methods=["GET", "POST"])
@login_required
def admin_meu_espaco():
    empresa_id = session["empresa_id"]

    conn = get_connection()
    empresa = conn.execute(
        "SELECT * FROM empresas WHERE id = ?",
        (empresa_id,),
    ).fetchone()

    if not empresa:
        conn.close()
        flash("Empresa não encontrada.", "erro")
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        telefone = request.form.get("telefone", "").strip()
        instagram = request.form.get("instagram", "").strip()
        endereco = request.form.get("endereco", "").strip()
        maps_url = request.form.get("maps_url", "").strip()
        descricao = request.form.get("descricao", "").strip()
        horario_texto = request.form.get("horario_texto", "").strip()

        logo_atual = empresa["logo"]
        arquivo_logo = request.files.get("logo")

        if arquivo_logo and arquivo_logo.filename:
            if not arquivo_permitido(arquivo_logo.filename):
                conn.close()
                flash(
                    "Formato inválido. Envie uma imagem PNG, JPG, JPEG ou WEBP.",
                    "erro",
                )
                return redirect(url_for("admin_meu_espaco"))

            extensao = secure_filename(
                arquivo_logo.filename
            ).rsplit(".", 1)[1].lower()

            novo_nome = f"empresa_{empresa_id}_{uuid4().hex}.{extensao}"
            caminho_logo = os.path.join(
                app.config["UPLOAD_FOLDER"],
                novo_nome,
            )

            arquivo_logo.save(caminho_logo)

            if logo_atual:
                caminho_antigo = os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    logo_atual,
                )

                if os.path.exists(caminho_antigo):
                    try:
                        os.remove(caminho_antigo)
                    except OSError:
                        pass

            logo_atual = novo_nome

        conn.execute(
            """
            UPDATE empresas
            SET nome = ?,
                telefone = ?,
                instagram = ?,
                endereco = ?,
                maps_url = ?,
                descricao = ?,
                horario_texto = ?,
                logo = ?
            WHERE id = ?
            """,
            (
                nome,
                telefone,
                instagram,
                endereco,
                maps_url,
                descricao,
                horario_texto,
                logo_atual,
                empresa_id,
            ),
        )

        conn.commit()
        conn.close()

        flash("Dados do seu espaço atualizados.", "sucesso")
        return redirect(url_for("admin_meu_espaco"))

    conn.close()

    return render_template(
        "admin/meu_espaco.html",
        empresa=empresa,
        horarios_funcionamento=obter_horarios_funcionamento(empresa),
        dias_semana=list(enumerate(DIAS_SEMANA_LABELS)),
    )


@app.route("/admin/meu-espaco/horarios", methods=["POST"])
@login_required
def admin_meu_espaco_horarios():
    empresa_id = session["empresa_id"]

    try:
        intervalo = int(request.form.get("intervalo_agendamento_minutos", 40))
    except (TypeError, ValueError):
        intervalo = 40
    intervalo = min(max(intervalo, 5), 240)

    nova_configuracao = {}
    for dia in range(7):
        aberto = request.form.get(f"aberto_{dia}") == "on"
        abertura = request.form.get(f"abertura_{dia}", "09:00").strip() or "09:00"
        fechamento = request.form.get(f"fechamento_{dia}", "18:00").strip() or "18:00"

        try:
            valido = datetime.strptime(abertura, "%H:%M") < datetime.strptime(fechamento, "%H:%M")
        except ValueError:
            valido = False

        if not valido:
            aberto = False
            abertura, fechamento = "09:00", "18:00"

        nova_configuracao[str(dia)] = {
            "aberto": aberto,
            "abertura": abertura,
            "fechamento": fechamento,
        }

    conn = get_connection()
    conn.execute(
        """
        UPDATE empresas
        SET horarios_funcionamento = ?, intervalo_agendamento_minutos = ?
        WHERE id = ?
        """,
        (json.dumps(nova_configuracao), intervalo, empresa_id),
    )
    conn.commit()
    conn.close()

    flash("Horário de funcionamento atualizado.", "sucesso")
    return redirect(url_for("admin_meu_espaco"))

