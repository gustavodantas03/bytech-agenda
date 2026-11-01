# Etapa 3 - financeiro por estabelecimento
from core import *  # noqa
from flask import abort, flash, redirect, url_for, Response
from datetime import date, timedelta
from calendar import monthrange
from decimal import Decimal, InvalidOperation
import csv, io
from routes.financeiro import _fin_autorizar, _fin_valor, _fin_data, _FIN_CATEGORIAS, _FIN_FORMAS


def _mes(base, offset):
    y = base.year + (base.month - 1 + offset) // 12
    m = (base.month - 1 + offset) % 12 + 1
    return date(y, m, min(base.day, monthrange(y, m)[1]))


def _gerar_recorrentes(empresa_id):
    # Gera ocorrências sem duplicar nem editar lançamentos existentes.
    hoje = date.today()
    conn = get_connection()
    try:
        planos = conn.execute('''SELECT id, descricao, categoria, valor, dia_vencimento, observacoes, inicio
            FROM financeiro_recorrencias WHERE empresa_id=? AND ativo=TRUE''', (empresa_id,)).fetchall()
        for plano in planos:
            for deslocamento in range(12):
                competencia = _mes(hoje.replace(day=1), deslocamento)
                if competencia < plano['inicio'].replace(day=1):
                    continue
                venc = competencia.replace(day=min(int(plano['dia_vencimento']), monthrange(competencia.year, competencia.month)[1]))
                conn.execute('''INSERT INTO financeiro_despesas
                  (empresa_id, descricao, categoria, valor, vencimento, status, observacoes, recorrencia_id, competencia)
                  VALUES (?, ?, ?, ?, ?, 'pendente', ?, ?, ?)
                  ON CONFLICT (recorrencia_id, competencia) DO NOTHING''',
                  (empresa_id, plano['descricao'], plano['categoria'], plano['valor'], venc.isoformat(),
                   plano['observacoes'], plano['id'], competencia.isoformat()))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@app.route('/admin/financeiro/despesas/<int:despesa_id>/editar', methods=['POST'])
@login_required
def admin_financeiro_despesa_editar(despesa_id):
    empresa_id = _fin_autorizar()
    descricao = request.form.get('descricao','').strip()
    categoria = request.form.get('categoria','').strip()
    observacoes = request.form.get('observacoes','').strip()
    try:
        valor = _fin_valor(request.form.get('valor'))
        vencimento = _fin_data(request.form.get('vencimento',''))
        if not descricao or len(descricao)>200 or len(observacoes)>2000 or categoria not in _FIN_CATEGORIAS:
            raise ValueError()
    except (ValueError, TypeError, InvalidOperation):
        flash('Dados inválidos. Informe valor no formato 10,00.', 'erro')
        return redirect(url_for('admin_financeiro_despesas'))
    conn = get_connection()
    try:
        cur = conn.execute('''UPDATE financeiro_despesas SET descricao=?, categoria=?, valor=?,
            vencimento=?, observacoes=?, atualizado_em=CURRENT_TIMESTAMP
            WHERE id=? AND empresa_id=? AND status='pendente' ''',
            (descricao, categoria, valor, vencimento.isoformat(), observacoes, despesa_id, empresa_id))
        ok = cur.rowcount
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()
    flash('Conta atualizada.' if ok else 'Somente contas pendentes podem ser editadas.', 'sucesso' if ok else 'erro')
    return redirect(url_for('admin_financeiro_despesas'))


@app.route('/admin/financeiro/recorrencias', methods=['GET','POST'])
@login_required
def admin_financeiro_recorrencias():
    empresa_id = _fin_autorizar()
    if request.method == 'POST':
        descricao = request.form.get('descricao','').strip()
        categoria = request.form.get('categoria','').strip()
        observacoes = request.form.get('observacoes','').strip()
        try:
            valor = _fin_valor(request.form.get('valor'))
            dia = int(request.form.get('dia_vencimento','0'))
            inicio = _fin_data(request.form.get('inicio',''))
            if not descricao or len(descricao)>200 or len(observacoes)>2000 or categoria not in _FIN_CATEGORIAS or not 1<=dia<=31:
                raise ValueError()
        except (ValueError, TypeError, InvalidOperation):
            flash('Confira os dados da recorrência e o valor no formato 10,00.', 'erro')
            return redirect(url_for('admin_financeiro_recorrencias'))
        conn = get_connection()
        try:
            conn.execute('''INSERT INTO financeiro_recorrencias
                (empresa_id, descricao, categoria, valor, dia_vencimento, inicio, observacoes)
                VALUES (?,?,?,?,?,?,?)''',
                (empresa_id, descricao, categoria, valor, dia, inicio.replace(day=1).isoformat(), observacoes))
            conn.commit()
        except Exception:
            conn.rollback(); raise
        finally:
            conn.close()
        _gerar_recorrentes(empresa_id)
        flash('Recorrência criada. Foram gerados vencimentos dos próximos 12 meses.', 'sucesso')
        return redirect(url_for('admin_financeiro_recorrencias'))
    _gerar_recorrentes(empresa_id)
    conn = get_connection()
    try:
        planos = conn.execute('''SELECT * FROM financeiro_recorrencias WHERE empresa_id=? ORDER BY ativo DESC, id DESC''',(empresa_id,)).fetchall()
    finally:
        conn.close()
    return render_template('admin/financeiro_recorrencias.html', planos=planos, categorias=_FIN_CATEGORIAS, hoje=date.today())


