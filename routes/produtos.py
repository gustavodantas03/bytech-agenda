"""Rotas do módulo produtos."""

from core import *  # noqa: F401,F403
from uuid import uuid4
from werkzeug.utils import secure_filename
import os


@app.route("/admin/produtos")
@login_required
def admin_produtos():
    empresa_id = session["empresa_id"]
    conn = get_connection()

    resumo = conn.execute(
        """
        SELECT
            COUNT(*) FILTER (WHERE ativo = 1) AS produtos_ativos,
            COALESCE(
                SUM(estoque) FILTER (WHERE ativo = 1),
                0
            ) AS unidades_estoque,
            COUNT(*) FILTER (
                WHERE ativo = 1
                  AND estoque > 0
                  AND estoque_minimo > 0
                  AND estoque <= estoque_minimo
            ) AS estoque_baixo,
            COUNT(*) FILTER (
                WHERE ativo = 1
                  AND estoque <= 0
            ) AS sem_estoque
        FROM produtos
        WHERE empresa_id = ?
        """,
        (empresa_id,),
    ).fetchone()

    produtos_atencao = conn.execute(
        """
        SELECT
            p.id,
            p.nome,
            p.estoque,
            p.estoque_minimo,
            p.foto,
            c.nome AS categoria_nome
        FROM produtos p
        LEFT JOIN categorias_produtos c
            ON c.id = p.categoria_id
        WHERE p.empresa_id = ?
          AND p.ativo = 1
          AND (
                p.estoque <= 0
                OR (
                    p.estoque_minimo > 0
                    AND p.estoque <= p.estoque_minimo
                )
          )
        ORDER BY
            CASE WHEN p.estoque <= 0 THEN 0 ELSE 1 END,
            p.estoque ASC,
            p.nome
        LIMIT 10
        """,
        (empresa_id,),
    ).fetchall()

    movimentacoes = conn.execute(
        """
        SELECT
            m.id,
            m.tipo,
            m.quantidade,
            m.estoque_anterior,
            m.estoque_posterior,
            m.motivo,
            m.responsavel,
            m.criado_em,
            p.nome AS produto_nome
        FROM movimentacoes_estoque m
        JOIN produtos p
            ON p.id = m.produto_id
        WHERE m.empresa_id = ?
        ORDER BY m.criado_em DESC, m.id DESC
        LIMIT 10
        """,
        (empresa_id,),
    ).fetchall()

    conn.close()

    return render_template(
        "admin/produtos_dashboard.html",
        resumo=resumo,
        produtos_atencao=produtos_atencao,
        movimentacoes=movimentacoes,
        aba_produtos="dashboard",
    )


