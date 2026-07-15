from datetime import date, datetime, timedelta
from functools import wraps
import sqlite3

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for

from database import get_connection, init_db


import os
from uuid import uuid4

from werkzeug.utils import secure_filename
app = Flask(__name__)
app.secret_key = "troque-esta-chave-em-producao"

UPLOAD_FOLDER = os.path.join(app.root_path, "static", "uploads", "logos")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def arquivo_permitido(nome_arquivo):
    return (
        "." in nome_arquivo
        and nome_arquivo.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )

def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("empresa_id"):
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapped_view


def gerar_horarios():
    horarios = []
    inicio = datetime.strptime("09:00", "%H:%M")
    fim = datetime.strptime("18:00", "%H:%M")
    intervalo = timedelta(minutes=40)

    atual = inicio
    while atual < fim:
        horarios.append(atual.strftime("%H:%M"))
        atual += intervalo

    return horarios

def master_login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("master_id"):
            return redirect(url_for("master_login"))

        return view(*args, **kwargs)

    return wrapped_view

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

@app.before_request
def setup():
    init_db()

@app.route("/master/sair")
def master_sair():
    session.clear()
    return redirect(url_for("master_login"))

@app.route("/master")
@master_login_required
def master_dashboard():
    conn = get_connection()

    empresas = conn.execute(
        """
        SELECT
            e.*,
            u.usuario,
            (
                SELECT COUNT(*)
                FROM funcionarios f
                WHERE f.empresa_id = e.id
            ) AS total_funcionarios,
            (
                SELECT COUNT(*)
                FROM servicos s
                WHERE s.empresa_id = e.id
            ) AS total_servicos
        FROM empresas e
        LEFT JOIN usuarios u
            ON u.empresa_id = e.id
        ORDER BY e.nome
        """
    ).fetchall()

    conn.close()

    return render_template(
        "master/dashboard.html",
        empresas=empresas,
    )

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

        if not all([nome, slug, usuario, senha]):
            flash("Preencha os campos obrigatórios.", "erro")
            return redirect(url_for("master_nova_empresa"))

        slug = slug.replace(" ", "-")

        conn = get_connection()

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
                    nome,
                    slug,
                    telefone,
                    instagram,
                    endereco,
                    maps_url,
                    descricao,
                    horario_texto,
                    ativo
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    nome,
                    slug,
                    telefone,
                    instagram,
                    endereco,
                    maps_url,
                    descricao or "Agende seu horário de forma rápida e simples.",
                    horario_texto,
                ),
            )

            empresa_id = cursor.lastrowid

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

            servicos_padrao = [
                ("Corte masculino", 25.00, 40),
                ("Barba", 15.00, 30),
                ("Corte + barba", 35.00, 60),
            ]

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
                    for nome_servico, valor, duracao in servicos_padrao
                ],
            )

            funcionarios_padrao = [
                ("Barbeiro 1", "Barbeiro"),
            ]

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
                    for nome_funcionario, cargo in funcionarios_padrao
                ],
            )

            conn.commit()
            conn.close()

            flash(
                f"Barbearia criada com sucesso. Link: /{slug}",
                "sucesso",
            )

            return redirect(
                url_for(
                    "master_empresa_criada",
                    empresa_id=empresa_id,
                )
            )

        except Exception:
            conn.rollback()
            conn.close()

            flash(
                "Não foi possível criar a barbearia.",
                "erro",
            )

            return redirect(url_for("master_nova_empresa"))

    return render_template("master/empresa_nova.html")

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
        flash("Barbearia não encontrada.", "erro")
        return redirect(url_for("master_dashboard"))

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
        novo_status = 0 if empresa["ativo"] else 1

        conn.execute(
            """
            UPDATE empresas
            SET ativo = ?
            WHERE id = ?
            """,
            (novo_status, empresa_id),
        )

        conn.commit()

    conn.close()

    return redirect(url_for("master_dashboard"))

@app.route("/")
def index():
    return redirect(url_for("landing", slug="demo"))


