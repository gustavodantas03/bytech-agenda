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


def _tipo_midia_payload(payload: dict) -> str | None:
    """Identifica se a mensagem é de mídia (áudio, imagem, etc.), sem texto."""
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    message = data.get("message") if isinstance(data.get("message"), dict) else {}
    mapa = {
        "audioMessage": "áudio",
        "imageMessage": "imagem",
        "videoMessage": "vídeo",
        "documentMessage": "documento",
        "stickerMessage": "figurinha",
    }
    for chave, rotulo in mapa.items():
        if chave in message:
            return rotulo
    return None


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
         json.dumps(resultado.data, ensure_ascii=False), resultado.ok),
    )
    return resultado


def _variacoes_nono_digito(numero: str) -> list[str]:
    """Gera variações do número com e sem o 9º dígito (celulares no Brasil),
    pois o WhatsApp nem sempre envia esse dígito de forma consistente."""
    variacoes = {numero}
    # DDD (2 dígitos) + resto do número, sem código do país
    if len(numero) == 11 and numero[2] == "9":
        # Tem o 9º dígito -> gera variação sem ele
        variacoes.add(numero[:2] + numero[3:])
    elif len(numero) == 10:
        # Não tem o 9º dígito -> gera variação com ele
        variacoes.add(numero[:2] + "9" + numero[2:])
    return list(variacoes)


def _agendamento_ativo(conn, empresa_id: int, telefone: str):
    local = telefone[2:] if telefone.startswith("55") else telefone
    candidatos = set(_variacoes_nono_digito(telefone))
    candidatos.update(_variacoes_nono_digito(local))
    candidatos.add(telefone)
    candidatos.add(local)
    placeholders = ",".join("?" for _ in candidatos)
    return conn.execute(
        f"""SELECT a.*, s.nome AS servico_nome, f.nome AS profissional_nome
        FROM agendamentos a
        JOIN servicos s ON s.id=a.servico_id
        LEFT JOIN funcionarios f ON f.id=a.funcionario_id
        WHERE a.empresa_id=?
          AND REPLACE(REPLACE(REPLACE(REPLACE(a.cliente_telefone,'(',''),')',''),'-',''),' ','') IN ({placeholders})
          AND a.status NOT IN ('cancelado','finalizado','concluido','faltou')
          AND CAST(a.data || ' ' || a.hora AS timestamp) >= CAST(? AS timestamp)
        ORDER BY a.data DESC, a.hora DESC, a.id DESC LIMIT 1""",
        (empresa_id, *candidatos, datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
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


def _mensagem_midia_nao_suportada(empresa, tipo_midia: str) -> str:
    nome_empresa = (empresa["nome"] if empresa else "") or "nosso estabelecimento"
    link = _link_agendamento(empresa)
    aviso = f"Recebemos seu {tipo_midia}! No momento ainda não conseguimos processar esse tipo de mensagem automaticamente."
    if link:
        return f"{aviso}\n\nPara marcar um horário na {nome_empresa}, acesse:\n{link}"
    return f"{aviso}\n\nEntre em contato com a {nome_empresa} para agendar."


def processar_webhook(payload: dict, instance_name: str = "") -> dict:
    meta = _metadados_payload(payload)
    texto = _texto_payload(payload)
    tipo_midia = _tipo_midia_payload(payload) if not texto else None
    evento = str(payload.get("event") or payload.get("type") or "").upper()
    if meta["from_me"] or not meta["telefone"] or "@g.us" in meta["remote"]:
        return {"ignorado": True}
    if not texto and not tipo_midia:
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

        if tipo_midia:
            try:
                conn.execute(
                    """INSERT INTO whatsapp_webhook_eventos
                    (empresa_id,event_id,evento,telefone,payload_json) VALUES (?,?,?,?,?)""",
                    (config["empresa_id"],event_id,evento,meta["telefone"],json.dumps(payload,ensure_ascii=False)),
                )
                conn.commit()
            except DatabaseIntegrityError:
                conn.rollback()
                return {"duplicado":True}
            empresa = conn.execute(
                "SELECT nome, slug FROM empresas WHERE id=?", (config["empresa_id"],)
            ).fetchone()
            _enviar(
                conn, config, meta["telefone"],
                _mensagem_midia_nao_suportada(empresa, tipo_midia),
                tipo="midia_nao_suportada",
            )
            conn.commit()
            return {"processado": True, "acao": "midia_recebida", "tipo_midia": tipo_midia}
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
            # Remove lembretes pendentes/já enviados do horário antigo, para que
            # novos lembretes (24h/2h) sejam gerados com base na nova data/hora.
            conn.execute(
                "DELETE FROM whatsapp_fila WHERE agendamento_id=? AND tipo IN ('lembrete_24h','lembrete_2h')",
                (agendamento["id"],),
            )
            _salvar_sessao(conn,config["empresa_id"],meta["telefone"],agendamento["id"],"FINALIZADO",{})
            _enviar(conn,config,meta["telefone"],f"Reagendamento concluído! ✅\nNova data: {datetime.strptime(dados['data'],'%Y-%m-%d').strftime('%d/%m/%Y')}\nHorário: {hora}",agendamento["id"],"reagendamento_confirmado")
            conn.commit(); return {"processado":True,"acao":"reagendado"}

        palavras_confirmar = {"1", "confirmar", "confirmo", "confirmado", "confirma", "ok", "sim"}
        palavras_reagendar = {"2", "reagendar", "remarcar", "reagenda", "remarca", "mudar", "trocar", "alterar"}
        palavras_cancelar = {"3", "cancelar", "cancela", "cancelado"}

        def _contem_palavra(texto: str, palavras: set) -> bool:
            if texto in palavras:
                return True
            tokens = set(texto.replace(",", " ").replace(".", " ").split())
            return bool(tokens & palavras)

        if _contem_palavra(resposta, palavras_confirmar):
            conn.execute("UPDATE agendamentos SET status='confirmado' WHERE id=? AND empresa_id=?",(agendamento["id"],config["empresa_id"]))
            _salvar_sessao(conn,config["empresa_id"],meta["telefone"],agendamento["id"],"FINALIZADO",{})
            _enviar(conn,config,meta["telefone"],"Obrigado! Seu agendamento está confirmado. ✅",agendamento["id"],"confirmacao_recebida")
            acao="confirmado"
        elif _contem_palavra(resposta, palavras_reagendar):
            _salvar_sessao(conn,config["empresa_id"],meta["telefone"],agendamento["id"],"ESCOLHENDO_DATA",{})
            _enviar(conn,config,meta["telefone"],"Claro! Envie a nova data no formato DD/MM, por exemplo 05/08.",agendamento["id"],"inicio_reagendamento")
            acao="reagendamento_iniciado"
        elif _contem_palavra(resposta, palavras_cancelar):
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