@app.route("/admin/produtos/cadastro", methods=["GET", "POST"])
@login_required
def cadastro_produtos():
    empresa_id = session["empresa_id"]
    conn = get_connection()

    if request.method == "POST":
        tipo = request.form.get("tipo", "produto")

        # =========================
        # CADASTRO DE CATEGORIA
        # =========================
        if tipo == "categoria":
            nome = request.form.get("nome", "").strip()

            if nome:
                conn.execute(
                    """
                    INSERT INTO categorias_produtos (empresa_id, nome)
                    VALUES (?, ?)
                    """,
                    (empresa_id, nome),
                )
                conn.commit()
                conn.close()

                flash("Categoria cadastrada.", "sucesso")
                return redirect(url_for("cadastro_produtos"))

        # =========================
        # CADASTRO DE PRODUTO
        # =========================
        elif tipo == "produto":
            nome = request.form.get("nome", "").strip()
            descricao = request.form.get("descricao", "").strip()
            categoria_id = request.form.get("categoria_id") or None

            preco = request.form.get("preco", "0").replace(",", ".")
            estoque = "0"
            estoque_minimo = request.form.get("estoque_minimo", "0").replace(",", ".")

            foto_nome = None
            arquivo_foto = request.files.get("foto")

            if arquivo_foto and arquivo_foto.filename:
                if not arquivo_permitido(arquivo_foto.filename):
                    conn.close()
                    flash(
                        "Formato inválido. Envie uma imagem PNG, JPG, JPEG ou WEBP.",
                        "erro",
                    )
                    return redirect(url_for("cadastro_produtos"))

                nome_seguro = secure_filename(arquivo_foto.filename)

                if "." not in nome_seguro:
                    conn.close()
                    flash("Arquivo de imagem inválido.", "erro")
                    return redirect(url_for("cadastro_produtos"))

                extensao = nome_seguro.rsplit(".", 1)[1].lower()

                foto_nome = f"produto_{empresa_id}_{uuid4().hex}.{extensao}"

                pasta_fotos = app.config.get(
                    "PRODUTOS_UPLOAD_FOLDER",
                    os.path.join(
                        app.static_folder,
                        "uploads",
                        "produtos",
                    ),
                )

                os.makedirs(pasta_fotos, exist_ok=True)

                caminho_foto = os.path.join(
                    pasta_fotos,
                    foto_nome,
                )

                arquivo_foto.save(caminho_foto)

            if nome:
                conn.execute(
                    """
                    INSERT INTO produtos (
                        empresa_id,
                        categoria_id,
                        nome,
                        descricao,
                        preco,
                        estoque,
                        estoque_minimo,
                        foto
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        empresa_id,
                        int(categoria_id) if categoria_id else None,
                        nome,
                        descricao or None,
                        float(preco or 0),
                        float(estoque or 0),
                        float(estoque_minimo or 0),
                        foto_nome,
                    ),
                )

                conn.commit()
                conn.close()

                flash("Produto cadastrado.", "sucesso")
                return redirect(url_for("cadastro_produtos"))

    categorias = conn.execute(
        """
        SELECT *
        FROM categorias_produtos
        WHERE empresa_id = ?
        ORDER BY ordem, nome
        """,
        (empresa_id,),
    ).fetchall()

    produtos = conn.execute(
        """
        SELECT
            p.*,
            c.nome AS categoria_nome
        FROM produtos p
        LEFT JOIN categorias_produtos c
            ON c.id = p.categoria_id
        WHERE p.empresa_id = ?
        ORDER BY p.ordem, p.nome
        """,
        (empresa_id,),
    ).fetchall()

    conn.close()

    return render_template(
        "admin/produtos.html",
        categorias=categorias,
        produtos=produtos,
        aba_produtos="produtos",
    )


@app.route("/admin/produtos/<int:produto_id>/editar", methods=["GET", "POST"])
@login_required
def editar_produto(produto_id):
    empresa_id = session["empresa_id"]
    conn = get_connection()

    produto = conn.execute(
        """
        SELECT *
        FROM produtos
        WHERE id = ?
          AND empresa_id = ?
        """,
        (produto_id, empresa_id),
    ).fetchone()

    if not produto:
        conn.close()
        flash("Produto não encontrado.", "erro")
        return redirect(url_for("cadastro_produtos"))

    categorias = conn.execute(
        """
        SELECT *
        FROM categorias_produtos
        WHERE empresa_id = ?
        ORDER BY ordem, nome
        """,
        (empresa_id,),
    ).fetchall()

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        descricao = request.form.get("descricao", "").strip()
        categoria_id = request.form.get("categoria_id") or None

        preco = request.form.get("preco", "0").replace(",", ".")
        estoque = str(produto["estoque"] or 0)
        estoque_minimo = request.form.get("estoque_minimo", "0").replace(",", ".")

        foto_nome = produto["foto"]
        arquivo_foto = request.files.get("foto")

        if arquivo_foto and arquivo_foto.filename:
            if not arquivo_permitido(arquivo_foto.filename):
                conn.close()
                flash(
                    "Formato inválido. Envie uma imagem PNG, JPG, JPEG ou WEBP.",
                    "erro",
                )
                return redirect(
                    url_for(
                        "editar_produto",
                        produto_id=produto_id,
                    )
                )

            nome_seguro = secure_filename(arquivo_foto.filename)

            if "." not in nome_seguro:
                conn.close()
                flash("Arquivo de imagem inválido.", "erro")
                return redirect(
                    url_for(
                        "editar_produto",
                        produto_id=produto_id,
                    )
                )

            extensao = nome_seguro.rsplit(".", 1)[1].lower()

            foto_nome = (
                f"produto_{empresa_id}_{uuid4().hex}.{extensao}"
            )

            pasta_fotos = app.config.get(
                "PRODUTOS_UPLOAD_FOLDER",
                os.path.join(
                    app.static_folder,
                    "uploads",
                    "produtos",
                ),
            )

            os.makedirs(pasta_fotos, exist_ok=True)

            arquivo_foto.save(
                os.path.join(
                    pasta_fotos,
                    foto_nome,
                )
            )

        if not nome:
            conn.close()
            flash("Informe o nome do produto.", "erro")
            return redirect(
                url_for(
                    "editar_produto",
                    produto_id=produto_id,
                )
            )

        conn.execute(
            """
            UPDATE produtos
            SET categoria_id = ?,
                nome = ?,
                descricao = ?,
                preco = ?,
                estoque = ?,
                estoque_minimo = ?,
                foto = ?
            WHERE id = ?
              AND empresa_id = ?
            """,
            (
                int(categoria_id) if categoria_id else None,
                nome,
                descricao or None,
                float(preco or 0),
                float(estoque or 0),
                float(estoque_minimo or 0),
                foto_nome,
                produto_id,
                empresa_id,
            ),
        )

        conn.commit()
        conn.close()

        flash("Produto atualizado com sucesso.", "sucesso")
        return redirect(url_for("cadastro_produtos"))

    conn.close()

    return render_template(
        "admin/produto_editar.html",
        produto=produto,
        categorias=categorias,
    )


@app.route("/admin/produtos/<int:produto_id>/alternar-status", methods=["POST"])
@login_required
def alternar_status_produto(produto_id):
    empresa_id = session["empresa_id"]
    conn = get_connection()

    produto = conn.execute(
        """
        SELECT id, nome, ativo
        FROM produtos
        WHERE id = ?
          AND empresa_id = ?
        """,
        (produto_id, empresa_id),
    ).fetchone()

    if not produto:
        conn.close()
        flash("Produto não encontrado.", "erro")
        return redirect(url_for("cadastro_produtos"))

    novo_status = 0 if produto["ativo"] else 1

    conn.execute(
        """
        UPDATE produtos
        SET ativo = ?
        WHERE id = ?
          AND empresa_id = ?
        """,
        (
            novo_status,
            produto_id,
            empresa_id,
        ),
    )

    conn.commit()
    conn.close()

    if novo_status:
        flash("Produto ativado com sucesso.", "sucesso")
    else:
        flash("Produto desativado com sucesso.", "sucesso")

    return redirect(url_for("cadastro_produtos"))


@app.route("/admin/produtos/categorias/<int:categoria_id>/editar", methods=["POST"])
@login_required
def editar_categoria_produto(categoria_id):
    empresa_id = session["empresa_id"]
    nome = request.form.get("nome", "").strip()

    if not nome:
        flash("Informe o nome da categoria.", "erro")
        return redirect(url_for("cadastro_produtos"))

    conn = get_connection()

    categoria = conn.execute(
        """
        SELECT id
        FROM categorias_produtos
        WHERE id = ?
          AND empresa_id = ?
        """,
        (categoria_id, empresa_id),
    ).fetchone()

    if not categoria:
        conn.close()
        flash("Categoria não encontrada.", "erro")
        return redirect(url_for("cadastro_produtos"))

    conn.execute(
        """
        UPDATE categorias_produtos
        SET nome = ?
        WHERE id = ?
          AND empresa_id = ?
        """,
        (nome, categoria_id, empresa_id),
    )

    conn.commit()
    conn.close()

    flash("Categoria atualizada com sucesso.", "sucesso")
    return redirect(url_for("cadastro_produtos"))


@app.route("/admin/produtos/categorias/<int:categoria_id>/alternar-status", methods=["POST"])
@login_required
def alternar_status_categoria_produto(categoria_id):
    empresa_id = session["empresa_id"]
    conn = get_connection()

    categoria = conn.execute(
        """
        SELECT id, nome, ativo
        FROM categorias_produtos
        WHERE id = ?
          AND empresa_id = ?
        """,
        (categoria_id, empresa_id),
    ).fetchone()

    if not categoria:
        conn.close()
        flash("Categoria não encontrada.", "erro")
        return redirect(url_for("cadastro_produtos"))

    novo_status = 0 if categoria["ativo"] else 1

    conn.execute(
        """
        UPDATE categorias_produtos
        SET ativo = ?
        WHERE id = ?
          AND empresa_id = ?
        """,
        (novo_status, categoria_id, empresa_id),
    )

    conn.commit()
    conn.close()

    if novo_status:
        flash("Categoria ativada com sucesso.", "sucesso")
    else:
        flash("Categoria desativada com sucesso.", "sucesso")

    return redirect(url_for("cadastro_produtos"))


@app.route("/admin/produtos/<int:produto_id>/movimentar", methods=["POST"])
@login_required
def movimentar_estoque_produto(produto_id):
    empresa_id = session["empresa_id"]

    tipo = request.form.get("tipo", "").strip().lower()
    motivo = request.form.get("motivo", "").strip()

    try:
        quantidade = float(
            request.form.get("quantidade", "0")
            .replace(",", ".")
        )
    except (TypeError, ValueError):
        quantidade = 0

    if tipo not in ("entrada", "saida"):
        flash("Tipo de movimentação inválido.", "erro")
        return redirect(url_for("admin_produtos"))

    if quantidade <= 0:
        flash("Informe uma quantidade maior que zero.", "erro")
        return redirect(url_for("admin_produtos"))

    conn = get_connection()

    produto = conn.execute(
        """
        SELECT id, nome, estoque
        FROM produtos
        WHERE id = ?
          AND empresa_id = ?
        """,
        (produto_id, empresa_id),
    ).fetchone()

    if not produto:
        conn.close()
        flash("Produto não encontrado.", "erro")
        return redirect(url_for("admin_produtos"))

    estoque_anterior = float(produto["estoque"] or 0)

    if tipo == "entrada":
        estoque_posterior = estoque_anterior + quantidade

    else:
        if quantidade > estoque_anterior:
            conn.rollback()
            conn.close()
            flash(
                "Saída não permitida: quantidade maior que o estoque disponível.",
                "erro",
            )
            return redirect(url_for("admin_produtos"))

        estoque_posterior = estoque_anterior - quantidade

    responsavel = (
        session.get("nome")
        or session.get("usuario")
        or session.get("username")
        or "Administrador"
    )

    try:
        conn.execute(
            """
            UPDATE produtos
            SET estoque = ?
            WHERE id = ?
              AND empresa_id = ?
            """,
            (
                estoque_posterior,
                produto_id,
                empresa_id,
            ),
        )

        conn.execute(
            """
            INSERT INTO movimentacoes_estoque (
                empresa_id,
                produto_id,
                tipo,
                quantidade,
                estoque_anterior,
                estoque_posterior,
                motivo,
                responsavel
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                empresa_id,
                produto_id,
                tipo,
                quantidade,
                estoque_anterior,
                estoque_posterior,
                motivo or None,
                responsavel,
            ),
        )

        conn.commit()

    except Exception:
        conn.rollback()
        conn.close()
        raise

    conn.close()

    if tipo == "entrada":
        flash(
            f"Entrada de {quantidade:g} unidade(s) registrada com sucesso.",
            "sucesso",
        )
    else:
        flash(
            f"Saída de {quantidade:g} unidade(s) registrada com sucesso.",
            "sucesso",
        )

    destino = request.form.get("destino", "").strip()

    if destino == "saida":
        return redirect(url_for("saida_estoque"))

    if destino == "entrada":
        return redirect(url_for("entrada_estoque"))

    return redirect(url_for("admin_produtos"))


