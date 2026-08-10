(() => {
    "use strict";

    const lista = document.getElementById("agendaList");
    const pesquisa = document.getElementById("agendaSearch");
    const vazioPesquisa = document.getElementById("agendaSearchEmpty");
    const feedback = document.getElementById("agendaFeedback");
    const filtrosStatus = [...document.querySelectorAll("[data-status-filter]")];
    let statusAtivo = "todos";

    const drawer = document.getElementById("clientDrawer");
    const drawerBackdrop = document.getElementById("clientDrawerBackdrop");
    const drawerLoading = document.getElementById("clientDrawerLoading");
    const drawerContent = document.getElementById("clientDrawerContent");

    const rotulos = {
        agendado: "Agendado",
        confirmado: "Confirmado",
        em_atendimento: "Em atendimento",
        finalizado: "Finalizado",
        cancelado: "Cancelado",
        faltou: "Não compareceu"
    };

    function normalizarTexto(texto) {
        return String(texto || "")
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .toLowerCase()
            .trim();
    }

    function mostrarFeedback(mensagem, tipo = "sucesso") {
        if (!feedback) return;
        feedback.textContent = mensagem;
        feedback.className = `agenda-feedback show ${tipo}`;
        window.clearTimeout(mostrarFeedback.timer);
        mostrarFeedback.timer = window.setTimeout(() => {
            feedback.classList.remove("show");
        }, 3500);
    }

    function formatarMoeda(valor) {
        return Number(valor || 0).toLocaleString("pt-BR", {
            style: "currency",
            currency: "BRL"
        });
    }

    function formatarData(valor, apenasDiaMes = false) {
        if (!valor) return null;
        const partes = String(valor).slice(0, 10).split("-");
        if (partes.length !== 3) return String(valor);
        return apenasDiaMes
            ? `${partes[2]}/${partes[1]}`
            : `${partes[2]}/${partes[1]}/${partes[0]}`;
    }

    function definirTexto(id, valor) {
        const elemento = document.getElementById(id);
        if (elemento) elemento.textContent = valor;
    }

    function atualizarKpis(resumo) {
        if (!resumo) return;
        Object.entries(resumo).forEach(([chave, valor]) => {
            const elemento = document.querySelector(`[data-kpi="${chave}"]`);
            if (!elemento) return;
            if (chave === "previsao") {
                elemento.textContent = formatarMoeda(valor);
            } else if (chave === "taxa_ocupacao") {
                elemento.textContent = `${valor}%`;
            } else {
                elemento.textContent = valor;
            }
        });
    }

    function construirAcoes(status) {
        const acoes = [
            '<button type="button" class="agenda-action agenda-action-client" data-open-client-button>👤 Cliente</button>'
        ];

        if (status === "agendado") {
            acoes.push('<button type="button" class="agenda-action agenda-action-confirm" data-new-status="confirmado">✓ Confirmar</button>');
        }
        if (["agendado", "confirmado"].includes(status)) {
            acoes.push('<button type="button" class="agenda-action agenda-action-start" data-new-status="em_atendimento">▶ Iniciar</button>');
        }
        if (status === "em_atendimento") {
            acoes.push('<button type="button" class="agenda-action agenda-action-finish" data-new-status="finalizado">★ Finalizar</button>');
        }
        if (!["finalizado", "cancelado", "faltou"].includes(status)) {
            acoes.push('<button type="button" class="agenda-action agenda-action-missed" data-new-status="faltou">! Faltou</button>');
            acoes.push('<button type="button" class="agenda-action agenda-action-cancel" data-new-status="cancelado">× Cancelar</button>');
        }
        return acoes.join("");
    }

    function atualizarCard(card, status) {
        card.dataset.status = status;
        [...card.classList]
            .filter((classe) => classe.startsWith("status-border-"))
            .forEach((classe) => card.classList.remove(classe));
        card.classList.add(`status-border-${status}`);

        const etiqueta = card.querySelector("[data-status-label]");
        if (etiqueta) {
            etiqueta.className = `status status-${status}`;
            etiqueta.textContent = rotulos[status] || status;
        }

        const acoes = card.querySelector(".agenda-quick-actions");
        if (acoes) acoes.innerHTML = construirAcoes(status);
    }

    async function lerJson(resposta) {
        const tipo = resposta.headers.get("content-type") || "";
        if (!tipo.includes("application/json")) {
            throw new Error("O servidor retornou uma resposta inválida. Verifique o terminal do Flask.");
        }
        return resposta.json();
    }

    async function alterarStatus(botao) {
        const card = botao.closest("[data-agendamento-id]");
        if (!card) return;

        const novoStatus = botao.dataset.newStatus;
        const url = card.dataset.statusUrl;

        if (!url) {
            mostrarFeedback("Rota de atualização não encontrada.", "erro");
            return;
        }

        if (novoStatus === "cancelado" &&
            !window.confirm("Deseja realmente cancelar este agendamento?")) {
            return;
        }

        card.classList.add("is-updating");
        card.querySelectorAll("button").forEach((item) => {
            item.disabled = true;
        });

        try {
            const resposta = await fetch(url, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "X-CSRFToken": window.CSRF_TOKEN || ""
                },
                body: JSON.stringify({
                    status: novoStatus,
                    funcionario_id: lista?.dataset.funcionarioId || null
                })
            });
            const dados = await lerJson(resposta);
            if (!resposta.ok || !dados.sucesso) {
                throw new Error(dados.mensagem || "Não foi possível atualizar o status.");
            }
            atualizarCard(card, dados.status);
            atualizarKpis(dados.resumo);
            mostrarFeedback(dados.mensagem || "Status atualizado com sucesso.");
        } catch (erro) {
            console.error(erro);
            mostrarFeedback(erro.message || "Erro ao atualizar o status.", "erro");
        } finally {
            card.classList.remove("is-updating");
            card.querySelectorAll("button").forEach((item) => {
                item.disabled = false;
            });
        }
    }

    function urlWhatsapp(telefone) {
        let numero = String(telefone || "").replace(/\D/g, "");
        if (numero && !numero.startsWith("55")) numero = `55${numero}`;
        return numero ? `https://wa.me/${numero}` : "#";
    }

    function abrirEstruturaDrawer() {
        if (!drawer || !drawerBackdrop || !drawerLoading || !drawerContent) {
            mostrarFeedback("O painel lateral não foi encontrado na página.", "erro");
            return false;
        }
        drawerBackdrop.hidden = false;
        drawer.classList.add("open");
        drawer.setAttribute("aria-hidden", "false");
        document.body.classList.add("client-drawer-open");
        drawerLoading.hidden = false;
        drawerContent.hidden = true;
        return true;
    }

    function fecharDrawer() {
        if (!drawer || !drawerBackdrop) return;
        drawer.classList.remove("open");
        drawer.setAttribute("aria-hidden", "true");
        drawerBackdrop.hidden = true;
        document.body.classList.remove("client-drawer-open");
    }

    function renderizarHistorico(historico) {
        const container = document.getElementById("drawerHistory");
        if (!container) return;
        if (!Array.isArray(historico) || !historico.length) {
            container.innerHTML = '<div class="client-history-empty">Nenhum atendimento registrado.</div>';
            return;
        }
        container.innerHTML = historico.map((item) => {
            const status = rotulos[item.status] || item.status || "Agendado";
            return `
                <article class="client-history-item">
                    <div class="client-history-date">
                        <strong>${formatarData(item.data) || "—"}</strong>
                        <span>${item.hora || ""}</span>
                    </div>
                    <div class="client-history-data">
                        <strong>${item.servico_nome || "Serviço"}</strong>
                        <span>${item.funcionario_nome || "Sem profissional"} · ${item.duracao_total || 0} min</span>
                    </div>
                    <div class="client-history-value">
                        <strong>${formatarMoeda(item.valor_total)}</strong>
                        <span class="status status-${item.status || "agendado"}">${status}</span>
                    </div>
                </article>`;
        }).join("");
    }

    function preencherDrawer(dados) {
        const cliente = dados.cliente || {};
        const whatsapp = urlWhatsapp(cliente.telefone);

        definirTexto("drawerAvatar", (cliente.nome || "C").slice(0, 1).toUpperCase());
        definirTexto("clientDrawerTitle", cliente.nome || "Cliente");
        definirTexto("drawerClientSince", `Cliente desde ${formatarData(cliente.criado_em) || "—"}`);
        definirTexto("drawerPhone", cliente.telefone || "Não informado");
        definirTexto("drawerEmail", cliente.email || "Não informado");
        definirTexto("drawerBirthday", formatarData(cliente.data_nascimento, true) || "Não informado");
        definirTexto("drawerInstagram", cliente.instagram || "Não informado");
        definirTexto("drawerVisits", cliente.total_visitas || 0);
        definirTexto("drawerSpent", formatarMoeda(cliente.total_gasto));
        definirTexto("drawerTicket", formatarMoeda(cliente.ticket_medio));
        definirTexto("drawerPoints", `${cliente.pontos_fidelidade || 0}/10`);
        definirTexto("drawerFavoriteService", cliente.servico_favorito || "Ainda não definido");
        definirTexto("drawerFavoriteProfessional", cliente.profissional_favorito || "Ainda não definido");
        definirTexto("drawerLastVisit", formatarData(cliente.ultima_visita) || "Ainda não");
        definirTexto("drawerRewards", `${cliente.recompensas_disponiveis || 0} disponível(is)`);
        definirTexto("drawerNotes", cliente.observacoes || "Nenhuma observação cadastrada.");

        ["drawerWhatsapp", "drawerWhatsappButton"].forEach((id) => {
            const link = document.getElementById(id);
            if (link) link.href = whatsapp;
        });

        const editar = document.getElementById("drawerEditClient");
        const templateEdicao = drawer?.dataset.clientEditUrlTemplate;
        if (editar && templateEdicao) {
            editar.href = templateEdicao.replace(
                /\/0\/editar(?:\?.*)?$/,
                `/${cliente.id}/editar`
            );
        }

        renderizarHistorico(dados.historico);
        drawerLoading.hidden = true;
        drawerContent.hidden = false;
    }

    async function abrirCliente(card) {
        if (!card) return;
        const url = card.dataset.clientUrl;
        if (!url) {
            mostrarFeedback("Rota do cliente não encontrada.", "erro");
            return;
        }
        if (!abrirEstruturaDrawer()) return;

        try {
            const resposta = await fetch(url, {
                headers: {"Accept": "application/json"}
            });
            const dados = await lerJson(resposta);
            if (!resposta.ok || !dados.sucesso) {
                throw new Error(dados.mensagem || "Não foi possível carregar o cliente.");
            }
            preencherDrawer(dados);
        } catch (erro) {
            console.error(erro);
            fecharDrawer();
            mostrarFeedback(erro.message || "Erro ao carregar o cliente.", "erro");
        }
    }

    function filtrarAgenda() {
        if (!lista) return;
        const termo = normalizarTexto(pesquisa ? pesquisa.value : "");
        let visiveis = 0;
        lista.querySelectorAll("[data-search]").forEach((card) => {
            const correspondeBusca = !termo || normalizarTexto(card.dataset.search).includes(termo);
            const correspondeStatus = statusAtivo === "todos" || card.dataset.status === statusAtivo;
            const mostrar = correspondeBusca && correspondeStatus;
            card.hidden = !mostrar;
            if (mostrar) visiveis += 1;
        });
        if (vazioPesquisa) vazioPesquisa.hidden = visiveis !== 0;
    }

    function aplicarBarrasOcupacao() {
        document.querySelectorAll(".agenda-occupancy-item[data-percent]").forEach((item) => {
            const percentual = Math.max(0, Math.min(100, Number(item.dataset.percent || 0)));
            const barra = item.querySelector(".agenda-occupancy-track span");
            if (barra) barra.style.width = `${percentual}%`;
        });
    }

    document.addEventListener("click", (evento) => {
        const alvo = evento.target instanceof Element
            ? evento.target
            : evento.target.parentElement;
        if (!alvo) return;

        const botaoStatus = alvo.closest("[data-new-status]");
        if (botaoStatus) {
            evento.preventDefault();
            alterarStatus(botaoStatus);
            return;
        }

        const gatilhoCliente = alvo.closest("[data-open-client], [data-open-client-button]");
        if (gatilhoCliente) {
            evento.preventDefault();
            abrirCliente(gatilhoCliente.closest("[data-agendamento-id]"));
            return;
        }

        if (alvo.closest("#closeClientDrawer") || alvo === drawerBackdrop) {
            fecharDrawer();
        }
    });

    document.addEventListener("keydown", (evento) => {
        if (evento.key === "Escape") fecharDrawer();
        const alvo = evento.target;
        if (alvo instanceof Element &&
            alvo.closest("[data-open-client]") &&
            ["Enter", " "].includes(evento.key)) {
            evento.preventDefault();
            abrirCliente(alvo.closest("[data-agendamento-id]"));
        }
    });

    if (pesquisa) pesquisa.addEventListener("input", filtrarAgenda);

    filtrosStatus.forEach((botao) => {
        botao.addEventListener("click", () => {
            statusAtivo = botao.dataset.statusFilter || "todos";
            filtrosStatus.forEach((item) => item.classList.toggle("active", item === botao));
            filtrarAgenda();
        });
    });

    aplicarBarrasOcupacao();
})();
