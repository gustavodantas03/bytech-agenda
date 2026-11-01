const carrinho = [];

function moeda(valor) {
    return Number(valor).toLocaleString("pt-BR", {
        style: "currency",
        currency: "BRL"
    });
}

function opcoesProfissionais(funcionarioId) {
    const select = document.getElementById("pdv-profissionais");

    if (!select || !select.options.length) {
        return '<option value="">Nenhum profissional disponível</option>';
    }

    let html = '<option value="">Selecione o profissional</option>';

    Array.from(select.options).forEach(opcao => {
        const selecionado = Number(opcao.value) === Number(funcionarioId)
            ? " selected"
            : "";

        html += `<option value="${opcao.value}"${selecionado}>${opcao.textContent}</option>`;
    });

    return html;
}

function alterarProfissional(id, funcionarioId) {
    const item = carrinho.find(i =>
        i.tipo === "servico" && i.id === id
    );

    if (!item) return;

    item.funcionario_id = funcionarioId
        ? Number(funcionarioId)
        : null;
}

function renderCarrinho() {
    const area = document.getElementById("carrinho");
    const subtotalEl = document.getElementById("subtotal-venda");
    const totalEl = document.getElementById("total-venda");
    const tipoDescontoEl = document.getElementById("tipo-desconto");
    const valorDescontoEl = document.getElementById("valor-desconto");

    if (!carrinho.length) {
        area.innerHTML = '<p style="color:#64748b;">Nenhum item adicionado.</p>';
        subtotalEl.textContent = "R$ 0,00";
        totalEl.textContent = "R$ 0,00";
        return;
    }

    let total = 0;

    area.innerHTML = carrinho.map(item => {
        const subtotal = item.preco * item.quantidade;
        total += subtotal;

        return `<div style="padding:10px 0;border-bottom:1px solid #e2e8f0;">
            <strong>${item.nome}</strong>
            <div><small>${moeda(item.preco)} cada</small></div>

            ${item.tipo === "servico" ? `
                <div style="margin-top:8px;">
                    <label style="display:block;font-size:.78rem;font-weight:700;margin-bottom:4px;">
                        Profissional
                    </label>
                    <select
                        onchange="alterarProfissional(${item.id}, this.value)"
                        style="width:100%;padding:7px;border:1px solid #cbd5e1;border-radius:8px;"
                    >
                        ${opcoesProfissionais(item.funcionario_id)}
                    </select>
                </div>
            ` : ""}

            <div style="display:flex;align-items:center;gap:8px;margin-top:8px;">
                <button type="button" onclick="alterarQuantidade('${item.tipo}',${item.id},-1)">−</button>
                <strong>${item.quantidade}</strong>
                <button type="button" onclick="alterarQuantidade('${item.tipo}',${item.id},1)">+</button>
                <button type="button" onclick="removerItem('${item.tipo}',${item.id})">Remover</button>
            </div>

            <div style="margin-top:6px;">
                <strong>${moeda(subtotal)}</strong>
            </div>
        </div>`;
    }).join("");

    const subtotalVenda = total;
    let valorInformado = Number(valorDescontoEl.value || 0);

    if (!Number.isFinite(valorInformado) || valorInformado < 0) {
        valorInformado = 0;
    }

    let desconto = 0;

    if (tipoDescontoEl.value === "percentual") {
        const percentual = Math.min(valorInformado, 100);
        desconto = subtotalVenda * (percentual / 100);
    } else {
        desconto = Math.min(valorInformado, subtotalVenda);
    }

    const totalVenda = Math.max(0, subtotalVenda - desconto);

    subtotalEl.textContent = moeda(subtotalVenda);
    totalEl.textContent = moeda(totalVenda);
}

document.querySelectorAll(".btn-add").forEach(botao => {
    botao.addEventListener("click", () => {
        const tipo = botao.dataset.tipo;
        const id = Number(botao.dataset.id);
        const preco = Number(botao.dataset.preco);

        let item = carrinho.find(i =>
            i.tipo === tipo && i.id === id
        );

        if (item) {
            if (tipo === "produto" && item.quantidade >= item.estoque) {
                alert("Quantidade máxima disponível em estoque.");
                return;
            }
            item.quantidade += 1;
        } else {
            carrinho.push({
                tipo: tipo,
                id: id,
                nome: botao.dataset.nome,
                preco: preco,
                estoque: tipo === "produto" ? Number(botao.dataset.estoque) : null,
                funcionario_id: null,
                quantidade: 1
            });
        }

        renderCarrinho();
    });
});

function alterarQuantidade(tipo, id, delta) {
    const item = carrinho.find(i => i.tipo === tipo && i.id === id);
    if (!item) return;

    const nova = item.quantidade + delta;

    if (nova <= 0) {
        removerItem(tipo, id);
        return;
    }

    if (tipo === "produto" && nova > item.estoque) {
        alert("Quantidade máxima disponível em estoque.");
        return;
    }

    item.quantidade = nova;
    renderCarrinho();
}

function removerItem(tipo, id) {
    const indice = carrinho.findIndex(i => i.tipo === tipo && i.id === id);
    if (indice === -1) return;

    carrinho.splice(indice, 1);
    renderCarrinho();
}

document.getElementById("finalizar-venda").addEventListener("click", async () => {
    if (!carrinho.length) {
        alert("Adicione pelo menos um item à venda.");
        return;
    }

    const servicoSemProfissional = carrinho.find(item =>
        item.tipo === "servico" && !item.funcionario_id
    );

    if (servicoSemProfissional) {
        alert("Selecione o profissional para o serviço: " + servicoSemProfissional.nome);
        return;
    }

    const botao = document.getElementById("finalizar-venda");
    const clienteId = document.getElementById("cliente-venda").value;

    const dados = {
        cliente_id: clienteId || null,
        forma_pagamento: document.getElementById("forma-pagamento").value,
        tipo_desconto: document.getElementById("tipo-desconto").value,
        valor_desconto: Number(document.getElementById("valor-desconto").value || 0),
        itens: carrinho.map(item => ({
            tipo: item.tipo,
            id: item.id,
            quantidade: item.quantidade,
            funcionario_id: item.tipo === "servico" ? item.funcionario_id : null
        }))
    };

    botao.disabled = true;
    botao.textContent = "Finalizando...";

    try {
        const resposta = await fetch("/admin/pdv/finalizar", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": document.getElementById("csrf-token").value
            },
            body: JSON.stringify(dados)
        });

        const resultado = await resposta.json();

        if (!resposta.ok || !resultado.ok) {
            alert(resultado.erro || "Não foi possível finalizar a venda.");
            return;
        }

        alert("Venda #" + resultado.venda_id + " finalizada com sucesso!");

        carrinho.length = 0;
        renderCarrinho();

        window.location.reload();

    } catch (erro) {
        alert("Erro de comunicação ao finalizar a venda.");
    } finally {
        botao.disabled = false;
        botao.textContent = "Finalizar venda";
    }
});

document.getElementById("tipo-desconto").addEventListener("change", renderCarrinho);
document.getElementById("valor-desconto").addEventListener("input", renderCarrinho);