# ============================================================
# PÁGINAS DO MÓDULO DE PRODUTOS / ESTOQUE
# ============================================================

@app.route("/admin/produtos/entrada", methods=["GET", "POST"])
@login_required
def entrada_estoque():
    empresa_id = session["empresa_id"]
    conn = get_connection()

    if request.method == "POST":
        produto_id = request.form.get("produto_id")
        motivo = request.form.get("motivo", "").strip()

        try:
            produto_id = int(produto_id)
        except (TypeError, ValueError):
            produto_id = 0

        try:
            quantidade = float(
                request.form.get("quantidade", "0").replace(",", ".")
            )
        except (TypeError, ValueError):
            quantidade = 0

        if not produto_id:
            conn.close()
            flash("Selecione um produto.", "erro")
            return redirect(url_for("entrada_estoque"))

        if quantidade <= 0:
            conn.close()
            flash("Informe uma quantidade maior que zero.", "erro")
            return redirect(url_for("entrada_estoque"))

        produto = conn.execute(
            """
            SELECT id, nome, estoque
            FROM produtos
            WHERE id = ?
              AND empresa_id = ?
              AND ativo = 1
            FOR UPDATE
            """,
            (produto_id, empresa_id),
        ).fetchone()

        if not produto:
            conn.rollback()
            conn.close()
            flash("Produto não encontrado ou inativo.", "erro")
            return redirect(url_for("entrada_estoque"))

        estoque_anterior = float(produto["estoque"] or 0)
        estoque_posterior = estoque_anterior + quantidade

        responsavel = (
            session.get("nome")
            or session.get("usuario")
            or session.get("username")
            or "Administrador"
        )

        try:
            conn.execute(
                """
                UPDATE produtos
                SET estoque = ?
                WHERE id = ?
                  AND empresa_id = ?
                """,
                (
                    estoque_posterior,
                    produto_id,
                    empresa_id,
                ),
            )

            conn.execute(
                """
                INSERT INTO movimentacoes_estoque (
                    empresa_id,
                    produto_id,
                    tipo,
                    quantidade,
                    estoque_anterior,
                    estoque_posterior,
                    motivo,
                    responsavel
                )
                VALUES (?, ?, 'entrada', ?, ?, ?, ?, ?)
                """,
                (
                    empresa_id,
                    produto_id,
                    quantidade,
                    estoque_anterior,
                    estoque_posterior,
                    motivo or None,
                    responsavel,
                ),
            )

            conn.commit()

        except Exception:
            conn.rollback()
            conn.close()
            raise

        conn.close()

        flash(
            f"Entrada de {quantidade:g} unidade(s) de {produto['nome']} registrada.",
            "sucesso",
        )
        return redirect(url_for("entrada_estoque"))

    produtos = conn.execute(
        """
        SELECT
            id,
            nome,
            estoque,
            estoque_minimo
        FROM produtos
        WHERE empresa_id = ?
          AND ativo = 1
        ORDER BY nome
        """,
        (empresa_id,),
    ).fetchall()

    entradas = conn.execute(
        """
        SELECT
            m.id,
            m.quantidade,
            m.estoque_anterior,
            m.estoque_posterior,
            m.motivo,
            m.responsavel,
            m.criado_em,
            p.nome AS produto_nome
        FROM movimentacoes_estoque m
        JOIN produtos p
            ON p.id = m.produto_id
        WHERE m.empresa_id = ?
          AND m.tipo = 'entrada'
        ORDER BY m.criado_em DESC, m.id DESC
        LIMIT 15
        """,
        (empresa_id,),
    ).fetchall()

    conn.close()

    return render_template(
        "admin/produtos_entrada.html",
        produtos=produtos,
        entradas=entradas,
        aba_produtos="entrada",
    )