@app.route('/admin/financeiro/recorrencias/<int:plano_id>/desativar', methods=['POST'])
@login_required
def admin_financeiro_recorrencia_desativar(plano_id):
    empresa_id = _fin_autorizar()
    conn = get_connection()
    try:
        cur = conn.execute('''UPDATE financeiro_recorrencias SET ativo=FALSE WHERE id=? AND empresa_id=? AND ativo=TRUE''', (plano_id, empresa_id))
        ok = cur.rowcount
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()
    flash('Recorrência desativada. Contas já geradas foram preservadas.' if ok else 'Recorrência não encontrada.', 'sucesso' if ok else 'erro')
    return redirect(url_for('admin_financeiro_recorrencias'))


def _dados_relatorio(empresa_id, inicio, fim):
    conn = get_connection()
    try:
        entradas = conn.execute('''SELECT CAST(vp.criado_em AS DATE) dia, COALESCE(SUM(vp.valor),0) total
            FROM venda_pagamentos vp JOIN vendas v ON v.id=vp.venda_id AND v.empresa_id=vp.empresa_id
            WHERE v.empresa_id=? AND v.status='finalizada' AND vp.criado_em>=? AND vp.criado_em<?
            GROUP BY CAST(vp.criado_em AS DATE) ORDER BY dia''',
            (empresa_id, inicio.isoformat(), (fim+timedelta(days=1)).isoformat())).fetchall()
        saidas = conn.execute('''SELECT data_pagamento dia, COALESCE(SUM(valor),0) total
            FROM financeiro_despesas WHERE empresa_id=? AND status='paga' AND data_pagamento BETWEEN ? AND ?
            GROUP BY data_pagamento ORDER BY data_pagamento''', (empresa_id, inicio.isoformat(), fim.isoformat())).fetchall()
        categorias = conn.execute('''SELECT categoria, COALESCE(SUM(valor),0) total
            FROM financeiro_despesas WHERE empresa_id=? AND status='paga' AND data_pagamento BETWEEN ? AND ?
            GROUP BY categoria ORDER BY total DESC''', (empresa_id, inicio.isoformat(), fim.isoformat())).fetchall()
        historico = conn.execute('''SELECT id, descricao, categoria, valor, vencimento, data_pagamento, forma_pagamento, status
            FROM financeiro_despesas WHERE empresa_id=? AND
              ((status='paga' AND data_pagamento BETWEEN ? AND ?) OR
               (status<>'paga' AND vencimento BETWEEN ? AND ?))
            ORDER BY COALESCE(data_pagamento, vencimento) DESC, id DESC LIMIT 500''',
            (empresa_id, inicio.isoformat(), fim.isoformat(), inicio.isoformat(), fim.isoformat())).fetchall()
    finally:
        conn.close()
    agrupado = {}
    for item in entradas:
        chave = str(item['dia'])[:7]
        agrupado.setdefault(chave, {'mes':chave,'receitas':Decimal('0'),'despesas':Decimal('0')})['receitas'] += Decimal(str(item['total']))
    for item in saidas:
        chave = str(item['dia'])[:7]
        agrupado.setdefault(chave, {'mes':chave,'receitas':Decimal('0'),'despesas':Decimal('0')})['despesas'] += Decimal(str(item['total']))
    meses = [agrupado[k] for k in sorted(agrupado)]
    for item in meses: item['saldo'] = item['receitas'] - item['despesas']
    receitas = sum((Decimal(str(x['total'])) for x in entradas), Decimal('0'))
    despesas = sum((Decimal(str(x['total'])) for x in saidas), Decimal('0'))
    return meses, categorias, historico, receitas, despesas


def _periodo_relatorio():
    hoje = date.today()
    try:
        inicio = date.fromisoformat(request.args.get('inicio',hoje.replace(day=1).isoformat()))
        fim = date.fromisoformat(request.args.get('fim',hoje.isoformat()))
        if inicio>fim or (fim-inicio).days>366: raise ValueError()
    except (ValueError, TypeError):
        inicio, fim = hoje.replace(day=1), hoje
    return inicio, fim


@app.route('/admin/financeiro/relatorios')
@login_required
def admin_financeiro_relatorios():
    empresa_id = _fin_autorizar()
    inicio, fim = _periodo_relatorio()
    meses, categorias, historico, receitas, despesas = _dados_relatorio(empresa_id, inicio, fim)
    return render_template('admin/financeiro_relatorios.html', inicio=inicio, fim=fim,
        meses=meses, categorias=categorias, historico=historico, receitas=receitas, despesas=despesas,
        maior=max([float(x['receitas']) for x in meses]+[float(x['despesas']) for x in meses]+[1]))


@app.route('/admin/financeiro/relatorios/exportar.csv')
@login_required
def admin_financeiro_relatorios_csv():
    empresa_id = _fin_autorizar()
    inicio, fim = _periodo_relatorio()
    meses, categorias, historico, receitas, despesas = _dados_relatorio(empresa_id, inicio, fim)
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(['Tipo','Data','Descrição','Categoria','Valor (R$)','Status','Forma'])
    for row in historico:
        # prefixa células textuais que poderiam ser interpretadas como fórmulas no Excel
        def seguro(s):
            s = str(s or '')
            return "'"+s if s.lstrip().startswith(('=','+','-','@')) else s
        writer.writerow(['Despesa',str(row['data_pagamento'] or row['vencimento']),seguro(row['descricao']),
            seguro(row['categoria']),str(row['valor']).replace('.',','),row['status'],seguro(row['forma_pagamento'])])
    writer.writerow([])
    writer.writerow(['Resumo','Receitas','Despesas','Saldo'])
    writer.writerow(['Total',str(receitas).replace('.',','),str(despesas).replace('.',','),str(receitas-despesas).replace('.',',')])
    return Response('\ufeff'+output.getvalue(), mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition':f'attachment; filename="financeiro_{inicio}_{fim}.csv"'})
