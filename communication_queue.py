"""Fila leve de mensagens e lembretes do WhatsApp.

Projetada para SQLite e VPS pequena. O scheduler apenas cria itens; o worker
processa a fila. O agendamento nunca é bloqueado por indisponibilidade da API.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from database import get_connection
from services.evolution_api import (
    cliente_evolution_para_config,
    EvolutionResult,
    _dados_agendamento,
    garantir_configuracao_empresa,
    normalizar_numero_whatsapp,
    renderizar_modelo,
)

CAMPOS_AUTOMACAO = {
    "confirmacao": "confirmacao_ativa",
    "lembrete_24h": "lembrete_24h_ativo",
    "lembrete_2h": "lembrete_2h_ativo",
    "cancelamento": "cancelamento_ativo",
    "pos_atendimento": "pos_atendimento_ativo",
}


def _montar_mensagem(conn, empresa_id: int, agendamento_id: int, tipo: str):
    garantir_configuracao_empresa(conn, empresa_id)
    automacao = conn.execute(
        "SELECT * FROM whatsapp_automacoes WHERE empresa_id=?", (empresa_id,)
    ).fetchone()
    campo = CAMPOS_AUTOMACAO.get(tipo)
    if campo and not automacao[campo]:
        return None, "Automação desativada."

    modelo = conn.execute(
        "SELECT * FROM whatsapp_modelos WHERE empresa_id=? AND tipo=? AND ativo=1",
        (empresa_id, tipo),
    ).fetchone()
    agendamento = _dados_agendamento(conn, empresa_id, agendamento_id)
    if not modelo or not agendamento:
        return None, "Modelo ou agendamento não encontrado."
    if not agendamento["cliente_telefone"]:
        return None, "Cliente sem telefone."

    try:
        data_formatada = datetime.strptime(agendamento["data"], "%Y-%m-%d").strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        data_formatada = agendamento["data"] or ""

    mensagem = renderizar_modelo(modelo["mensagem"], {
        "nome": agendamento["cliente_nome"],
        "empresa": agendamento["empresa_nome"],
        "servico": agendamento["servico_nome"],
        "profissional": agendamento["profissional_nome"] or "",
        "data": data_formatada,
        "hora": agendamento["hora"],
        "telefone_empresa": agendamento["empresa_telefone"] or "",
    })
    return {
        "cliente_id": agendamento["cliente_id"],
        "telefone": normalizar_numero_whatsapp(agendamento["cliente_telefone"]),
        "mensagem": mensagem,
    }, None


def enfileirar_mensagem_agendamento(
    empresa_id: int,
    agendamento_id: int,
    tipo: str,
    agendado_para: datetime | None = None,
) -> EvolutionResult:
    conn = get_connection()
    try:
        dados, erro = _montar_mensagem(conn, empresa_id, agendamento_id, tipo)
        if erro:
            return EvolutionResult(False, {}, error=erro)
        config = conn.execute(
            "SELECT max_tentativas FROM whatsapp_configuracoes WHERE empresa_id=?",
            (empresa_id,),
        ).fetchone()
        momento = (agendado_para or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO whatsapp_fila
            (empresa_id, agendamento_id, cliente_id, tipo, telefone, mensagem,
             status, max_tentativas, agendado_para)
            VALUES (?, ?, ?, ?, ?, ?, 'pendente', ?, ?)
            """,
            (empresa_id, agendamento_id, dados["cliente_id"], tipo,
             dados["telefone"], dados["mensagem"], int(config["max_tentativas"] or 3), momento),
        )
        conn.commit()
        if cursor.rowcount == 0:
            return EvolutionResult(True, {"duplicado": True})
        return EvolutionResult(True, {"fila_id": cursor.lastrowid})
    finally:
        conn.close()


def gerar_lembretes(agora: datetime | None = None) -> dict:
    """Cria lembretes em janelas curtas, com proteção contra duplicidade."""
    agora = agora or datetime.now()
    conn = get_connection()
    criados = 0
    ignorados = 0
    try:
        empresas = conn.execute("SELECT id FROM empresas WHERE ativo=1").fetchall()
        for empresa in empresas:
            empresa_id = empresa["id"]
            garantir_configuracao_empresa(conn, empresa_id)
            auto = conn.execute(
                "SELECT * FROM whatsapp_automacoes WHERE empresa_id=?", (empresa_id,)
            ).fetchone()
            janelas = []
            if auto["lembrete_24h_ativo"]:
                janelas.append(("lembrete_24h", agora + timedelta(hours=23, minutes=55), agora + timedelta(hours=24, minutes=5)))
            if auto["lembrete_2h_ativo"]:
                janelas.append(("lembrete_2h", agora + timedelta(hours=1, minutes=55), agora + timedelta(hours=2, minutes=5)))

            for tipo, inicio, fim in janelas:
                itens = conn.execute(
                    """
                    SELECT id FROM agendamentos
                    WHERE empresa_id=?
                      AND status NOT IN ('cancelado','concluido','faltou')
                      AND CAST(data || ' ' || hora AS timestamp) BETWEEN ? AND ?
                    """,
                    (empresa_id, inicio.strftime("%Y-%m-%d %H:%M:%S"), fim.strftime("%Y-%m-%d %H:%M:%S")),
                ).fetchall()
                for item in itens:
                    result = enfileirar_mensagem_agendamento(empresa_id, item["id"], tipo, agora)
                    if result.ok and not result.data.get("duplicado"):
                        criados += 1
                    else:
                        ignorados += 1
        return {"criados": criados, "ignorados": ignorados}
    finally:
        conn.close()


