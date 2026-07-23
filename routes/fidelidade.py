"""Programa de fidelidade e recompensas do CRM."""

from core import *  # noqa: F401,F403


def _saldo_cliente(conn, empresa_id, cliente_id):
    row = conn.execute(
        "SELECT pontos_fidelidade FROM clientes WHERE id=? AND empresa_id=?",
        (cliente_id, empresa_id),
    ).fetchone()
    return int(row["pontos_fidelidade"] or 0) if row else None


@app.route('/admin/fidelidade')
@login_required
@recurso_required('crm')
def admin_fidelidade():
    empresa_id = session['empresa_id']
    conn = get_connection()
    config = conn.execute(
        "SELECT * FROM fidelidade_configuracoes WHERE empresa_id=?",
        (empresa_id,),
    ).fetchone()
    if not config:
        conn.execute("INSERT INTO fidelidade_configuracoes (empresa_id) VALUES (?)", (empresa_id,))
        conn.commit()
        config = conn.execute("SELECT * FROM fidelidade_configuracoes WHERE empresa_id=?", (empresa_id,)).fetchone()

    indicadores = conn.execute(
        """
        SELECT COUNT(*) AS participantes,
               COALESCE(SUM(pontos_fidelidade),0) AS pontos_em_circulacao,
               SUM(CASE WHEN pontos_fidelidade > 0 THEN 1 ELSE 0 END) AS clientes_com_saldo
        FROM clientes WHERE empresa_id=? AND COALESCE(ativo,1)=1
        """, (empresa_id,)
    ).fetchone()
    emitidos = conn.execute(
        "SELECT COALESCE(SUM(CASE WHEN quantidade>0 THEN quantidade ELSE 0 END),0) total FROM fidelidade_movimentos WHERE empresa_id=?",
        (empresa_id,),
    ).fetchone()['total']
    resgatados = conn.execute(
        "SELECT COALESCE(SUM(pontos_utilizados),0) total FROM fidelidade_resgates WHERE empresa_id=?",
        (empresa_id,),
    ).fetchone()['total']
    recompensas = conn.execute(
        "SELECT * FROM fidelidade_recompensas WHERE empresa_id=? ORDER BY ativo DESC, pontos_necessarios, nome COLLATE NOCASE",
        (empresa_id,),
    ).fetchall()
    ranking = conn.execute(
        """SELECT id,nome,telefone,pontos_fidelidade FROM clientes
           WHERE empresa_id=? AND COALESCE(ativo,1)=1
           ORDER BY pontos_fidelidade DESC,nome COLLATE NOCASE LIMIT 10""",
        (empresa_id,),
    ).fetchall()
    movimentos = conn.execute(
        """SELECT m.*,c.nome cliente_nome FROM fidelidade_movimentos m
           JOIN clientes c ON c.id=m.cliente_id
           WHERE m.empresa_id=? ORDER BY m.id DESC LIMIT 15""",
        (empresa_id,),
    ).fetchall()
    conn.close()
    return render_template('admin/fidelidade.html', config=config, indicadores=indicadores,
                           emitidos=emitidos, resgatados=resgatados, recompensas=recompensas,
                           ranking=ranking, movimentos=movimentos)


@app.route('/admin/fidelidade/configuracoes', methods=['POST'])
@login_required
@recurso_required('crm')
def admin_fidelidade_configuracoes():
    empresa_id = session['empresa_id']
    tipo = request.form.get('tipo_pontuacao','valor')
    if tipo not in {'valor','atendimento'}: tipo='valor'
    try:
        pontos = max(1, int(request.form.get('pontos_por_atendimento','1')))
        valor = max(0.01, float(request.form.get('valor_por_ponto','10').replace(',','.')))
        validade = request.form.get('validade_dias','').strip()
        validade = max(1, int(validade)) if validade else None
    except ValueError:
        flash('Revise os valores das configurações.', 'erro')
        return redirect(url_for('admin_fidelidade'))
    conn=get_connection()
    conn.execute("""INSERT INTO fidelidade_configuracoes
        (empresa_id,ativo,tipo_pontuacao,pontos_por_atendimento,valor_por_ponto,validade_dias,permitir_ajuste_manual,atualizado_em)
        VALUES (?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
        ON CONFLICT(empresa_id) DO UPDATE SET ativo=excluded.ativo,tipo_pontuacao=excluded.tipo_pontuacao,
        pontos_por_atendimento=excluded.pontos_por_atendimento,valor_por_ponto=excluded.valor_por_ponto,
        validade_dias=excluded.validade_dias,permitir_ajuste_manual=excluded.permitir_ajuste_manual,
        atualizado_em=CURRENT_TIMESTAMP""",
        (empresa_id,1 if request.form.get('ativo') else 0,tipo,pontos,valor,validade,1 if request.form.get('permitir_ajuste_manual') else 0))
    conn.commit(); conn.close(); flash('Configurações de fidelidade atualizadas.','sucesso')
    return redirect(url_for('admin_fidelidade'))