@app.route("/<slug>")
def landing(slug):
    conn = get_connection()
    empresa = conn.execute(
        "SELECT * FROM empresas WHERE slug = ? AND ativo = 1", (slug,)
    ).fetchone()

    if not empresa:
        conn.close()
        return "Barbearia não encontrada.", 404

    servicos = conn.execute(
        "SELECT * FROM servicos WHERE empresa_id = ? AND ativo = 1 ORDER BY nome",
        (empresa["id"],),
    ).fetchall()
    conn.close()

    return render_template("landing.html", empresa=empresa, servicos=servicos)


@app.route("/<slug>/agendar")
def agendar(slug):
    conn = get_connection()
    empresa = conn.execute(
        "SELECT * FROM empresas WHERE slug = ? AND ativo = 1", (slug,)
    ).fetchone()

    if not empresa:
        conn.close()
        return "Barbearia não encontrada.", 404

    servicos = conn.execute(
        "SELECT * FROM servicos WHERE empresa_id = ? AND ativo = 1 ORDER BY nome",
        (empresa["id"],),
    ).fetchall()

    funcionarios = conn.execute(
        "SELECT * FROM funcionarios WHERE empresa_id = ? AND ativo = 1 ORDER BY nome",
        (empresa["id"],),
    ).fetchall()
    conn.close()

    datas = []
    atual = date.today()
    while len(datas) < 7:
        if atual.weekday() != 6:
            datas.append({"valor": atual.isoformat(), "texto": atual.strftime("%d/%m/%Y")})
        atual += timedelta(days=1)

    return render_template(
        "agendar.html",
        empresa=empresa,
        servicos=servicos,
        funcionarios=funcionarios,
        datas=datas,
    )


@app.route("/api/<slug>/horarios")
def horarios_disponiveis(slug):
    data = request.args.get("data")
    funcionario_id = request.args.get("funcionario_id", type=int)
    duracao_total = request.args.get("duracao_total", default=40, type=int)

    if not data or not funcionario_id:
        return jsonify({"erro": "Data ou profissional não informado."}), 400

    if duracao_total < 1 or duracao_total > 480:
        return jsonify({"erro": "Duração total inválida."}), 400

    conn = get_connection()
    empresa = conn.execute(
        "SELECT id FROM empresas WHERE slug = ? AND ativo = 1", (slug,)
    ).fetchone()

    if not empresa:
        conn.close()
        return jsonify({"erro": "Barbearia não encontrada."}), 404

    funcionario = conn.execute(
        "SELECT id FROM funcionarios WHERE id = ? AND empresa_id = ? AND ativo = 1",
        (funcionario_id, empresa["id"]),
    ).fetchone()

    if not funcionario:
        conn.close()
        return jsonify({"erro": "Profissional inválido."}), 400

    agendamentos_existentes = conn.execute(
        """
        SELECT hora, COALESCE(duracao_total, 40) AS duracao_total
        FROM agendamentos
        WHERE empresa_id = ?
          AND funcionario_id = ?
          AND data = ?
          AND status != 'cancelado'
        """,
        (empresa["id"], funcionario_id, data),
    ).fetchall()
    conn.close()

    abertura = datetime.strptime("09:00", "%H:%M")
    fechamento = datetime.strptime("18:00", "%H:%M")
    livres = []

    for hora in gerar_horarios():
        inicio_candidato = datetime.strptime(hora, "%H:%M")
        fim_candidato = inicio_candidato + timedelta(minutes=duracao_total)

        if fim_candidato > fechamento:
            continue

        tem_conflito = False
        for existente in agendamentos_existentes:
            inicio_existente = datetime.strptime(existente["hora"], "%H:%M")
            fim_existente = inicio_existente + timedelta(
                minutes=existente["duracao_total"] or 40
            )

            if inicio_candidato < fim_existente and fim_candidato > inicio_existente:
                tem_conflito = True
                break

        if not tem_conflito and inicio_candidato >= abertura:
            livres.append(hora)

    return jsonify({"horarios": livres})