@app.route("/admin/produtos/saida", methods=["GET", "POST"])
@login_required
def saida_estoque():
    empresa_id = session["empresa_id"]
    conn = get_connection()

    if request.method == "POST":
        produto_id = request.form.get("produto_id")
        motivo = request.form.get("motivo", "").strip()

        try:
            produto_id = int(produto_id)
        except (TypeError, ValueError):
            produto_id = 0

        try:
            quantidade = float(
                request.form.get("quantidade", "0").replace(",", ".")
            )
        except (TypeError, ValueError):
            quantidade = 0

        if not produto_id or quantidade <= 0:
            conn.close()
            flash("Selecione o produto e informe uma quantidade válida.", "erro")
            return redirect(url_for("saida_estoque"))

        produto = conn.execute(
            """
            SELECT id, nome, estoque
            FROM produtos
            WHERE id = ?
              AND empresa_id = ?
              AND ativo = 1
            FOR UPDATE
            """,
            (produto_id, empresa_id),
        ).fetchone()

        if not produto:
            conn.rollback()
            conn.close()
            flash("Produto não encontrado ou inativo.", "erro")
            return redirect(url_for("saida_estoque"))

        estoque_anterior = float(produto["estoque"] or 0)

        if quantidade > estoque_anterior:
            conn.close()
            flash(
                f"Estoque insuficiente. Disponível: {estoque_anterior:g}.",
                "erro",
            )
            return redirect(url_for("saida_estoque"))

        estoque_posterior = estoque_anterior - quantidade

        responsavel = (
            session.get("nome")
            or session.get("usuario")
            or session.get("username")
            or "Administrador"
        )

        try:
            conn.execute(
                """
                UPDATE produtos
                SET estoque = ?
                WHERE id = ?
                  AND empresa_id = ?
                """,
                (estoque_posterior, produto_id, empresa_id),
            )

            conn.execute(
                """
                INSERT INTO movimentacoes_estoque (
                    empresa_id,
                    produto_id,
                    tipo,
                    quantidade,
                    estoque_anterior,
                    estoque_posterior,
                    motivo,
                    responsavel
                )
                VALUES (?, ?, 'saida', ?, ?, ?, ?, ?)
                """,
                (
                    empresa_id,
                    produto_id,
                    quantidade,
                    estoque_anterior,
                    estoque_posterior,
                    motivo or None,
                    responsavel,
                ),
            )

            conn.commit()

        except Exception:
            conn.rollback()
            conn.close()
            raise

        conn.close()

        flash(
            f"Saída de {quantidade:g} unidade(s) de {produto['nome']} registrada.",
            "sucesso",
        )
        return redirect(url_for("saida_estoque"))

    produtos = conn.execute(
        """
        SELECT id, nome, estoque, estoque_minimo
        FROM produtos
        WHERE empresa_id = ?
          AND ativo = 1
        ORDER BY nome
        """,
        (empresa_id,),
    ).fetchall()

    saidas = conn.execute(
        """
        SELECT
            m.id,
            m.quantidade,
            m.estoque_anterior,
            m.estoque_posterior,
            m.motivo,
            m.responsavel,
            m.criado_em,
            p.nome AS produto_nome
        FROM movimentacoes_estoque m
        JOIN produtos p ON p.id = m.produto_id
        WHERE m.empresa_id = ?
          AND m.tipo = 'saida'
        ORDER BY m.criado_em DESC, m.id DESC
        LIMIT 15
        """,
        (empresa_id,),
    ).fetchall()

    conn.close()

    return render_template(
        "admin/produtos_saida.html",
        produtos=produtos,
        saidas=saidas,
        aba_produtos="saida",
    )