def processar_fila(limite: int = 30, agora: datetime | None = None) -> dict:
    agora = agora or datetime.now()
    conn = get_connection()
    enviados = erros = reprogramados = 0
    try:
        itens = conn.execute(
            """
            SELECT * FROM whatsapp_fila
            WHERE status IN ('pendente','tentando')
              AND CAST(agendado_para AS timestamp) <= CAST(? AS timestamp)
              AND (proxima_tentativa_em IS NULL OR CAST(proxima_tentativa_em AS timestamp) <= CAST(? AS timestamp))
              AND tentativas < max_tentativas
            ORDER BY id LIMIT ?
            """,
            (agora.strftime("%Y-%m-%d %H:%M:%S"), agora.strftime("%Y-%m-%d %H:%M:%S"), limite),
        ).fetchall()

        for item in itens:
            # Reserva simples para evitar processamento repetido no mesmo ciclo.
            conn.execute(
                "UPDATE whatsapp_fila SET status='tentando', tentativas=tentativas+1, atualizado_em=CURRENT_TIMESTAMP WHERE id=?",
                (item["id"],),
            )
            conn.commit()
            config = conn.execute(
                "SELECT * FROM whatsapp_configuracoes WHERE empresa_id=?", (item["empresa_id"],)
            ).fetchone()
            result = cliente_evolution_para_config(config).enviar_texto(
                config["instance_name"], item["telefone"], item["mensagem"]
            )
            resposta = json.dumps(result.data, ensure_ascii=False)
            if result.ok:
                conn.execute(
                    """UPDATE whatsapp_fila SET status='enviado', enviado_em=CURRENT_TIMESTAMP,
                       ultimo_erro=NULL, resposta_api=?, atualizado_em=CURRENT_TIMESTAMP WHERE id=?""",
                    (resposta, item["id"]),
                )
                conn.execute(
                    """INSERT INTO whatsapp_historico
                    (empresa_id,agendamento_id,cliente_id,tipo,telefone,mensagem,status,resposta_api,enviado_em)
                    VALUES (?,?,?,?,?,?, 'enviado', ?, CURRENT_TIMESTAMP)""",
                    (item["empresa_id"], item["agendamento_id"], item["cliente_id"], item["tipo"], item["telefone"], item["mensagem"], resposta),
                )
                enviados += 1
            else:
                tentativa_atual = int(item["tentativas"] or 0) + 1
                esgotou = tentativa_atual >= int(item["max_tentativas"] or 3)
                status = "erro" if esgotou else "pendente"
                # Retentativas progressivas: 2, 5 e 15 minutos.
                espera = (2, 5, 15)[min(tentativa_atual - 1, 2)]
                proxima = (agora + timedelta(minutes=espera)).strftime("%Y-%m-%d %H:%M:%S")
                conn.execute(
                    """UPDATE whatsapp_fila SET status=?, proxima_tentativa_em=?,
                       ultimo_erro=?, resposta_api=?, atualizado_em=CURRENT_TIMESTAMP WHERE id=?""",
                    (status, None if esgotou else proxima, result.error, resposta, item["id"]),
                )
                if esgotou:
                    conn.execute(
                        """INSERT INTO whatsapp_historico
                        (empresa_id,agendamento_id,cliente_id,tipo,telefone,mensagem,status,erro,resposta_api)
                        VALUES (?,?,?,?,?,?, 'erro', ?, ?)""",
                        (item["empresa_id"], item["agendamento_id"], item["cliente_id"], item["tipo"], item["telefone"], item["mensagem"], result.error, resposta),
                    )
                    erros += 1
                else:
                    reprogramados += 1
            conn.commit()
        return {"processados": len(itens), "enviados": enviados, "erros": erros, "reprogramados": reprogramados}
    finally:
        conn.close()
