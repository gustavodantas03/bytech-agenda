"""Painel administrativo da integração WhatsApp/Evolution API."""

from core import *  # noqa: F401,F403
from services.evolution_api import (
    cliente_evolution_para_config,
    garantir_configuracao_empresa,
    infraestrutura_evolution_configurada,
    normalizar_numero_whatsapp,
    extrair_perfil_instancia,
)


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


def _estado_normalizado(data):
    estado = data.get("instance", {}).get("state") or data.get("state") or "desconectado"
    return "conectado" if estado == "open" else estado


@app.route("/admin/comunicacao/whatsapp")
@login_required
@recurso_required("whatsapp")
def admin_whatsapp():
    empresa_id = session["empresa_id"]
    conn = get_connection()
    config, automacoes, modelos, historico, resumo, fila = _dados_modulo(conn, empresa_id)
    conn.close()
    return render_template(
        "admin/whatsapp.html", config=config, automacoes=automacoes,
        modelos=modelos, historico=historico, resumo=resumo, fila=fila,
        configurado=infraestrutura_evolution_configurada(),
    )


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
    if not infraestrutura_evolution_configurada():
        conn.close()
        flash("A infraestrutura do WhatsApp ainda não foi configurada pela Bytech.", "erro")
        return redirect(url_for("admin_whatsapp"))

    client = cliente_evolution_para_config(config)
    estado = client.estado(config["instance_name"])
    criacao = None
    if not estado.ok:
        criacao = client.criar_instancia(config["instance_name"])
        if not criacao.ok and criacao.status_code not in (400, 409):
            conn.close()
            flash(f"Não foi possível preparar a instância: {criacao.error}", "erro")
            return redirect(url_for("admin_whatsapp"))

    resultado = client.conectar(config["instance_name"])
    dados = resultado.data if resultado.ok else (criacao.data if criacao and criacao.ok else {})
    qrcode = (dados.get("base64") or dados.get("code") or
              dados.get("qrcode", {}).get("base64"))
    if qrcode:
        conn.execute(
            """UPDATE whatsapp_configuracoes SET status='aguardando_qr', qr_code=?,
               ultima_sincronizacao=CURRENT_TIMESTAMP WHERE empresa_id=?""",
            (qrcode, empresa_id),
        )
        conn.commit()
        flash("QR Code gerado. Escaneie com o WhatsApp.", "sucesso")
    else:
        estado_atual = client.estado(config["instance_name"])
        if estado_atual.ok and _estado_normalizado(estado_atual.data) == "conectado":
            conn.execute(
                """UPDATE whatsapp_configuracoes SET status='conectado', qr_code=NULL,
                   ultima_sincronizacao=CURRENT_TIMESTAMP WHERE empresa_id=?""",
                (empresa_id,),
            )
            conn.commit()
            flash("WhatsApp já está conectado.", "sucesso")
        else:
            flash(f"Não foi possível gerar o QR Code: {resultado.error or 'resposta sem QR Code'}", "erro")
    conn.close()
    return redirect(url_for("admin_whatsapp") + "#conexao")


@app.route("/admin/comunicacao/whatsapp/status")
@login_required
@recurso_required("whatsapp")
def status_whatsapp():
    empresa_id = session["empresa_id"]
    conn = get_connection(); garantir_configuracao_empresa(conn, empresa_id)
    config = conn.execute("SELECT * FROM whatsapp_configuracoes WHERE empresa_id=?", (empresa_id,)).fetchone()
    if not infraestrutura_evolution_configurada():
        conn.close()
        return jsonify(sucesso=False, configurado=False, status="nao_configurado", erro=None)
    resultado = cliente_evolution_para_config(config).estado(config["instance_name"])
    estado = "desconectado"
    perfil = {"numero": "", "nome": "", "foto": ""}
    if resultado.ok:
        estado = _estado_normalizado(resultado.data)
        qr = None if estado == "conectado" else config["qr_code"]
        if estado == "conectado":
            detalhes = cliente_evolution_para_config(config).detalhes_instancia(config["instance_name"])
            if detalhes.ok:
                perfil = extrair_perfil_instancia(detalhes.data, config["instance_name"])
        conn.execute(
            """UPDATE whatsapp_configuracoes SET status=?, qr_code=?,
               numero_conectado=COALESCE(NULLIF(?, ''), numero_conectado),
               nome_perfil=COALESCE(NULLIF(?, ''), nome_perfil),
               foto_perfil=COALESCE(NULLIF(?, ''), foto_perfil),
               conectado_em=CASE WHEN ?='conectado' THEN COALESCE(conectado_em, CURRENT_TIMESTAMP) ELSE conectado_em END,
               ultima_sincronizacao=CURRENT_TIMESTAMP WHERE empresa_id=?""",
            (estado, qr, perfil["numero"], perfil["nome"], perfil["foto"], estado, empresa_id),
        )
        conn.commit()
    config_atual = conn.execute("SELECT * FROM whatsapp_configuracoes WHERE empresa_id=?", (empresa_id,)).fetchone()
    resposta = {
        "sucesso": resultado.ok, "configurado": True, "status": estado, "erro": resultado.error,
        "numero": config_atual["numero_conectado"] or "",
        "nome": config_atual["nome_perfil"] or "",
        "foto": config_atual["foto_perfil"] or "",
        "ultima_sincronizacao": config_atual["ultima_sincronizacao"] or "",
    }
    conn.close()
    return jsonify(**resposta)


