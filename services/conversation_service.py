"""Processamento bidirecional das respostas recebidas pela Evolution API."""
from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta

from database import DatabaseIntegrityError, get_connection
from config import Config
from services.evolution_api import cliente_evolution_para_config, normalizar_numero_whatsapp


def _texto_payload(payload: dict) -> str:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    message = data.get("message") if isinstance(data.get("message"), dict) else {}
    return str(
        message.get("conversation")
        or (message.get("extendedTextMessage") or {}).get("text")
        or (message.get("buttonsResponseMessage") or {}).get("selectedButtonId")
        or (message.get("listResponseMessage") or {}).get("singleSelectReply", {}).get("selectedRowId")
        or data.get("body")
        or data.get("text")
        or ""
    ).strip()


def _metadados_payload(payload: dict) -> dict:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    key = data.get("key") if isinstance(data.get("key"), dict) else {}
    remote = str(key.get("remoteJid") or data.get("remoteJid") or data.get("sender") or "")
    telefone = normalizar_numero_whatsapp(remote.split("@")[0].split(":")[0])
    event_id = str(key.get("id") or data.get("id") or payload.get("id") or "")
    from_me = bool(key.get("fromMe") or data.get("fromMe"))
    return {"telefone": telefone, "event_id": event_id, "from_me": from_me, "remote": remote}


def _enviar(conn, config, telefone: str, mensagem: str, agendamento_id=None, tipo="resposta_automatica"):
    resultado = cliente_evolution_para_config(config).enviar_texto(
        config["instance_name"], telefone, mensagem
    )
    conn.execute(
        """INSERT INTO whatsapp_historico
        (empresa_id,agendamento_id,tipo,telefone,mensagem,status,erro,resposta_api,enviado_em)
        VALUES (?,?,?,?,?,?,?,?,CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE NULL END)""",
        (config["empresa_id"], agendamento_id, tipo, telefone, mensagem,
         "enviado" if resultado.ok else "erro", resultado.error,
         json.dumps(resultado.data, ensure_ascii=False), 1 if resultado.ok else 0),
    )
    return resultado


def _agendamento_ativo(conn, empresa_id: int, telefone: str):
    local = telefone[2:] if telefone.startswith("55") else telefone
    return conn.execute(
        """SELECT a.*, s.nome AS servico_nome, f.nome AS profissional_nome
        FROM agendamentos a
        JOIN servicos s ON s.id=a.servico_id
        LEFT JOIN funcionarios f ON f.id=a.funcionario_id
        WHERE a.empresa_id=?
          AND REPLACE(REPLACE(REPLACE(REPLACE(a.cliente_telefone,'(',''),')',''),'-',''),' ','') IN (?,?)
          AND a.status NOT IN ('cancelado','finalizado','concluido','faltou')
        ORDER BY a.data DESC, a.hora DESC, a.id DESC LIMIT 1""",
        (empresa_id, telefone, local),
    ).fetchone()


def _salvar_sessao(conn, empresa_id, telefone, agendamento_id, estado, dados=None):
    existente = conn.execute(
        "SELECT id FROM whatsapp_sessoes WHERE empresa_id=? AND telefone=?",
        (empresa_id, telefone),
    ).fetchone()
    payload = json.dumps(dados or {}, ensure_ascii=False)
    if existente:
        conn.execute(
            """UPDATE whatsapp_sessoes SET agendamento_id=?,estado=?,dados_json=?,
               atualizado_em=CURRENT_TIMESTAMP WHERE id=?""",
            (agendamento_id, estado, payload, existente["id"]),
        )
    else:
        conn.execute(
            """INSERT INTO whatsapp_sessoes
            (empresa_id,telefone,agendamento_id,estado,dados_json) VALUES (?,?,?,?,?)""",
            (empresa_id, telefone, agendamento_id, estado, payload),
        )


def _parse_data(texto: str):
    texto = texto.strip().lower()
    hoje = date.today()
    if texto in {"hoje"}: return hoje
    if texto in {"amanha", "amanhã"}: return hoje + timedelta(days=1)
    m = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?", texto)
    if not m: return None
    d, mes, ano = int(m.group(1)), int(m.group(2)), m.group(3)
    ano = hoje.year if not ano else int(ano) + (2000 if len(ano)==2 else 0)
    try: return date(ano, mes, d)
    except ValueError: return None