@app.route("/admin/produtos/estoque")
@login_required
def estoque_produtos():
    empresa_id = session["empresa_id"]
    conn = get_connection()

    produtos = conn.execute(
        """
        SELECT
            p.id,
            p.nome,
            p.preco,
            p.estoque,
            p.estoque_minimo,
            p.foto,
            p.ativo,
            c.nome AS categoria_nome
        FROM produtos p
        LEFT JOIN categorias_produtos c
            ON c.id = p.categoria_id
        WHERE p.empresa_id = ?
        ORDER BY
            CASE
                WHEN p.estoque <= 0 THEN 0
                WHEN p.estoque_minimo > 0
                     AND p.estoque <= p.estoque_minimo THEN 1
                ELSE 2
            END,
            p.nome
        """,
        (empresa_id,),
    ).fetchall()

    ativos = [p for p in produtos if p["ativo"]]

    resumo = {
        "total_produtos": len(ativos),
        "unidades_estoque": sum(float(p["estoque"] or 0) for p in ativos),
        "estoque_baixo": sum(
            1 for p in ativos
            if float(p["estoque"] or 0) > 0
            and float(p["estoque_minimo"] or 0) > 0
            and float(p["estoque"] or 0) <= float(p["estoque_minimo"] or 0)
        ),
        "sem_estoque": sum(
            1 for p in ativos if float(p["estoque"] or 0) <= 0
        ),
        "valor_estoque": sum(
            float(p["preco"] or 0) * float(p["estoque"] or 0)
            for p in ativos
        ),
    }

    conn.close()

    return render_template(
        "admin/produtos_estoque.html",
        produtos=produtos,
        resumo=resumo,
        aba_produtos="estoque",
    )


@app.route("/admin/produtos/relatorios")
@login_required
def relatorios_produtos():
    empresa_id = session["empresa_id"]

    tipo = request.args.get("tipo", "").strip()
    produto_id = request.args.get("produto_id", "").strip()
    data_inicio = request.args.get("data_inicio", "").strip()
    data_fim = request.args.get("data_fim", "").strip()

    conn = get_connection()

    produtos = conn.execute(
        """
        SELECT id, nome
        FROM produtos
        WHERE empresa_id = ?
        ORDER BY nome
        """,
        (empresa_id,),
    ).fetchall()

    sql = """
        SELECT
            m.id,
            m.tipo,
            m.quantidade,
            m.estoque_anterior,
            m.estoque_posterior,
            m.motivo,
            m.responsavel,
            m.criado_em,
            p.nome AS produto_nome
        FROM movimentacoes_estoque m
        JOIN produtos p ON p.id = m.produto_id
        WHERE m.empresa_id = ?
    """

    params = [empresa_id]

    if tipo in ("entrada", "saida"):
        sql += " AND m.tipo = ?"
        params.append(tipo)

    if produto_id.isdigit():
        sql += " AND m.produto_id = ?"
        params.append(int(produto_id))

    if data_inicio:
        sql += " AND DATE(m.criado_em) >= ?"
        params.append(data_inicio)

    if data_fim:
        sql += " AND DATE(m.criado_em) <= ?"
        params.append(data_fim)

    sql += " ORDER BY m.criado_em DESC"

    movimentacoes = conn.execute(
        sql,
        tuple(params),
    ).fetchall()

    total_entradas = sum(
        float(m["quantidade"] or 0)
        for m in movimentacoes
        if m["tipo"] == "entrada"
    )

    total_saidas = sum(
        float(m["quantidade"] or 0)
        for m in movimentacoes
        if m["tipo"] == "saida"
    )

    resumo = {
        "movimentacoes": len(movimentacoes),
        "entradas": total_entradas,
        "saidas": total_saidas,
    }

    conn.close()

    return render_template(
        "admin/produtos_relatorios.html",
        produtos=produtos,
        movimentacoes=movimentacoes,
        resumo=resumo,
        tipo=tipo,
        produto_id=produto_id,
        data_inicio=data_inicio,
        data_fim=data_fim,
        aba_produtos="relatorios",
    )

