"""Painel administrativo da integração WhatsApp/Evolution API."""

from core import *  # noqa: F401,F403
from services.evolution_api import EvolutionClient, garantir_configuracao_empresa


def _dados_modulo(conn, empresa_id):
    garantir_configuracao_empresa(conn, empresa_id)
    config = conn.execute(
        "SELECT * FROM whatsapp_configuracoes WHERE empresa_id = ?", (empresa_id,)
    ).fetchone()
    automacoes = conn.execute(
        "SELECT * FROM whatsapp_automacoes WHERE empresa_id = ?", (empresa_id,)
    ).fetchone()
    modelos = conn.execute(
        "SELECT * FROM whatsapp_modelos WHERE empresa_id = ? ORDER BY id", (empresa_id,)
    ).fetchall()
    historico = conn.execute(
        """
        SELECT h.*, a.cliente_nome
        FROM whatsapp_historico h
        LEFT JOIN agendamentos a ON a.id = h.agendamento_id
        WHERE h.empresa_id = ?
        ORDER BY h.id DESC LIMIT 100
        """,
        (empresa_id,),
    ).fetchall()
    resumo = conn.execute(
        """
        SELECT COUNT(*) total,
               SUM(CASE WHEN status = 'enviado' THEN 1 ELSE 0 END) enviados,
               SUM(CASE WHEN status = 'erro' THEN 1 ELSE 0 END) erros
        FROM whatsapp_historico
        WHERE empresa_id = ? AND CAST(criado_em AS date) = CURRENT_DATE
        """,
        (empresa_id,),
    ).fetchone()
    fila = conn.execute(
        """SELECT COUNT(*) total,
           SUM(CASE WHEN status IN ('pendente','tentando') THEN 1 ELSE 0 END) pendentes,
           SUM(CASE WHEN status='erro' THEN 1 ELSE 0 END) erros
           FROM whatsapp_fila WHERE empresa_id=?""",
        (empresa_id,),
    ).fetchone()
    return config, automacoes, modelos, historico, resumo, fila


@app.route("/admin/comunicacao/whatsapp")
@login_required
@recurso_required("whatsapp")
def admin_whatsapp():
    empresa_id = session["empresa_id"]
    conn = get_connection()
    config, automacoes, modelos, historico, resumo, fila = _dados_modulo(conn, empresa_id)
    conn.close()
    configurado = bool((config["base_url"] or "").strip() and (config["api_key"] or "").strip())
    return render_template(
        "admin/whatsapp.html", config=config, automacoes=automacoes,
        modelos=modelos, historico=historico, resumo=resumo, fila=fila,
        configurado=configurado,
    )


@app.route("/admin/comunicacao/whatsapp/configuracoes", methods=["POST"])
@login_required
@recurso_required("whatsapp")
def salvar_whatsapp_configuracoes():
    empresa_id = session["empresa_id"]
    base_url = request.form.get("base_url", "").strip().rstrip("/")
    if not base_url:
        flash("Informe o endereço da Evolution API.", "erro")
        return redirect(url_for("admin_whatsapp") + "#configuracao-inicial")
    api_key = request.form.get("api_key", "").strip()
    instance_name = request.form.get("instance_name", "").strip()
    timeout = request.form.get("timeout_segundos", type=int) or 15
    conn = get_connection()
    garantir_configuracao_empresa(conn, empresa_id)
    if api_key:
        conn.execute(
            """UPDATE whatsapp_configuracoes SET base_url=?, api_key=?, instance_name=?,
               timeout_segundos=?, atualizado_em=CURRENT_TIMESTAMP WHERE empresa_id=?""",
            (base_url, api_key, instance_name, timeout, empresa_id),
        )
    else:
        conn.execute(
            """UPDATE whatsapp_configuracoes SET base_url=?, instance_name=?,
               timeout_segundos=?, atualizado_em=CURRENT_TIMESTAMP WHERE empresa_id=?""",
            (base_url, instance_name, timeout, empresa_id),
        )
    config_atual = conn.execute(
        "SELECT api_key FROM whatsapp_configuracoes WHERE empresa_id=?", (empresa_id,)
    ).fetchone()
    conn.commit(); conn.close()
    if not config_atual or not (config_atual["api_key"] or "").strip():
        flash("Informe a API Key para concluir a configuração.", "erro")
        return redirect(url_for("admin_whatsapp") + "#configuracao-inicial")
    flash("Configuração salva. Agora conecte o WhatsApp e leia o QR Code.", "sucesso")
    return redirect(url_for("admin_whatsapp") + "#conexao")


