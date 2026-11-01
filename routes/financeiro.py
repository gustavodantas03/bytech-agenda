# Financeiro do estabelecimento: painel somente leitura, isolado por empresa.
from datetime import date, datetime, timedelta
from flask import abort
from core import *  # noqa: F401,F403


def _periodo():
    hoje = date.today()
    primeiro = hoje.replace(day=1)
    inicio = request.args.get('inicio', primeiro.isoformat()).strip()
    fim = request.args.get('fim', hoje.isoformat()).strip()
    try:
        di = date.fromisoformat(inicio)
        df = date.fromisoformat(fim)
        if di > df or (df-di).days > 366:
            raise ValueError()
    except (ValueError, TypeError):
        di, df = primeiro, hoje
    return di, df


@app.route('/admin/financeiro')
@login_required
def admin_financeiro():
    if session.get('papel') == 'colaborador' and 'relatorios' not in session.get('permissoes', []):
        abort(403)
    empresa_id = session['empresa_id']
    inicio, fim = _periodo()
    conn = get_connection()
    try:
        resumo = conn.execute("""
            SELECT COUNT(DISTINCT v.id) AS quantidade,
                   COALESCE(SUM(vp.valor), 0) AS recebido
            FROM vendas v
            JOIN venda_pagamentos vp ON vp.venda_id=v.id AND vp.empresa_id=v.empresa_id
            WHERE v.empresa_id=? AND v.status='finalizada'
              AND vp.criado_em >= ? AND vp.criado_em < ?
        """, (empresa_id, inicio.isoformat(), (fim+timedelta(days=1)).isoformat())).fetchone()
        formas = conn.execute("""
            SELECT vp.forma, COALESCE(SUM(vp.valor),0) AS total
            FROM venda_pagamentos vp
            JOIN vendas v ON v.id=vp.venda_id AND v.empresa_id=vp.empresa_id
            WHERE v.empresa_id=? AND v.status='finalizada'
              AND vp.criado_em >= ? AND vp.criado_em < ?
            GROUP BY vp.forma ORDER BY total DESC
        """, (empresa_id, inicio.isoformat(), (fim+timedelta(days=1)).isoformat())).fetchall()
        dias = conn.execute("""
            SELECT CAST(vp.criado_em AS DATE) AS dia, SUM(vp.valor) AS total
            FROM venda_pagamentos vp
            JOIN vendas v ON v.id=vp.venda_id AND v.empresa_id=vp.empresa_id
            WHERE v.empresa_id=? AND v.status='finalizada'
              AND vp.criado_em >= ? AND vp.criado_em < ?
            GROUP BY CAST(vp.criado_em AS DATE) ORDER BY dia
        """, (empresa_id, inicio.isoformat(), (fim+timedelta(days=1)).isoformat())).fetchall()
        recentes = conn.execute("""
            SELECT v.id, v.finalizado_em, v.total, v.responsavel,
                   COALESCE(STRING_AGG(DISTINCT vp.forma, ', '), 'Não informado') AS forma
            FROM vendas v
            LEFT JOIN venda_pagamentos vp ON vp.venda_id=v.id AND vp.empresa_id=v.empresa_id
            WHERE v.empresa_id=? AND v.status='finalizada'
              AND v.finalizado_em >= ? AND v.finalizado_em < ?
            GROUP BY v.id, v.finalizado_em, v.total, v.responsavel
            ORDER BY v.finalizado_em DESC LIMIT 12
        """, (empresa_id, inicio.isoformat(), (fim+timedelta(days=1)).isoformat())).fetchall()
        previstos = conn.execute("""
            SELECT COALESCE(SUM(valor_total),0) AS total, COUNT(*) AS quantidade
            FROM agendamentos
            WHERE empresa_id=? AND data BETWEEN ? AND ?
              AND LOWER(COALESCE(status,'agendado')) NOT IN ('cancelado','cancelada')
        """, (empresa_id, inicio.isoformat(), fim.isoformat())).fetchone()
        despesas_resumo = conn.execute("""
            SELECT COALESCE(SUM(CASE WHEN status='paga' AND data_pagamento BETWEEN ? AND ?
                                     THEN valor ELSE 0 END),0) AS pagas,
                   COALESCE(SUM(CASE WHEN status='pendente' THEN valor ELSE 0 END),0) AS pendentes,
                   COALESCE(SUM(CASE WHEN status='pendente' AND vencimento < ?
                                     THEN valor ELSE 0 END),0) AS vencidas
              FROM financeiro_despesas WHERE empresa_id=?
        """, (inicio.isoformat(), fim.isoformat(), date.today().isoformat(), empresa_id)).fetchone()
    finally:
        conn.close()
    despesas_pagas = float(despesas_resumo['pagas'] or 0)
    contas_pendentes = float(despesas_resumo['pendentes'] or 0)
    contas_vencidas = float(despesas_resumo['vencidas'] or 0)
    quantidade = int(resumo['quantidade'] or 0)
    recebido = float(resumo['recebido'] or 0)
    hoje_fin = date.today()
    periodos_rapidos = [
        ('Hoje', hoje_fin, hoje_fin),
        ('7 dias', hoje_fin-timedelta(days=6), hoje_fin),
        ('30 dias', hoje_fin-timedelta(days=29), hoje_fin),
        ('Este mês', hoje_fin.replace(day=1), hoje_fin),
    ]
    return render_template('admin/financeiro.html',
        inicio=inicio.isoformat(), fim=fim.isoformat(), periodos_rapidos=periodos_rapidos,
        quantidade=quantidade, recebido=recebido,
        ticket=recebido/quantidade if quantidade else 0,
        formas=formas, dias=dias, recentes=recentes,
        previstos=float(previstos['total'] or 0),
        previstos_quantidade=int(previstos['quantidade'] or 0),
        despesas_pagas=despesas_pagas, saldo_caixa=recebido-despesas_pagas,
        contas_pendentes=contas_pendentes, contas_vencidas=contas_vencidas)