@app.route("/admin/pdv")
@login_required
def admin_pdv():
    empresa_id = session["empresa_id"]

    conn = get_connection()

    clientes = conn.execute(
        "SELECT id, nome, telefone FROM clientes WHERE empresa_id = ? AND ativo = 1 ORDER BY nome",
        (empresa_id,),
    ).fetchall()

    produtos = conn.execute(
        "SELECT id, nome, preco, estoque, foto FROM produtos WHERE empresa_id = ? AND ativo = 1 ORDER BY nome",
        (empresa_id,),
    ).fetchall()

    servicos = conn.execute(
        "SELECT id, nome, valor, duracao, foto FROM servicos WHERE empresa_id = ? AND ativo = 1 ORDER BY nome",
        (empresa_id,),
    ).fetchall()

    funcionarios = conn.execute(
        "SELECT id, nome, cargo, foto FROM funcionarios WHERE empresa_id = ? AND ativo = 1 ORDER BY nome",
        (empresa_id,),
    ).fetchall()

    conn.close()

    return render_template(
        "admin/pdv.html",
        clientes=clientes,
        produtos=produtos,
        servicos=servicos,
        funcionarios=funcionarios,
    )

@app.route("/admin/pdv/finalizar", methods=["POST"])
@login_required
def finalizar_venda_pdv():
    empresa_id = session["empresa_id"]
    dados = request.get_json(silent=True) or {}

    cliente_id = dados.get("cliente_id")
    forma_pagamento = str(dados.get("forma_pagamento", "")).strip().lower()
    tipo_desconto = str(dados.get("tipo_desconto", "valor")).strip().lower()
    valor_desconto = dados.get("valor_desconto", 0)
    itens = dados.get("itens") or []

    formas_validas = {"dinheiro", "pix", "debito", "credito", "outro"}
    tipos_desconto_validos = {"valor", "percentual"}

    if tipo_desconto not in tipos_desconto_validos:
        return jsonify({
            "ok": False,
            "erro": "Tipo de desconto inválido."
        }), 400

    try:
        valor_desconto = float(valor_desconto or 0)
    except (TypeError, ValueError):
        return jsonify({
            "ok": False,
            "erro": "Valor de desconto inválido."
        }), 400

    if valor_desconto < 0:
        return jsonify({
            "ok": False,
            "erro": "O desconto não pode ser negativo."
        }), 400

    if tipo_desconto == "percentual" and valor_desconto > 100:
        return jsonify({
            "ok": False,
            "erro": "O desconto percentual não pode ser maior que 100%."
        }), 400

    if forma_pagamento not in formas_validas:
        return jsonify({
            "ok": False,
            "erro": "Forma de pagamento inválida."
        }), 400

    if not itens:
        return jsonify({
            "ok": False,
            "erro": "Adicione pelo menos um item à venda."
        }), 400

    if cliente_id in ("", None):
        cliente_id = None
    else:
        try:
            cliente_id = int(cliente_id)
        except (TypeError, ValueError):
            return jsonify({
                "ok": False,
                "erro": "Cliente inválido."
            }), 400

    conn = get_connection()

    try:
        if cliente_id is not None:
            cliente = conn.execute(
                """
                SELECT id
                FROM clientes
                WHERE id = ?
                  AND empresa_id = ?
                  AND ativo = 1
                """,
                (cliente_id, empresa_id),
            ).fetchone()

            if not cliente:
                conn.rollback()
                conn.close()
                return jsonify({
                    "ok": False,
                    "erro": "Cliente não encontrado."
                }), 400

        itens_validos = []
        itens_recebidos = set()
        subtotal_venda = 0.0

        for item in itens:
            tipo = str(item.get("tipo", "")).strip()
            item_id = item.get("id")
            funcionario_id = None

            try:
                item_id = int(item_id)
                quantidade = float(item.get("quantidade", 0))
            except (TypeError, ValueError):
                raise ValueError("Item ou quantidade inválida.")

            if quantidade <= 0:
                raise ValueError("A quantidade deve ser maior que zero.")

            chave_item = (tipo, item_id)
            if chave_item in itens_recebidos:
                raise ValueError("Item duplicado na venda.")
            itens_recebidos.add(chave_item)

            if tipo == "produto":
                registro = conn.execute(
                    """
                    SELECT id, nome, preco, estoque
                    FROM produtos
                    WHERE id = ?
                      AND empresa_id = ?
                      AND ativo = 1
                    FOR UPDATE
                    """,
                    (item_id, empresa_id),
                ).fetchone()

                if not registro:
                    raise ValueError("Produto não encontrado.")

                if quantidade > float(registro["estoque"] or 0):
                    raise ValueError(
                        f"Estoque insuficiente para {registro['nome']}."
                    )

                valor = float(registro["preco"] or 0)

            elif tipo == "servico":
                registro = conn.execute(
                    """
                    SELECT id, nome, valor
                    FROM servicos
                    WHERE id = ?
                      AND empresa_id = ?
                      AND ativo = 1
                    """,
                    (item_id, empresa_id),
                ).fetchone()

                if not registro:
                    raise ValueError("Serviço não encontrado.")

                try:
                    funcionario_id = int(item.get("funcionario_id"))
                except (TypeError, ValueError):
                    raise ValueError(
                        f"Selecione o profissional para {registro['nome']}."
                    )

                funcionario = conn.execute(
                    """
                    SELECT id
                    FROM funcionarios
                    WHERE id = ?
                      AND empresa_id = ?
                      AND ativo = 1
                    """,
                    (funcionario_id, empresa_id),
                ).fetchone()

                if not funcionario:
                    raise ValueError(
                        f"Profissional inválido para {registro['nome']}."
                    )

                valor = float(registro["valor"] or 0)

            else:
                raise ValueError("Tipo de item inválido.")

            subtotal = valor * quantidade
            subtotal_venda += subtotal

            itens_validos.append({
                "tipo": tipo,
                "id": item_id,
                "nome": registro["nome"],
                "quantidade": quantidade,
                "valor": valor,
                "subtotal": subtotal,
                "funcionario_id": funcionario_id,
            })

        subtotal_venda = round(subtotal_venda, 2)

        if tipo_desconto == "percentual":
            desconto_venda = round(
                subtotal_venda * (valor_desconto / 100),
                2,
            )
        else:
            desconto_venda = round(valor_desconto, 2)

        if desconto_venda > subtotal_venda:
            raise ValueError(
                "O desconto não pode ser maior que o subtotal da venda."
            )

        desconto_venda = max(0.0, desconto_venda)
        total_venda = round(subtotal_venda - desconto_venda, 2)

        responsavel = (
            session.get("nome")
            or session.get("usuario")
            or session.get("username")
            or "Administrador"
        )

        venda = conn.execute(
            """
            INSERT INTO vendas (
                empresa_id,
                cliente_id,
                subtotal,
                desconto,
                total,
                status,
                responsavel,
                finalizado_em
            )
            VALUES (?, ?, ?, ?, ?, 'finalizada', ?, CURRENT_TIMESTAMP)
            RETURNING id
            """,
            (
                empresa_id,
                cliente_id,
                subtotal_venda,
                desconto_venda,
                total_venda,
                responsavel,
            ),
        ).fetchone()

        venda_id = venda["id"]

        for item in itens_validos:
            produto_id = item["id"] if item["tipo"] == "produto" else None
            servico_id = item["id"] if item["tipo"] == "servico" else None

            conn.execute(
                """
                INSERT INTO venda_itens (
                    venda_id,
                    empresa_id,
                    tipo,
                    produto_id,
                    servico_id,
                    funcionario_id,
                    descricao,
                    quantidade,
                    valor_unitario,
                    subtotal
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    venda_id,
                    empresa_id,
                    item["tipo"],
                    produto_id,
                    servico_id,
                    item["funcionario_id"],
                    item["nome"],
                    item["quantidade"],
                    item["valor"],
                    item["subtotal"],
                ),
            )

        for item in itens_validos:
            if item["tipo"] != "produto":
                continue

            produto = conn.execute(
                """
                SELECT estoque
                FROM produtos
                WHERE id = ?
                  AND empresa_id = ?
                """,
                (item["id"], empresa_id),
            ).fetchone()

            estoque_anterior = float(produto["estoque"] or 0)
            estoque_posterior = estoque_anterior - item["quantidade"]

            conn.execute(
                """
                UPDATE produtos
                SET estoque = ?,
                    atualizado_em = CURRENT_TIMESTAMP
                WHERE id = ?
                  AND empresa_id = ?
                """,
                (
                    estoque_posterior,
                    item["id"],
                    empresa_id,
                ),
            )

            conn.execute(
                """
                INSERT INTO movimentacoes_estoque (
                    empresa_id,
                    produto_id,
                    tipo,
                    quantidade,
                    estoque_anterior,
                    estoque_posterior,
                    motivo,
                    responsavel
                )
                VALUES (?, ?, 'saida', ?, ?, ?, ?, ?)
                """,
                (
                    empresa_id,
                    item["id"],
                    item["quantidade"],
                    estoque_anterior,
                    estoque_posterior,
                    f"Venda #{venda_id}",
                    responsavel,
                ),
            )

        conn.execute(
            """
            INSERT INTO venda_pagamentos (
                venda_id,
                empresa_id,
                forma,
                valor
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                venda_id,
                empresa_id,
                forma_pagamento,
                total_venda,
            ),
        )

        conn.commit()
        conn.close()

        return jsonify({
            "ok": True,
            "venda_id": venda_id,
            "total": total_venda,
        })

    except ValueError as erro:
        conn.rollback()
        conn.close()
        return jsonify({
            "ok": False,
            "erro": str(erro),
        }), 400

    except Exception:
        conn.rollback()
        conn.close()
        raise