@app.route("/api/<slug>/agendamentos", methods=["POST"])
def criar_agendamento(slug):
    dados = request.get_json() or {}
    servico_ids = dados.get("servico_ids") or []

    obrigatorios = [
        "cliente_nome",
        "cliente_telefone",
        "funcionario_id",
        "data",
        "hora",
    ]

    if any(not dados.get(campo) for campo in obrigatorios) or not servico_ids:
        return jsonify({"erro": "Preencha todos os campos e escolha ao menos um serviço."}), 400

    try:
        servico_ids = list(dict.fromkeys(int(item) for item in servico_ids))
    except (TypeError, ValueError):
        return jsonify({"erro": "Lista de serviços inválida."}), 400

    conn = get_connection()
    empresa = conn.execute(
        "SELECT * FROM empresas WHERE slug = ? AND ativo = 1", (slug,)
    ).fetchone()

    if not empresa:
        conn.close()
        return jsonify({"erro": "Barbearia não encontrada."}), 404

    placeholders = ",".join("?" for _ in servico_ids)
    servicos = conn.execute(
        f"""
        SELECT *
        FROM servicos
        WHERE id IN ({placeholders})
          AND empresa_id = ?
          AND ativo = 1
        ORDER BY nome
        """,
        (*servico_ids, empresa["id"]),
    ).fetchall()

    funcionario = conn.execute(
        "SELECT * FROM funcionarios WHERE id = ? AND empresa_id = ? AND ativo = 1",
        (dados["funcionario_id"], empresa["id"]),
    ).fetchone()

    if len(servicos) != len(servico_ids) or not funcionario:
        conn.close()
        return jsonify({"erro": "Serviço ou profissional inválido."}), 400

    duracao_total = sum(int(servico["duracao"] or 0) for servico in servicos)
    valor_total = sum(float(servico["valor"] or 0) for servico in servicos)

    inicio_novo = datetime.strptime(dados["hora"], "%H:%M")
    fim_novo = inicio_novo + timedelta(minutes=duracao_total)

    existentes = conn.execute(
        """
        SELECT hora, COALESCE(duracao_total, 40) AS duracao_total
        FROM agendamentos
        WHERE empresa_id = ?
          AND funcionario_id = ?
          AND data = ?
          AND status != 'cancelado'
        """,
        (empresa["id"], funcionario["id"], dados["data"]),
    ).fetchall()

    for existente in existentes:
        inicio_existente = datetime.strptime(existente["hora"], "%H:%M")
        fim_existente = inicio_existente + timedelta(
            minutes=existente["duracao_total"] or 40
        )
        if inicio_novo < fim_existente and fim_novo > inicio_existente:
            conn.close()
            return jsonify({"erro": "Este intervalo de horário acabou de ser ocupado. Escolha outro."}), 409

    try:
        cursor = conn.execute(
            """
            INSERT INTO agendamentos
            (
                empresa_id,
                cliente_nome,
                cliente_telefone,
                servico_id,
                funcionario_id,
                data,
                hora,
                duracao_total,
                valor_total
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                empresa["id"],
                dados["cliente_nome"].strip(),
                dados["cliente_telefone"].strip(),
                servico_ids[0],
                funcionario["id"],
                dados["data"],
                dados["hora"],
                duracao_total,
                valor_total,
            ),
        )
        agendamento_id = cursor.lastrowid

        conn.executemany(
            """
            INSERT INTO agendamento_servicos (agendamento_id, servico_id)
            VALUES (?, ?)
            """,
            [(agendamento_id, servico_id) for servico_id in servico_ids],
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        conn.close()
        return jsonify({"erro": "Este horário acabou de ser ocupado. Escolha outro."}), 409

    nomes_servicos = [servico["nome"] for servico in servicos]
    conn.close()

    mensagem = (
        f"Olá! Meu nome é {dados['cliente_nome']}. "
        f"Agendei os serviços: {', '.join(nomes_servicos)} "
        f"com {funcionario['nome']} para {dados['data']} às {dados['hora']}. "
        f"Valor total: R$ {valor_total:.2f}."
    )

    return jsonify({
        "sucesso": True,
        "mensagem": "Agendamento realizado com sucesso.",
        "whatsapp": mensagem,
        "valor_total": valor_total,
        "duracao_total": duracao_total,
    })


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
        conn.close()

        if conta:
            session["empresa_id"] = conta["empresa_id"]
            session["usuario_id"] = conta["id"]
            return redirect(url_for("admin_dashboard"))

        flash("Usuário ou senha inválidos.", "erro")

    return render_template("admin/login.html")


@app.route("/admin/sair")
def admin_sair():
    session.clear()
    return redirect(url_for("admin_login"))


@app.route("/admin/api/ultimo-agendamento")
@login_required
def admin_ultimo_agendamento():
    empresa_id = session["empresa_id"]

    conn = get_connection()

    ultimo = conn.execute(
        """
        SELECT
            a.id,
            a.cliente_nome,
            a.cliente_telefone,
            a.data,
            a.hora,
            a.status,
            COALESCE(
                (
                    SELECT GROUP_CONCAT(
                        s2.nome,
                        ' + '
                    )
                    FROM agendamento_servicos ags
                    JOIN servicos s2
                        ON s2.id = ags.servico_id
                    WHERE ags.agendamento_id = a.id
                ),
                s.nome
            ) AS servico_nome,
            f.nome AS funcionario_nome
        FROM agendamentos a
        JOIN servicos s
            ON s.id = a.servico_id
        LEFT JOIN funcionarios f
            ON f.id = a.funcionario_id
        WHERE a.empresa_id = ?
        ORDER BY a.id DESC
        LIMIT 1
        """,
        (empresa_id,),
    ).fetchone()

    conn.close()

    if not ultimo:
        return jsonify({
            "id": 0,
        })

    return jsonify({
        "id": ultimo["id"],
        "cliente_nome": ultimo["cliente_nome"],
        "cliente_telefone": ultimo["cliente_telefone"],
        "servico_nome": ultimo["servico_nome"],
        "funcionario_nome": (
            ultimo["funcionario_nome"]
            or "Sem profissional"
        ),
        "data": ultimo["data"],
        "hora": ultimo["hora"],
        "status": ultimo["status"],
    })

@app.route("/admin")
@login_required
def admin_dashboard():
    empresa_id = session["empresa_id"]
    hoje = date.today().isoformat()

    conn = get_connection()
    empresa = conn.execute("SELECT * FROM empresas WHERE id = ?", (empresa_id,)).fetchone()
    agendamentos = conn.execute(
        """
        SELECT
            a.*,
            COALESCE(
                (
                    SELECT GROUP_CONCAT(s2.nome, ' + ')
                    FROM agendamento_servicos ags
                    JOIN servicos s2 ON s2.id = ags.servico_id
                    WHERE ags.agendamento_id = a.id
                ),
                s.nome
            ) AS servico_nome,
            f.nome AS funcionario_nome
        FROM agendamentos a
        JOIN servicos s ON s.id = a.servico_id
        LEFT JOIN funcionarios f ON f.id = a.funcionario_id
        WHERE a.empresa_id = ? AND a.data = ?
        ORDER BY f.nome, a.hora
        """,
        (empresa_id, hoje),
    ).fetchall()
    total = conn.execute(
        "SELECT COUNT(*) AS total FROM agendamentos WHERE empresa_id = ?",
        (empresa_id,),
    ).fetchone()["total"]
    total_funcionarios = conn.execute(
        "SELECT COUNT(*) AS total FROM funcionarios WHERE empresa_id = ? AND ativo = 1",
        (empresa_id,),
    ).fetchone()["total"]
    conn.close()

    return render_template(
        "admin/dashboard.html",
        empresa=empresa,
        agendamentos=agendamentos,
        total=total,
        total_funcionarios=total_funcionarios,
        hoje=hoje,
    )


@app.route("/admin/servicos", methods=["GET", "POST"])
@login_required
def admin_servicos():
    empresa_id = session["empresa_id"]
    conn = get_connection()

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        valor = request.form.get("valor", "0").replace(",", ".")
        duracao = request.form.get("duracao", "40")

        if nome:
            conn.execute(
                "INSERT INTO servicos (empresa_id, nome, valor, duracao) VALUES (?, ?, ?, ?)",
                (empresa_id, nome, float(valor), int(duracao)),
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

        conn.execute(
            """
            UPDATE servicos
            SET nome = ?, valor = ?, duracao = ?
            WHERE id = ? AND empresa_id = ?
            """,
            (nome, float(valor), int(duracao), servico_id, empresa_id),
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


@app.route("/admin/funcionarios", methods=["GET", "POST"])
@login_required
def admin_funcionarios():
    empresa_id = session["empresa_id"]
    conn = get_connection()

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        cargo = request.form.get("cargo", "Barbeiro").strip() or "Barbeiro"

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
        cargo = request.form.get("cargo", "Barbeiro").strip() or "Barbeiro"
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


@app.route("/admin/barbearia", methods=["GET", "POST"])
@login_required
def admin_barbearia():
    empresa_id = session["empresa_id"]

    conn = get_connection()
    empresa = conn.execute(
        "SELECT * FROM empresas WHERE id = ?",
        (empresa_id,),
    ).fetchone()

    if not empresa:
        conn.close()
        flash("Barbearia não encontrada.", "erro")
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
                return redirect(url_for("admin_barbearia"))

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

        flash("Dados da barbearia atualizados.", "sucesso")
        return redirect(url_for("admin_barbearia"))

    conn.close()

    return render_template(
        "admin/barbearia.html",
        empresa=empresa,
    )

@app.route("/admin/agenda")
@login_required
def admin_agenda():
    empresa_id = session["empresa_id"]
    data_filtro = request.args.get("data", date.today().isoformat())
    funcionario_id = request.args.get("funcionario_id", type=int)

    conn = get_connection()
    funcionarios = conn.execute(
        "SELECT * FROM funcionarios WHERE empresa_id = ? AND ativo = 1 ORDER BY nome",
        (empresa_id,),
    ).fetchall()

    sql = """
        SELECT
            a.*,
            COALESCE(
                (
                    SELECT GROUP_CONCAT(s2.nome, ' + ')
                    FROM agendamento_servicos ags
                    JOIN servicos s2 ON s2.id = ags.servico_id
                    WHERE ags.agendamento_id = a.id
                ),
                s.nome
            ) AS servico_nome,
            f.nome AS funcionario_nome
        FROM agendamentos a
        JOIN servicos s ON s.id = a.servico_id
        LEFT JOIN funcionarios f ON f.id = a.funcionario_id
        WHERE a.empresa_id = ? AND a.data = ?
    """
    params = [empresa_id, data_filtro]

    if funcionario_id:
        sql += " AND a.funcionario_id = ?"
        params.append(funcionario_id)

    sql += " ORDER BY f.nome, a.hora"
    agendamentos = conn.execute(sql, params).fetchall()
    conn.close()

    return render_template(
        "admin/agenda.html",
        agendamentos=agendamentos,
        funcionarios=funcionarios,
        data_filtro=data_filtro,
        funcionario_id=funcionario_id,
    )


@app.route("/admin/agendamentos/<int:agendamento_id>/cancelar", methods=["POST"])
@login_required
def cancelar_agendamento(agendamento_id):
    empresa_id = session["empresa_id"]
    conn = get_connection()
    conn.execute(
        """
        UPDATE agendamentos
        SET status = 'cancelado'
        WHERE id = ? AND empresa_id = ?
        """,
        (agendamento_id, empresa_id),
    )
    conn.commit()
    conn.close()
    return redirect(request.referrer or url_for("admin_agenda"))

@app.route("/admin/agendamentos/novo", methods=["GET", "POST"])
@login_required
def novo_agendamento():
    empresa_id = session["empresa_id"]

    conn = get_connection()

    servicos = conn.execute(
        """
        SELECT *
        FROM servicos
        WHERE empresa_id = ?
          AND ativo = 1
        ORDER BY nome
        """,
        (empresa_id,),
    ).fetchall()

    funcionarios = conn.execute(
        """
        SELECT *
        FROM funcionarios
        WHERE empresa_id = ?
          AND ativo = 1
        ORDER BY nome
        """,
        (empresa_id,),
    ).fetchall()

    if request.method == "POST":
        cliente_nome = request.form.get(
            "cliente_nome",
            "",
        ).strip()

        cliente_telefone = request.form.get(
            "cliente_telefone",
            "",
        ).strip()

        servico_id = request.form.get(
            "servico_id",
            type=int,
        )

        funcionario_id = request.form.get(
            "funcionario_id",
            type=int,
        )

        data = request.form.get(
            "data",
            "",
        ).strip()

        hora = request.form.get(
            "hora",
            "",
        ).strip()

        if not all([
            cliente_nome,
            cliente_telefone,
            servico_id,
            funcionario_id,
            data,
            hora,
        ]):
            conn.close()

            flash(
                "Preencha todos os campos.",
                "erro",
            )

            return redirect(
                url_for("novo_agendamento")
            )

        servico = conn.execute(
            """
            SELECT id
            FROM servicos
            WHERE id = ?
              AND empresa_id = ?
              AND ativo = 1
            """,
            (
                servico_id,
                empresa_id,
            ),
        ).fetchone()

        funcionario = conn.execute(
            """
            SELECT id
            FROM funcionarios
            WHERE id = ?
              AND empresa_id = ?
              AND ativo = 1
            """,
            (
                funcionario_id,
                empresa_id,
            ),
        ).fetchone()

        if not servico or not funcionario:
            conn.close()

            flash(
                "Serviço ou funcionário inválido.",
                "erro",
            )

            return redirect(
                url_for("novo_agendamento")
            )

        horario_ocupado = conn.execute(
            """
            SELECT id
            FROM agendamentos
            WHERE empresa_id = ?
              AND funcionario_id = ?
              AND data = ?
              AND hora = ?
              AND status != 'cancelado'
            LIMIT 1
            """,
            (
                empresa_id,
                funcionario_id,
                data,
                hora,
            ),
        ).fetchone()

        if horario_ocupado:
            conn.close()

            flash(
                "Este horário já está ocupado para esse barbeiro.",
                "erro",
            )

            return redirect(
                url_for("novo_agendamento")
            )

        try:
            servico_dados = conn.execute(
                "SELECT valor, duracao FROM servicos WHERE id = ?",
                (servico_id,),
            ).fetchone()

            cursor = conn.execute(
                """
                INSERT INTO agendamentos (
                    empresa_id,
                    cliente_nome,
                    cliente_telefone,
                    servico_id,
                    funcionario_id,
                    data,
                    hora,
                    status,
                    duracao_total,
                    valor_total
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    empresa_id,
                    cliente_nome,
                    cliente_telefone,
                    servico_id,
                    funcionario_id,
                    data,
                    hora,
                    "agendado",
                    int(servico_dados["duracao"] or 40),
                    float(servico_dados["valor"] or 0),
                ),
            )

            conn.execute(
                """
                INSERT INTO agendamento_servicos (agendamento_id, servico_id)
                VALUES (?, ?)
                """,
                (cursor.lastrowid, servico_id),
            )

            conn.commit()
            conn.close()

            flash(
                "Agendamento cadastrado com sucesso.",
                "sucesso",
            )

            return redirect(
                url_for(
                    "admin_agenda",
                    data=data,
                    funcionario_id=funcionario_id,
                )
            )

        except sqlite3.IntegrityError:
            conn.close()

            flash(
                "Este horário acabou de ser ocupado.",
                "erro",
            )

            return redirect(
                url_for("novo_agendamento")
            )

    conn.close()

    horarios = gerar_horarios()

    return render_template(
        "admin/agendamento_novo.html",
        servicos=servicos,
        funcionarios=funcionarios,
        horarios=horarios,
        data_hoje=date.today().isoformat(),
    )

if __name__ == "__main__":
    app.run(debug=True)