# Despesas do estabelecimento. Todas as operações são isoladas por empresa.
from decimal import Decimal, InvalidOperation
from flask import flash, redirect, url_for

_FIN_CATEGORIAS = ('Aluguel', 'Água', 'Energia', 'Internet', 'Materiais', 'Produtos', 'Salários', 'Comissões', 'Impostos', 'Manutenção', 'Marketing', 'Outros')
_FIN_FORMAS = ('Pix', 'Dinheiro', 'Cartão de débito', 'Cartão de crédito', 'Transferência', 'Boleto', 'Outros')


def _fin_autorizar():
    if session.get('papel') == 'colaborador' and 'relatorios' not in session.get('permissoes', []):
        abort(403)
    return session['empresa_id']


def _fin_data(valor):
    return date.fromisoformat(valor)


def _fin_valor(valor):
    # O formulário envia sempre o padrão brasileiro, por exemplo: 10,00.
    # Não interpretar 10.000 como 10000: formato ambíguo é rejeitado.
    import re
    texto = (valor or '').strip()
    if not re.fullmatch(r'(?:[0-9]{1,10}|[1-9][0-9]{0,2}(?:\.[0-9]{3}){1,3}),[0-9]{2}', texto):
        raise ValueError('Use o formato 10,00')
    numero = Decimal(texto.replace('.', '').replace(',', '.'))
    if not numero.is_finite() or numero <= 0 or numero > Decimal('9999999999.99'):
        raise ValueError('Valor inválido')
    return numero