@app.route("/admin/comunicacao/whatsapp/automacoes", methods=["POST"])
@login_required
@recurso_required("whatsapp")
def salvar_whatsapp_automacoes():
    empresa_id = session["empresa_id"]
    campos = ["confirmacao", "lembrete_24h", "lembrete_2h", "cancelamento",
              "pos_atendimento", "aniversario", "cliente_inativo"]
    valores = [1 if request.form.get(campo) else 0 for campo in campos]
    conn = get_connection(); garantir_configuracao_empresa(conn, empresa_id)
    conn.execute(
        """UPDATE whatsapp_automacoes SET confirmacao_ativa=?, lembrete_24h_ativo=?,
        lembrete_2h_ativo=?, cancelamento_ativo=?, pos_atendimento_ativo=?,
        aniversario_ativo=?, cliente_inativo_ativo=?, atualizado_em=CURRENT_TIMESTAMP
        WHERE empresa_id=?""", (*valores, empresa_id),
    )
    conn.commit(); conn.close()
    flash("Automações atualizadas.", "sucesso")
    return redirect(url_for("admin_whatsapp") + "#automacoes")


@app.route("/admin/comunicacao/whatsapp/modelos", methods=["POST"])
@login_required
@recurso_required("whatsapp")
def salvar_whatsapp_modelos():
    empresa_id = session["empresa_id"]
    conn = get_connection(); garantir_configuracao_empresa(conn, empresa_id)
    modelos = conn.execute("SELECT id FROM whatsapp_modelos WHERE empresa_id=?", (empresa_id,)).fetchall()
    for modelo in modelos:
        texto = request.form.get(f"mensagem_{modelo['id']}")
        if texto is not None and texto.strip():
            conn.execute("UPDATE whatsapp_modelos SET mensagem=?, atualizado_em=CURRENT_TIMESTAMP WHERE id=? AND empresa_id=?",
                         (texto.strip(), modelo["id"], empresa_id))
    conn.commit(); conn.close()
    flash("Modelos de mensagem salvos.", "sucesso")
    return redirect(url_for("admin_whatsapp") + "#modelos")


@app.route("/admin/comunicacao/whatsapp/conectar", methods=["POST"])
@login_required
@recurso_required("whatsapp")
def conectar_whatsapp():
    empresa_id = session["empresa_id"]
    conn = get_connection(); garantir_configuracao_empresa(conn, empresa_id)
    config = conn.execute("SELECT * FROM whatsapp_configuracoes WHERE empresa_id=?", (empresa_id,)).fetchone()
    if not (config["base_url"] or "").strip() or not (config["api_key"] or "").strip():
        conn.close()
        flash("Configure a URL e a API Key antes de conectar o WhatsApp.", "aviso")
        return redirect(url_for("admin_whatsapp") + "#configuracao-inicial")
    client = EvolutionClient(config["base_url"], config["api_key"], config["timeout_segundos"])
    estado = client.estado(config["instance_name"])
    if not estado.ok and estado.status_code == 404:
        client.criar_instancia(config["instance_name"])
    resultado = client.conectar(config["instance_name"])
    if resultado.ok:
        qrcode = resultado.data.get("base64") or resultado.data.get("code") or resultado.data.get("qrcode", {}).get("base64")
        conn.execute("UPDATE whatsapp_configuracoes SET status='aguardando_qr', qr_code=?, ultima_sincronizacao=CURRENT_TIMESTAMP WHERE empresa_id=?",
                     (qrcode, empresa_id))
        conn.commit(); flash("QR Code gerado. Escaneie com o WhatsApp.", "sucesso")
    else:
        flash(f"Não foi possível conectar: {resultado.error}", "erro")
    conn.close()
    return redirect(url_for("admin_whatsapp"))