@app.route('/admin/fidelidade/recompensas/nova', methods=['POST'])
@login_required
@recurso_required('crm')
def admin_nova_recompensa():
    empresa_id=session['empresa_id']; nome=request.form.get('nome','').strip(); descricao=request.form.get('descricao','').strip()
    tipo=request.form.get('tipo','brinde')
    if tipo not in {'brinde','desconto','servico'}: tipo='brinde'
    try:
        pontos=int(request.form.get('pontos_necessarios','0')); valor=float(request.form.get('valor_desconto','0').replace(',','.'))
    except ValueError:
        pontos=0; valor=0
    if not nome or pontos <= 0:
        flash('Informe o nome e uma quantidade válida de pontos.','erro'); return redirect(url_for('admin_fidelidade'))
    conn=get_connection(); conn.execute("""INSERT INTO fidelidade_recompensas
        (empresa_id,nome,descricao,pontos_necessarios,tipo,valor_desconto) VALUES (?,?,?,?,?,?)""",
        (empresa_id,nome,descricao or None,pontos,tipo,max(0,valor)))
    conn.commit(); conn.close(); flash('Recompensa cadastrada.','sucesso'); return redirect(url_for('admin_fidelidade'))


@app.route('/admin/fidelidade/recompensas/<int:recompensa_id>/status', methods=['POST'])
@login_required
@recurso_required('crm')
def admin_status_recompensa(recompensa_id):
    empresa_id=session['empresa_id']; conn=get_connection()
    conn.execute("UPDATE fidelidade_recompensas SET ativo=CASE WHEN ativo=1 THEN 0 ELSE 1 END, atualizado_em=CURRENT_TIMESTAMP WHERE id=? AND empresa_id=?",(recompensa_id,empresa_id))
    conn.commit(); conn.close(); flash('Status da recompensa atualizado.','sucesso'); return redirect(url_for('admin_fidelidade'))


@app.route('/admin/clientes/<int:cliente_id>/fidelidade/ajuste', methods=['POST'])
@login_required
@recurso_required('crm')
def admin_ajuste_pontos(cliente_id):
    empresa_id=session['empresa_id']
    try: quantidade=int(request.form.get('quantidade','0'))
    except ValueError: quantidade=0
    descricao=request.form.get('descricao','Ajuste manual').strip()[:200]
    if quantidade == 0:
        flash('Informe uma quantidade diferente de zero.','erro'); return redirect(url_for('admin_perfil_cliente',cliente_id=cliente_id))
    conn=get_connection(); saldo=_saldo_cliente(conn,empresa_id,cliente_id)
    if saldo is None: conn.close(); flash('Cliente não encontrado.','erro'); return redirect(url_for('admin_clientes'))
    if saldo + quantidade < 0: conn.close(); flash('O ajuste deixaria o saldo negativo.','erro'); return redirect(url_for('admin_perfil_cliente',cliente_id=cliente_id))
    conn.execute("UPDATE clientes SET pontos_fidelidade=pontos_fidelidade+?,atualizado_em=CURRENT_TIMESTAMP WHERE id=? AND empresa_id=?",(quantidade,cliente_id,empresa_id))
    conn.execute("INSERT INTO fidelidade_movimentos (empresa_id,cliente_id,tipo,quantidade,descricao) VALUES (?,?,?,?,?)",(empresa_id,cliente_id,'ajuste',quantidade,descricao or 'Ajuste manual'))
    conn.commit(); conn.close(); flash('Saldo de pontos atualizado.','sucesso'); return redirect(url_for('admin_perfil_cliente',cliente_id=cliente_id))


@app.route('/admin/clientes/<int:cliente_id>/fidelidade/resgatar', methods=['POST'])
@login_required
@recurso_required('crm')
def admin_resgatar_recompensa(cliente_id):
    empresa_id=session['empresa_id']
    try: recompensa_id=int(request.form.get('recompensa_id','0'))
    except ValueError: recompensa_id=0
    observacoes=request.form.get('observacoes','').strip()[:300]
    conn=get_connection(); cliente=conn.execute("SELECT id,pontos_fidelidade FROM clientes WHERE id=? AND empresa_id=?",(cliente_id,empresa_id)).fetchone()
    recompensa=conn.execute("SELECT * FROM fidelidade_recompensas WHERE id=? AND empresa_id=? AND ativo=1",(recompensa_id,empresa_id)).fetchone()
    if not cliente or not recompensa:
        conn.close(); flash('Cliente ou recompensa inválida.','erro'); return redirect(url_for('admin_perfil_cliente',cliente_id=cliente_id))
    pontos=int(recompensa['pontos_necessarios'])
    if int(cliente['pontos_fidelidade'] or 0) < pontos:
        conn.close(); flash('Saldo insuficiente para este resgate.','erro'); return redirect(url_for('admin_perfil_cliente',cliente_id=cliente_id))
    conn.execute("UPDATE clientes SET pontos_fidelidade=pontos_fidelidade-?,atualizado_em=CURRENT_TIMESTAMP WHERE id=?",(pontos,cliente_id))
    conn.execute("INSERT INTO fidelidade_resgates (empresa_id,cliente_id,recompensa_id,pontos_utilizados,observacoes) VALUES (?,?,?,?,?)",(empresa_id,cliente_id,recompensa_id,pontos,observacoes or None))
    conn.execute("INSERT INTO fidelidade_movimentos (empresa_id,cliente_id,tipo,quantidade,descricao) VALUES (?,?,?,?,?)",(empresa_id,cliente_id,'resgate',-pontos,f"Resgate: {recompensa['nome']}"))
    conn.commit(); conn.close(); flash('Recompensa resgatada com sucesso.','sucesso'); return redirect(url_for('admin_perfil_cliente',cliente_id=cliente_id))