@app.route("/admin/vendas")
@login_required
def admin_vendas():
    empresa_id = session["empresa_id"]

    conn = get_connection()

    vendas = conn.execute(
        """
        SELECT
            v.id,
            v.cliente_id,
            COALESCE(c.nome, 'Consumidor não identificado') AS cliente_nome,
            v.subtotal,
            v.desconto,
            v.total,
            v.status,
            v.responsavel,
            v.criado_em,
            v.finalizado_em,
            COALESCE(
                (
                    SELECT STRING_AGG(vp.forma, ', ' ORDER BY vp.id)
                    FROM venda_pagamentos vp
                    WHERE vp.venda_id = v.id
                      AND vp.empresa_id = v.empresa_id
                ),
                'Não informado'
            ) AS formas_pagamento
        FROM vendas v
        LEFT JOIN clientes c
            ON c.id = v.cliente_id
           AND c.empresa_id = v.empresa_id
        WHERE v.empresa_id = ?
        ORDER BY v.id DESC
        """,
        (empresa_id,),
    ).fetchall()

    conn.close()

    return render_template(
        "admin/vendas.html",
        vendas=vendas,
    )

@app.route("/admin/vendas/<int:venda_id>")
@login_required
def admin_venda_detalhe(venda_id):
    empresa_id = session["empresa_id"]

    conn = get_connection()

    venda = conn.execute(
        """
        SELECT
            v.id,
            v.cliente_id,
            COALESCE(c.nome, 'Consumidor não identificado') AS cliente_nome,
            c.telefone AS cliente_telefone,
            v.subtotal,
            v.desconto,
            v.total,
            v.status,
            v.observacoes,
            v.responsavel,
            v.criado_em,
            v.finalizado_em,
            v.cancelado_em
        FROM vendas v
        LEFT JOIN clientes c
            ON c.id = v.cliente_id
           AND c.empresa_id = v.empresa_id
        WHERE v.id = ?
          AND v.empresa_id = ?
        """,
        (venda_id, empresa_id),
    ).fetchone()

    if not venda:
        conn.close()
        return "Venda não encontrada.", 404

    itens = conn.execute(
        """
        SELECT
            id,
            tipo,
            produto_id,
            servico_id,
            vi.funcionario_id,
            f.nome AS funcionario_nome,
            vi.descricao,
            vi.quantidade,
            vi.valor_unitario,
            vi.subtotal
        FROM venda_itens vi
        LEFT JOIN funcionarios f
            ON f.id = vi.funcionario_id
           AND f.empresa_id = vi.empresa_id
        WHERE vi.venda_id = ?
          AND vi.empresa_id = ?
        ORDER BY vi.id
        """,
        (venda_id, empresa_id),
    ).fetchall()

    pagamentos = conn.execute(
        """
        SELECT
            id,
            forma,
            valor,
            observacoes,
            criado_em
        FROM venda_pagamentos
        WHERE venda_id = ?
          AND empresa_id = ?
        ORDER BY id
        """,
        (venda_id, empresa_id),
    ).fetchall()

    conn.close()

    return render_template(
        "admin/venda_detalhe.html",
        venda=venda,
        itens=itens,
        pagamentos=pagamentos,
    )

