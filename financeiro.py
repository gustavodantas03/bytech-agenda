"""Regras financeiras do SaaS Bytech Agenda."""
from calendar import monthrange
from datetime import date, datetime


def _data(valor):
    if not valor:
        return None
    if isinstance(valor, date):
        return valor
    try:
        return datetime.strptime(str(valor)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def vencimento_mes(ano, mes, dia):
    ultimo = monthrange(ano, mes)[1]
    return date(ano, mes, min(max(int(dia or 10), 1), ultimo))


def proximo_mes(data_base):
    if data_base.month == 12:
        return date(data_base.year + 1, 1, 1)
    return date(data_base.year, data_base.month + 1, 1)


def registrar_log(conn, empresa_id, acao, descricao, cobranca_id=None, pagamento_id=None):
    conn.execute(
        """INSERT INTO logs_financeiros
        (empresa_id,cobranca_id,pagamento_id,acao,descricao) VALUES (?,?,?,?,?)""",
        (empresa_id, cobranca_id, pagamento_id, acao, descricao),
    )


def garantir_cobranca_competencia(conn, empresa, ano, mes):
    valor = float(empresa["mensalidade"] or 0)
    if valor <= 0:
        return None
    vencimento = vencimento_mes(ano, mes, empresa["dia_vencimento"] or 10)
    competencia = vencimento.strftime("%Y-%m")
    existente = conn.execute(
        "SELECT * FROM cobrancas WHERE empresa_id=? AND competencia=?",
        (empresa["id"], competencia),
    ).fetchone()
    if existente:
        return existente
    cursor = conn.execute(
        """INSERT INTO cobrancas
        (empresa_id,competencia,descricao,valor,valor_final,vencimento,status)
        VALUES (?,?,?,?,?,?,'aberta')""",
        (empresa["id"], competencia, f"Mensalidade {competencia}", valor, valor, vencimento.isoformat()),
    )
    cobranca_id = cursor.lastrowid
    registrar_log(conn, empresa["id"], "cobranca_gerada", f"Cobrança {competencia} gerada no valor de R$ {valor:.2f}.", cobranca_id=cobranca_id)
    return conn.execute("SELECT * FROM cobrancas WHERE id=?", (cobranca_id,)).fetchone()


def garantir_cobranca_atual(conn, empresa, hoje=None):
    hoje = hoje or date.today()
    return garantir_cobranca_competencia(conn, empresa, hoje.year, hoje.month)


def calcular_status(vencimento, pago, tolerancia, bloqueio, hoje=None):
    hoje = hoje or date.today()
    if pago:
        return "em_dia", 0, False
    vencimento = _data(vencimento)
    if not vencimento or hoje <= vencimento:
        return "em_dia", 0, False
    atraso = (hoje - vencimento).days
    status = "pendente" if atraso <= int(tolerancia or 5) else "inadimplente"
    bloquear = atraso >= int(bloqueio or 15)
    return status, atraso, bloquear


def atualizar_empresa_financeiro(conn, empresa_id, hoje=None, criar_cobranca=True):
    hoje = hoje or date.today()
    empresa = conn.execute("SELECT * FROM empresas WHERE id=?", (empresa_id,)).fetchone()
    if not empresa:
        return None
    if criar_cobranca:
        garantir_cobranca_atual(conn, empresa, hoje)
    cobranca = conn.execute(
        """SELECT * FROM cobrancas WHERE empresa_id=? AND status NOT IN ('paga','cancelada')
        ORDER BY vencimento ASC LIMIT 1""", (empresa_id,)
    ).fetchone()
    if cobranca:
        status, atraso, bloquear = calcular_status(
            cobranca["vencimento"], False, empresa["tolerancia_dias"], empresa["bloquear_apos_dias"], hoje
        )
        status_cobranca = "vencida" if status in ("pendente","inadimplente") else "aberta"
        conn.execute("UPDATE cobrancas SET status=?, atualizado_em=CURRENT_TIMESTAMP WHERE id=?", (status_cobranca,cobranca["id"]))
        proximo_vencimento = cobranca["vencimento"]
    else:
        status, atraso, bloquear = "em_dia", 0, False
        atual = vencimento_mes(hoje.year, hoje.month, empresa["dia_vencimento"] or 10)
        base = proximo_mes(atual)
        proximo_vencimento = vencimento_mes(base.year, base.month, empresa["dia_vencimento"] or 10).isoformat()
    bloqueio_manual = int(empresa["bloqueio_manual"] or 0)
    bloqueado_anterior = int(empresa["bloqueado_financeiro"] or 0)
    bloqueado_financeiro = 1 if bloquear else 0
    ativo = 0 if (bloqueio_manual or bloqueado_financeiro) else 1
    conn.execute(
        """UPDATE empresas SET status_pagamento=?,dias_atraso=?,bloqueado_financeiro=?,
        ativo=?,proximo_vencimento=?,financeiro_atualizado_em=CURRENT_TIMESTAMP WHERE id=?""",
        (status,atraso,bloqueado_financeiro,ativo,proximo_vencimento,empresa_id),
    )
    if bloqueado_financeiro != bloqueado_anterior:
        acao = "bloqueio_automatico" if bloqueado_financeiro else "desbloqueio_automatico"
        texto = "Empresa bloqueada automaticamente por inadimplência." if bloqueado_financeiro else "Empresa desbloqueada automaticamente."
        registrar_log(conn, empresa_id, acao, texto, cobranca_id=cobranca["id"] if cobranca else None)
    return {"status":status,"dias_atraso":atraso,"bloqueado_financeiro":bool(bloqueado_financeiro),"ativo":bool(ativo)}


def atualizar_todas_empresas(conn, hoje=None):
    for item in conn.execute("SELECT id FROM empresas").fetchall():
        atualizar_empresa_financeiro(conn, item["id"], hoje=hoje)
    conn.commit()


def registrar_pagamento(
    conn,
    cobranca_id,
    valor=None,
    data_pagamento=None,
    forma="Pix",
    observacoes="",
    desconto=0,
    acrescimo=0,
):
    cobranca = conn.execute("SELECT * FROM cobrancas WHERE id=?", (cobranca_id,)).fetchone()
    if not cobranca:
        raise ValueError("Cobrança não encontrada.")
    if cobranca["status"] == "paga":
        raise ValueError("Esta cobrança já foi paga.")
    if cobranca["status"] == "cancelada":
        raise ValueError("Uma cobrança cancelada não pode ser paga.")

    valor_original = float(cobranca["valor"] or 0)
    desconto = float(desconto or 0)
    acrescimo = float(acrescimo or 0)
    if desconto < 0 or acrescimo < 0:
        raise ValueError("Desconto e acréscimo não podem ser negativos.")
    if desconto > valor_original + acrescimo:
        raise ValueError("O desconto não pode ser maior que o valor da cobrança somado ao acréscimo.")

    valor_calculado = round(valor_original - desconto + acrescimo, 2)
    valor_informado = float(valor) if valor not in (None, "") else valor_calculado
    if abs(valor_informado - valor_calculado) > 0.01:
        raise ValueError("O valor final informado não corresponde ao cálculo de desconto e acréscimo.")
    if valor_calculado <= 0:
        raise ValueError("O valor final do pagamento deve ser maior que zero.")

    data_pagamento = str(data_pagamento or date.today().isoformat())[:10]
    if not _data(data_pagamento):
        raise ValueError("Informe uma data de pagamento válida.")
    forma = (forma or "Pix").strip()
    formas_validas = {"Pix", "Cartão", "Dinheiro", "Transferência", "Boleto"}
    if forma not in formas_validas:
        raise ValueError("Forma de pagamento inválida.")

    recibo = f"BY-{datetime.now():%Y%m%d%H%M%S}-{cobranca_id:05d}"
    cursor = conn.execute(
        """INSERT INTO pagamentos
        (empresa_id,cobranca_id,valor,valor_original,desconto,acrescimo,valor_final,
         data_pagamento,forma_pagamento,observacoes,recibo_numero)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            cobranca["empresa_id"], cobranca_id, valor_calculado, valor_original,
            desconto, acrescimo, valor_calculado, data_pagamento, forma,
            observacoes, recibo,
        ),
    )
    pagamento_id = cursor.lastrowid
    conn.execute(
        """UPDATE cobrancas
        SET status='paga', desconto=?, acrescimo=?, valor_final=?, atualizado_em=CURRENT_TIMESTAMP
        WHERE id=?""",
        (desconto, acrescimo, valor_calculado, cobranca_id),
    )
    conn.execute(
        "UPDATE empresas SET ultimo_pagamento=? WHERE id=?",
        (data_pagamento, cobranca["empresa_id"]),
    )
    detalhes = f"Pagamento de R$ {valor_calculado:.2f} registrado via {forma}"
    if desconto:
        detalhes += f", com desconto de R$ {desconto:.2f}"
    if acrescimo:
        detalhes += f", com acréscimo de R$ {acrescimo:.2f}"
    registrar_log(
        conn, cobranca["empresa_id"], "pagamento_registrado", detalhes + ".",
        cobranca_id, pagamento_id,
    )
    atualizar_empresa_financeiro(conn, cobranca["empresa_id"])
    empresa = conn.execute("SELECT * FROM empresas WHERE id=?", (cobranca["empresa_id"],)).fetchone()
    base = proximo_mes(_data(cobranca["vencimento"]))
    garantir_cobranca_competencia(conn, empresa, base.year, base.month)
    return pagamento_id


def estornar_pagamento(conn, pagamento_id, motivo):
    pagamento = conn.execute("SELECT * FROM pagamentos WHERE id=?",(pagamento_id,)).fetchone()
    if not pagamento:
        raise ValueError("Pagamento não encontrado.")
    if int(pagamento["estornado"] or 0):
        raise ValueError("Este pagamento já foi estornado.")
    conn.execute("UPDATE pagamentos SET estornado=1,estornado_em=CURRENT_TIMESTAMP,motivo_estorno=? WHERE id=?",(motivo,pagamento_id))
    conn.execute("UPDATE cobrancas SET status='aberta',atualizado_em=CURRENT_TIMESTAMP WHERE id=?",(pagamento["cobranca_id"],))
    registrar_log(conn,pagamento["empresa_id"],"pagamento_estornado",f"Pagamento estornado. Motivo: {motivo}",pagamento["cobranca_id"],pagamento_id)
    atualizar_empresa_financeiro(conn,pagamento["empresa_id"],criar_cobranca=False)