def _horarios_livres(conn, agendamento, nova_data: str):
    duracao = int(agendamento["duracao_total"] or 40)
    existentes = conn.execute(
        """SELECT hora,COALESCE(duracao_total,40) duracao_total FROM agendamentos
        WHERE empresa_id=? AND funcionario_id=? AND data=? AND status!='cancelado' AND id!=?""",
        (agendamento["empresa_id"], agendamento["funcionario_id"], nova_data, agendamento["id"]),
    ).fetchall()
    livres=[]
    inicio=datetime.strptime("09:00","%H:%M")
    fim=datetime.strptime("18:00","%H:%M")
    atual=inicio
    while atual+timedelta(minutes=duracao)<=fim:
        conflito=False
        for item in existentes:
            ei=datetime.strptime(item["hora"],"%H:%M")
            ef=ei+timedelta(minutes=int(item["duracao_total"] or 40))
            if atual < ef and atual+timedelta(minutes=duracao) > ei:
                conflito=True; break
        if not conflito: livres.append(atual.strftime("%H:%M"))
        atual += timedelta(minutes=40)
    return livres


def _link_agendamento(empresa) -> str:
    slug = empresa["slug"] if empresa else ""
    if not slug:
        return ""
    base = (Config.PUBLIC_URL or "").rstrip("/")
    return f"{base}/{slug}/agendar" if base else f"/{slug}/agendar"


def _mensagem_direcionar_agendamento(empresa) -> str:
    nome_empresa = (empresa["nome"] if empresa else "") or "nosso estabelecimento"
    link = _link_agendamento(empresa)
    if link:
        return (
            f"Olá! 👋 Não encontrei um agendamento ativo para este número na {nome_empresa}.\n\n"
            f"Para marcar um horário, acesse:\n{link}"
        )
    return (
        f"Olá! 👋 Não encontrei um agendamento ativo para este número na {nome_empresa}. "
        "Entre em contacto com o estabelecimento para agendar."
    )


