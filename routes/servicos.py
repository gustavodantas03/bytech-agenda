"""Rotas do módulo servicos."""

from core import *  # noqa: F401,F403
from uuid import uuid4
from werkzeug.utils import secure_filename
import os

@app.route("/admin/servicos", methods=["GET", "POST"])
@login_required
def admin_servicos():
    empresa_id = session["empresa_id"]
    conn = get_connection()

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        valor = request.form.get("valor", "0").replace(",", ".")
        duracao = request.form.get("duracao", "40")

        foto_nome = None
        arquivo_foto = request.files.get("foto")

        if arquivo_foto and arquivo_foto.filename:
            if not arquivo_permitido(arquivo_foto.filename):
                conn.close()
                flash(
                    "Formato inválido. Envie uma imagem PNG, JPG, JPEG ou WEBP.",
                    "erro",
                )
                return redirect(url_for("admin_servicos"))

            extensao = secure_filename(
                arquivo_foto.filename
            ).rsplit(".", 1)[1].lower()

            foto_nome = f"servico_{empresa_id}_{uuid4().hex}.{extensao}"
            pasta_fotos = app.config["SERVICOS_UPLOAD_FOLDER"]
            os.makedirs(pasta_fotos, exist_ok=True)
            caminho_foto = os.path.join(pasta_fotos, foto_nome)
            arquivo_foto.save(caminho_foto)

        if nome:
            conn.execute(
                "INSERT INTO servicos (empresa_id, nome, valor, duracao, foto) VALUES (?, ?, ?, ?, ?)",
                (empresa_id, nome, float(valor), int(duracao), foto_nome),
            )
            conn.commit()
            flash("Serviço cadastrado.", "sucesso")

    servicos = conn.execute(
        "SELECT * FROM servicos WHERE empresa_id = ? ORDER BY nome", (empresa_id,)
    ).fetchall()
    conn.close()

    return render_template("admin/servicos.html", servicos=servicos)


@app.route("/admin/servicos/<int:servico_id>/editar", methods=["GET", "POST"])
@login_required
def editar_servico(servico_id):
    empresa_id = session["empresa_id"]
    conn = get_connection()
    servico = conn.execute(
        "SELECT * FROM servicos WHERE id = ? AND empresa_id = ?",
        (servico_id, empresa_id),
    ).fetchone()

    if not servico:
        conn.close()
        flash("Serviço não encontrado.", "erro")
        return redirect(url_for("admin_servicos"))

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        valor = request.form.get("valor", "0").replace(",", ".")
        duracao = request.form.get("duracao", "40")

        foto_nome = servico["foto"]
        arquivo_foto = request.files.get("foto")

        if arquivo_foto and arquivo_foto.filename:
            if not arquivo_permitido(arquivo_foto.filename):
                conn.close()
                flash(
                    "Formato inválido. Envie uma imagem PNG, JPG, JPEG ou WEBP.",
                    "erro",
                )
                return redirect(
                    url_for("editar_servico", servico_id=servico_id)
                )

            extensao = secure_filename(
                arquivo_foto.filename
            ).rsplit(".", 1)[1].lower()

            foto_nome = f"servico_{empresa_id}_{uuid4().hex}.{extensao}"
            pasta_fotos = app.config["SERVICOS_UPLOAD_FOLDER"]
            os.makedirs(pasta_fotos, exist_ok=True)
            caminho_foto = os.path.join(pasta_fotos, foto_nome)
            arquivo_foto.save(caminho_foto)

        conn.execute(
            """
            UPDATE servicos
            SET nome = ?, valor = ?, duracao = ?, foto = ?
            WHERE id = ? AND empresa_id = ?
            """,
            (nome, float(valor), int(duracao), foto_nome, servico_id, empresa_id),
        )
        conn.commit()
        conn.close()
        flash("Serviço atualizado.", "sucesso")
        return redirect(url_for("admin_servicos"))

    conn.close()
    return render_template("admin/servico_editar.html", servico=servico)


@app.route("/admin/servicos/<int:servico_id>/alternar", methods=["POST"])
@login_required
def alternar_servico(servico_id):
    empresa_id = session["empresa_id"]
    conn = get_connection()
    servico = conn.execute(
        "SELECT * FROM servicos WHERE id = ? AND empresa_id = ?",
        (servico_id, empresa_id),
    ).fetchone()

    if servico:
        novo_status = 0 if servico["ativo"] else 1
        conn.execute("UPDATE servicos SET ativo = ? WHERE id = ?", (novo_status, servico_id))
        conn.commit()

    conn.close()
    return redirect(url_for("admin_servicos"))


@app.route("/admin/servicos/<int:servico_id>/excluir", methods=["POST"])
@login_required
def excluir_servico(servico_id):
    empresa_id = session["empresa_id"]
    conn = get_connection()
    possui_agendamento = conn.execute(
        """
        SELECT a.id
        FROM agendamentos a
        LEFT JOIN agendamento_servicos ags ON ags.agendamento_id = a.id
        WHERE a.empresa_id = ?
          AND (a.servico_id = ? OR ags.servico_id = ?)
        LIMIT 1
        """,
        (empresa_id, servico_id, servico_id),
    ).fetchone()

    if possui_agendamento:
        conn.close()
        flash("Este serviço possui agendamentos. Desative-o em vez de excluir.", "erro")
        return redirect(url_for("admin_servicos"))

    conn.execute(
        "DELETE FROM servicos WHERE id = ? AND empresa_id = ?",
        (servico_id, empresa_id),
    )
    conn.commit()
    conn.close()
    flash("Serviço excluído.", "sucesso")
    return redirect(url_for("admin_servicos"))

