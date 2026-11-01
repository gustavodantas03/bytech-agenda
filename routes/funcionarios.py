"""Rotas do módulo funcionarios."""

from core import *  # noqa: F401,F403
from uuid import uuid4
from werkzeug.utils import secure_filename
import os

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

        arquivo_foto = request.files.get("foto")
        foto_nome = None

        if arquivo_foto and arquivo_foto.filename:
            if not arquivo_permitido(arquivo_foto.filename):
                conn.close()
                flash(
                    "Formato inválido. Envie uma imagem PNG, JPG, JPEG ou WEBP.",
                    "erro",
                )
                return redirect(url_for("admin_funcionarios"))

            extensao = secure_filename(
                arquivo_foto.filename
            ).rsplit(".", 1)[1].lower()

            foto_nome = f"profissional_{empresa_id}_{uuid4().hex}.{extensao}"
            pasta_fotos = app.config["PROFISSIONAIS_UPLOAD_FOLDER"]
            os.makedirs(pasta_fotos, exist_ok=True)
            caminho_foto = os.path.join(pasta_fotos, foto_nome)
            arquivo_foto.save(caminho_foto)

        if nome:
            conn.execute(
                "INSERT INTO funcionarios (empresa_id, nome, cargo, foto) VALUES (?, ?, ?, ?)",
                (empresa_id, nome, cargo, foto_nome),
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

        foto_nome = funcionario["foto"]

        arquivo_foto = request.files.get("foto")

        if arquivo_foto and arquivo_foto.filename:
            if not arquivo_permitido(arquivo_foto.filename):
                conn.close()
                flash(
                    "Formato inválido. Envie uma imagem PNG, JPG, JPEG ou WEBP.",
                    "erro",
                )
                return redirect(
                    url_for("editar_funcionario", funcionario_id=funcionario_id)
                )

            extensao = secure_filename(
                arquivo_foto.filename
            ).rsplit(".", 1)[1].lower()

            foto_nome = f"profissional_{empresa_id}_{uuid4().hex}.{extensao}"
            pasta_fotos = app.config["PROFISSIONAIS_UPLOAD_FOLDER"]
            os.makedirs(pasta_fotos, exist_ok=True)
            caminho_foto = os.path.join(pasta_fotos, foto_nome)
            arquivo_foto.save(caminho_foto)

        conn.execute(
            "UPDATE funcionarios SET nome = ?, cargo = ?, foto = ? WHERE id = ? AND empresa_id = ?",
            (nome, cargo, foto_nome, funcionario_id, empresa_id),
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