@app.route("/admin/comunicacao/whatsapp/status")
@login_required
@recurso_required("whatsapp")
def status_whatsapp():
    empresa_id = session["empresa_id"]
    conn = get_connection(); garantir_configuracao_empresa(conn, empresa_id)
    config = conn.execute("SELECT * FROM whatsapp_configuracoes WHERE empresa_id=?", (empresa_id,)).fetchone()
    if not (config["base_url"] or "").strip() or not (config["api_key"] or "").strip():
        conn.close()
        return jsonify(sucesso=False, configurado=False, status="nao_configurado", erro=None)
    resultado = EvolutionClient(config["base_url"], config["api_key"], config["timeout_segundos"]).estado(config["instance_name"])
    estado = "desconectado"
    if resultado.ok:
        estado = resultado.data.get("instance", {}).get("state") or resultado.data.get("state") or "desconectado"
        estado = "conectado" if estado == "open" else estado
        conn.execute("UPDATE whatsapp_configuracoes SET status=?, ultima_sincronizacao=CURRENT_TIMESTAMP WHERE empresa_id=?", (estado, empresa_id))
        conn.commit()
    conn.close()
    return jsonify(sucesso=resultado.ok, status=estado, erro=resultado.error)


@app.route("/admin/comunicacao/whatsapp/testar", methods=["POST"])
@login_required
@recurso_required("whatsapp")
def testar_whatsapp():
    from services.evolution_api import normalizar_numero_whatsapp
    empresa_id = session["empresa_id"]
    numero = normalizar_numero_whatsapp(request.form.get("numero", ""))
    conn = get_connection(); garantir_configuracao_empresa(conn, empresa_id)
    config = conn.execute("SELECT * FROM whatsapp_configuracoes WHERE empresa_id=?", (empresa_id,)).fetchone()
    if not (config["base_url"] or "").strip() or not (config["api_key"] or "").strip():
        conn.close()
        flash("Conclua a configuração da Evolution API antes de testar o envio.", "aviso")
        return redirect(url_for("admin_whatsapp") + "#configuracao-inicial")
    if not numero:
        conn.close()
        flash("Informe um número de WhatsApp válido.", "erro")
        return redirect(url_for("admin_whatsapp") + "#conexao")
    resultado = EvolutionClient(config["base_url"], config["api_key"], config["timeout_segundos"]).enviar_texto(
        config["instance_name"], numero, "✅ Teste do Bytech Agenda realizado com sucesso!"
    )
    conn.execute("INSERT INTO whatsapp_historico (empresa_id,tipo,telefone,mensagem,status,erro) VALUES (?,?,?,?,?,?)",
                 (empresa_id,"teste",numero,"✅ Teste do Bytech Agenda realizado com sucesso!","enviado" if resultado.ok else "erro",resultado.error))
    conn.commit(); conn.close()
    flash("Mensagem de teste enviada." if resultado.ok else f"Falha no teste: {resultado.error}", "sucesso" if resultado.ok else "erro")
    return redirect(url_for("admin_whatsapp"))


@app.route("/admin/comunicacao/whatsapp/processar", methods=["POST"])
@login_required
@recurso_required("whatsapp")
def processar_whatsapp_manual():
    from services.communication_queue import gerar_lembretes, processar_fila
    lembretes = gerar_lembretes()
    fila = processar_fila()
    flash(f"Processamento concluído: {fila['enviados']} enviada(s), {fila['reprogramados']} reprogramada(s) e {fila['erros']} erro(s).", "sucesso")
    return redirect(url_for("admin_whatsapp") + "#historico")