@app.route("/admin/vendas/<int:venda_id>/cancelar", methods=["POST"])
@login_required
def admin_venda_cancelar(venda_id):
    empresa_id = session["empresa_id"]
    conn = get_connection()

    try:
        venda = conn.execute(
            """
            SELECT id, status
            FROM vendas
            WHERE id = ?
              AND empresa_id = ?
            FOR UPDATE
            """,
            (venda_id, empresa_id),
        ).fetchone()

        if not venda:
            raise ValueError("Venda não encontrada.")

        if venda["status"] == "cancelada":
            raise ValueError("Esta venda já foi cancelada.")

        if venda["status"] != "finalizada":
            raise ValueError("Somente vendas finalizadas podem ser canceladas.")

        itens = conn.execute(
            """
            SELECT produto_id, quantidade
            FROM venda_itens
            WHERE venda_id = ?
              AND empresa_id = ?
              AND tipo = 'produto'
              AND produto_id IS NOT NULL
            ORDER BY produto_id
            """,
            (venda_id, empresa_id),
        ).fetchall()

        responsavel = (
            session.get("nome")
            or session.get("usuario")
            or session.get("username")
            or "Administrador"
        )

        for item in itens:
            produto = conn.execute(
                """
                SELECT id, estoque
                FROM produtos
                WHERE id = ?
                  AND empresa_id = ?
                FOR UPDATE
                """,
                (item["produto_id"], empresa_id),
            ).fetchone()

            if not produto:
                raise ValueError("Produto da venda não encontrado.")

            estoque_anterior = float(produto["estoque"] or 0)
            quantidade = float(item["quantidade"] or 0)
            estoque_posterior = estoque_anterior + quantidade

            conn.execute(
                """
                UPDATE produtos
                SET estoque = ?,
                    atualizado_em = CURRENT_TIMESTAMP
                WHERE id = ?
                  AND empresa_id = ?
                """,
                (
                    estoque_posterior,
                    item["produto_id"],
                    empresa_id,
                ),
            )

            conn.execute(
                """
                INSERT INTO movimentacoes_estoque (
                    empresa_id,
                    produto_id,
                    tipo,
                    quantidade,
                    estoque_anterior,
                    estoque_posterior,
                    motivo,
                    responsavel
                )
                VALUES (?, ?, 'entrada', ?, ?, ?, ?, ?)
                """,
                (
                    empresa_id,
                    item["produto_id"],
                    quantidade,
                    estoque_anterior,
                    estoque_posterior,
                    f"Cancelamento venda #{venda_id}",
                    responsavel,
                ),
            )

        conn.execute(
            """
            UPDATE vendas
            SET status = 'cancelada',
                cancelado_em = CURRENT_TIMESTAMP
            WHERE id = ?
              AND empresa_id = ?
            """,
            (venda_id, empresa_id),
        )

        conn.commit()
        conn.close()

        flash("Venda cancelada e estoque devolvido com sucesso.", "sucesso")
        return redirect(
            url_for("admin_venda_detalhe", venda_id=venda_id)
        )

    except ValueError as erro:
        conn.rollback()
        conn.close()
        flash(str(erro), "erro")
        return redirect(
            url_for("admin_venda_detalhe", venda_id=venda_id)
        )

    except Exception:
        conn.rollback()
        conn.close()
        raise