@app.route('/admin/financeiro/despesas')
@login_required
def admin_financeiro_despesas():
    empresa_id = _fin_autorizar()
    status = request.args.get('status', '').strip()
    if status not in ('', 'pendente', 'paga', 'cancelada', 'vencida'):
        status = ''
    conn = get_connection()
    try:
        registros = conn.execute('''
            SELECT id, descricao, categoria, valor, vencimento, status,
                   data_pagamento, forma_pagamento, observacoes
            FROM financeiro_despesas
            WHERE empresa_id=?
            ORDER BY CASE WHEN status='pendente' THEN 0 ELSE 1 END,
                     vencimento ASC, id DESC
            LIMIT 500
        ''', (empresa_id,)).fetchall()
    finally:
        conn.close()
    hoje = date.today()
    despesas = [d for d in registros if
        (not status or (status == 'vencida' and d['status'] == 'pendente' and d['vencimento'] < hoje)
         or d['status'] == status)]
    pendente = sum(Decimal(str(d['valor'])) for d in registros if d['status'] == 'pendente')
    vencido = sum(Decimal(str(d['valor'])) for d in registros if d['status'] == 'pendente' and d['vencimento'] < hoje)
    return render_template('admin/financeiro_despesas.html', despesas=despesas,
        categorias=_FIN_CATEGORIAS, formas=_FIN_FORMAS, hoje=hoje,
        status_filtro=status, total_pendente=pendente, total_vencido=vencido)


@app.route('/admin/financeiro/despesas/nova', methods=['POST'])
@login_required
def admin_financeiro_despesa_nova():
    empresa_id = _fin_autorizar()
    descricao = request.form.get('descricao', '').strip()
    categoria = request.form.get('categoria', 'Outros').strip()
    observacoes = request.form.get('observacoes', '').strip()
    try:
        if not descricao or len(descricao) > 200 or len(observacoes) > 2000 or categoria not in _FIN_CATEGORIAS:
            raise ValueError('Preencha os campos corretamente')
        valor = _fin_valor(request.form.get('valor'))
        vencimento = _fin_data(request.form.get('vencimento', ''))
    except (ValueError, InvalidOperation, TypeError):
        flash('Confira descrição, categoria, valor e vencimento.', 'erro')
        return redirect(url_for('admin_financeiro_despesas'))
    conn = get_connection()
    try:
        conn.execute('''
            INSERT INTO financeiro_despesas
            (empresa_id, descricao, categoria, valor, vencimento, status, observacoes)
            VALUES (?, ?, ?, ?, ?, 'pendente', ?)
        ''', (empresa_id, descricao, categoria, valor, vencimento.isoformat(), observacoes))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    flash('Conta a pagar cadastrada com sucesso.', 'sucesso')
    return redirect(url_for('admin_financeiro_despesas'))


@app.route('/admin/financeiro/despesas/<int:despesa_id>/pagar', methods=['POST'])
@login_required
def admin_financeiro_despesa_pagar(despesa_id):
    empresa_id = _fin_autorizar()
    forma = request.form.get('forma_pagamento', '').strip()
    try:
        data_pagamento = _fin_data(request.form.get('data_pagamento', ''))
        if forma not in _FIN_FORMAS:
            raise ValueError()
    except (ValueError, TypeError):
        flash('Informe uma data e uma forma de pagamento válidas.', 'erro')
        return redirect(url_for('admin_financeiro_despesas'))
    conn = get_connection()
    try:
        cursor = conn.execute('''
            UPDATE financeiro_despesas
               SET status='paga', data_pagamento=?, forma_pagamento=?, atualizado_em=CURRENT_TIMESTAMP
             WHERE id=? AND empresa_id=? AND status='pendente'
        ''', (data_pagamento.isoformat(), forma, despesa_id, empresa_id))
        atualizado = cursor.rowcount
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    flash('Pagamento registrado.' if atualizado else 'Conta não encontrada ou já processada.',
          'sucesso' if atualizado else 'erro')
    return redirect(url_for('admin_financeiro_despesas'))


@app.route('/admin/financeiro/despesas/<int:despesa_id>/cancelar', methods=['POST'])
@login_required
def admin_financeiro_despesa_cancelar(despesa_id):
    empresa_id = _fin_autorizar()
    conn = get_connection()
    try:
        cursor = conn.execute('''
            UPDATE financeiro_despesas
               SET status='cancelada', atualizado_em=CURRENT_TIMESTAMP
             WHERE id=? AND empresa_id=? AND status='pendente'
        ''', (despesa_id, empresa_id))
        atualizado = cursor.rowcount
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    flash('Conta cancelada.' if atualizado else 'Só é possível cancelar contas pendentes.',
          'sucesso' if atualizado else 'erro')
    return redirect(url_for('admin_financeiro_despesas'))