def processar_webhook(payload: dict, instance_name: str = "") -> dict:
    meta = _metadados_payload(payload)
    texto = _texto_payload(payload)
    evento = str(payload.get("event") or payload.get("type") or "").upper()
    if meta["from_me"] or not texto or not meta["telefone"] or "@g.us" in meta["remote"]:
        return {"ignorado": True}

    conn=get_connection()
    try:
        config=conn.execute(
            "SELECT * FROM whatsapp_configuracoes WHERE instance_name=?",
            (instance_name or str(payload.get("instance") or ""),),
        ).fetchone()
        if not config:
            return {"erro":"Instância não vinculada.","status":404}
        event_id=meta["event_id"] or f"{config['empresa_id']}:{meta['telefone']}:{hash(json.dumps(payload,sort_keys=True,default=str))}"
        try:
            conn.execute(
                """INSERT INTO whatsapp_webhook_eventos
                (empresa_id,event_id,evento,telefone,payload_json) VALUES (?,?,?,?,?)""",
                (config["empresa_id"],event_id,evento,meta["telefone"],json.dumps(payload,ensure_ascii=False)),
            )
            conn.commit()
        except DatabaseIntegrityError:
            conn.rollback(); return {"duplicado":True}

        conn.execute(
            """INSERT INTO whatsapp_historico
            (empresa_id,tipo,telefone,mensagem,status,resposta_api,enviado_em)
            VALUES (?,?,?,?, 'recebido', ?, CURRENT_TIMESTAMP)""",
            (config["empresa_id"],"mensagem_recebida",meta["telefone"],texto,json.dumps(payload,ensure_ascii=False)),
        )
        sessao=conn.execute(
            "SELECT * FROM whatsapp_sessoes WHERE empresa_id=? AND telefone=?",
            (config["empresa_id"],meta["telefone"]),
        ).fetchone()
        agendamento=_agendamento_ativo(conn,config["empresa_id"],meta["telefone"])
        if not agendamento:
            reenviar = True
            if sessao and sessao["estado"] == "SEM_AGENDAMENTO_LINK_ENVIADO":
                try:
                    ultimo_envio = datetime.strptime((sessao["atualizado_em"] or "")[:19], "%Y-%m-%d %H:%M:%S")
                    reenviar = (datetime.now() - ultimo_envio) >= timedelta(hours=6)
                except (TypeError, ValueError):
                    reenviar = True
            if reenviar:
                empresa = conn.execute(
                    "SELECT nome, slug FROM empresas WHERE id=?", (config["empresa_id"],)
                ).fetchone()
                _enviar(conn,config,meta["telefone"],_mensagem_direcionar_agendamento(empresa),tipo="direcionamento_agendamento")
                _salvar_sessao(conn,config["empresa_id"],meta["telefone"],None,"SEM_AGENDAMENTO_LINK_ENVIADO",{})
            conn.commit(); return {"processado":True,"acao":"sem_agendamento"}

        estado=sessao["estado"] if sessao else "AGUARDANDO_CONFIRMACAO"
        resposta=texto.strip().lower()
        if estado == "ESCOLHENDO_DATA":
            nova=_parse_data(resposta)
            if not nova or nova < date.today():
                _enviar(conn,config,meta["telefone"],"Data inválida. Envie no formato DD/MM, por exemplo 05/08.",agendamento["id"])
                conn.commit(); return {"processado":True,"acao":"data_invalida"}
            livres=_horarios_livres(conn,agendamento,nova.isoformat())
            if not livres:
                _enviar(conn,config,meta["telefone"],"Não há horários disponíveis nessa data. Envie outra data no formato DD/MM.",agendamento["id"])
            else:
                _salvar_sessao(conn,config["empresa_id"],meta["telefone"],agendamento["id"],"ESCOLHENDO_HORARIO",{"data":nova.isoformat(),"horarios":livres})
                _enviar(conn,config,meta["telefone"],"Horários disponíveis em " + nova.strftime("%d/%m") + ":\n" + "\n".join(livres) + "\n\nResponda com o horário desejado.",agendamento["id"])
            conn.commit(); return {"processado":True,"acao":"data_reagendamento"}
        if estado == "ESCOLHENDO_HORARIO":
            dados=json.loads(sessao["dados_json"] or "{}")
            hora=re.sub(r"[^0-9:]","",resposta)
            if re.fullmatch(r"\d{4}",hora): hora=hora[:2]+":"+hora[2:]
            if hora not in dados.get("horarios",[]):
                _enviar(conn,config,meta["telefone"],"Horário indisponível. Escolha um dos horários enviados.",agendamento["id"])
                conn.commit(); return {"processado":True,"acao":"horario_invalido"}
            conn.execute("UPDATE agendamentos SET data=?,hora=?,status='confirmado' WHERE id=? AND empresa_id=?",(dados["data"],hora,agendamento["id"],config["empresa_id"]))
            _salvar_sessao(conn,config["empresa_id"],meta["telefone"],agendamento["id"],"FINALIZADO",{})
            _enviar(conn,config,meta["telefone"],f"Reagendamento concluído! ✅\nNova data: {datetime.strptime(dados['data'],'%Y-%m-%d').strftime('%d/%m/%Y')}\nHorário: {hora}",agendamento["id"],"reagendamento_confirmado")
            conn.commit(); return {"processado":True,"acao":"reagendado"}

        if resposta in {"1","confirmar","confirmo"}:
            conn.execute("UPDATE agendamentos SET status='confirmado' WHERE id=? AND empresa_id=?",(agendamento["id"],config["empresa_id"]))
            _salvar_sessao(conn,config["empresa_id"],meta["telefone"],agendamento["id"],"FINALIZADO",{})
            _enviar(conn,config,meta["telefone"],"Obrigado! Seu agendamento está confirmado. ✅",agendamento["id"],"confirmacao_recebida")
            acao="confirmado"
        elif resposta in {"2","reagendar"}:
            _salvar_sessao(conn,config["empresa_id"],meta["telefone"],agendamento["id"],"ESCOLHENDO_DATA",{})
            _enviar(conn,config,meta["telefone"],"Claro! Envie a nova data no formato DD/MM, por exemplo 05/08.",agendamento["id"],"inicio_reagendamento")
            acao="reagendamento_iniciado"
        elif resposta in {"3","cancelar"}:
            conn.execute("UPDATE agendamentos SET status='cancelado' WHERE id=? AND empresa_id=?",(agendamento["id"],config["empresa_id"]))
            _salvar_sessao(conn,config["empresa_id"],meta["telefone"],agendamento["id"],"FINALIZADO",{})
            _enviar(conn,config,meta["telefone"],"Seu agendamento foi cancelado. O horário já foi liberado. Esperamos atendê-lo em breve.",agendamento["id"],"cancelamento_recebido")
            acao="cancelado"
        else:
            _enviar(conn,config,meta["telefone"],"Não entendi. Responda com:\n1 - Confirmar\n2 - Reagendar\n3 - Cancelar",agendamento["id"])
            acao="opcao_invalida"
        conn.commit(); return {"processado":True,"acao":acao,"agendamento_id":agendamento["id"]}
    finally:
        conn.close()