@app.route("/admin/comunicacao/whatsapp/desconectar", methods=["POST"])
@login_required
@recurso_required("whatsapp")
def desconectar_whatsapp():
    empresa_id = session["empresa_id"]
    conn = get_connection(); garantir_configuracao_empresa(conn, empresa_id)
    config = conn.execute("SELECT * FROM whatsapp_configuracoes WHERE empresa_id=?", (empresa_id,)).fetchone()
    resultado = cliente_evolution_para_config(config).logout(config["instance_name"])
    if resultado.ok or resultado.status_code in (400, 404):
        conn.execute(
            """UPDATE whatsapp_configuracoes SET status='desconectado', qr_code=NULL,
               numero_conectado=NULL, nome_perfil=NULL, foto_perfil=NULL, conectado_em=NULL,
               ultima_sincronizacao=CURRENT_TIMESTAMP WHERE empresa_id=?""",
            (empresa_id,),
        )
        conn.commit()
        flash("WhatsApp desconectado.", "sucesso")
    else:
        flash(f"Não foi possível desconectar: {resultado.error}", "erro")
    conn.close()
    return redirect(url_for("admin_whatsapp") + "#conexao")


@app.route("/admin/comunicacao/whatsapp/testar", methods=["POST"])
@login_required
@recurso_required("whatsapp")
def testar_whatsapp():
    empresa_id = session["empresa_id"]
    numero = normalizar_numero_whatsapp(request.form.get("numero", ""))
    conn = get_connection(); garantir_configuracao_empresa(conn, empresa_id)
    config = conn.execute("SELECT * FROM whatsapp_configuracoes WHERE empresa_id=?", (empresa_id,)).fetchone()
    if not infraestrutura_evolution_configurada():
        conn.close(); flash("A infraestrutura do WhatsApp não está configurada.", "erro")
        return redirect(url_for("admin_whatsapp") + "#conexao")
    if not numero:
        conn.close(); flash("Informe um número de WhatsApp válido.", "erro")
        return redirect(url_for("admin_whatsapp") + "#conexao")
    if config["status"] != "conectado":
        conn.close(); flash("Conecte o WhatsApp antes de testar o envio.", "erro")
        return redirect(url_for("admin_whatsapp") + "#conexao")
    mensagem = "✅ Teste do Bytech Agenda realizado com sucesso!"
    resultado = cliente_evolution_para_config(config).enviar_texto(config["instance_name"], numero, mensagem)
    import json
    conn.execute(
        """INSERT INTO whatsapp_historico
           (empresa_id,tipo,telefone,mensagem,status,erro,resposta_api,enviado_em)
           VALUES (?,?,?,?,?,?,?,CASE WHEN ?='enviado' THEN CURRENT_TIMESTAMP ELSE NULL END)""",
        (empresa_id, "teste", numero, mensagem, "enviado" if resultado.ok else "erro",
         resultado.error, json.dumps(resultado.data, ensure_ascii=False),
         "enviado" if resultado.ok else "erro"),
    )
    conn.commit(); conn.close()
    flash("Mensagem de teste enviada." if resultado.ok else f"Falha no envio: {resultado.error}",
          "sucesso" if resultado.ok else "erro")
    return redirect(url_for("admin_whatsapp") + "#conexao")


@app.route("/admin/comunicacao/whatsapp/processar", methods=["POST"])
@login_required
@recurso_required("whatsapp")
def processar_whatsapp_manual():
    from services.communication_queue import processar_fila
    resultado = processar_fila()
    flash(f"Fila processada: {resultado['enviados']} enviada(s), {resultado['reprogramados']} reagendada(s) e {resultado['erros']} erro(s).", "sucesso")
    return redirect(url_for("admin_whatsapp") + "#historico")
