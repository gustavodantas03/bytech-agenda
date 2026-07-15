/* ==================================================
   BYTECH AGENDA
   AGENDAMENTO COM MÚLTIPLOS SERVIÇOS — PARTE 1
================================================== */

const estado = {
    cliente_nome: "",
    cliente_telefone: "",

    servicos: [],
    servico_ids: [],
    servicos_nomes: [],

    valor_total: 0,
    duracao_total: 0,

    funcionario_id: null,
    funcionario_nome: "",

    data: "",
    data_texto: "",
    hora: ""
};


/* ==================================================
   CONFIGURAÇÃO DAS ETAPAS
================================================== */

const etapasAgendamento = {
    nome: 1,
    telefone: 2,
    servico: 3,
    funcionario: 4,
    data: 5,
    hora: 6,
    confirmacao: 6,
    sucesso: 6
};


function mostrarEtapa(nome) {
    document
        .querySelectorAll(".step")
        .forEach((step) => {
            step.classList.remove("active");
        });

    const etapaAtual = document.querySelector(
        `[data-step="${nome}"]`
    );

    if (!etapaAtual) {
        console.error(
            `A etapa "${nome}" não foi encontrada.`
        );

        return;
    }

    etapaAtual.classList.add("active");

    atualizarProgresso(nome);

    setTimeout(() => {
        const card = document.getElementById("chat");

        if (card) {
            card.scrollIntoView({
                behavior: "smooth",
                block: "start"
            });
        }
    }, 100);
}


function atualizarProgresso(nome) {
    const numeroEtapa =
        etapasAgendamento[nome] || 1;

    const percentual = Math.round(
        (numeroEtapa / 6) * 100
    );

    const barra = document.getElementById(
        "bookingProgressBar"
    );

    const texto = document.getElementById(
        "bookingProgressText"
    );

    const percentualTexto = document.getElementById(
        "bookingProgressPercent"
    );

    if (barra) {
        barra.style.width = `${percentual}%`;
    }

    if (texto) {
        texto.textContent =
            nome === "sucesso"
                ? "Agendamento concluído"
                : `Etapa ${numeroEtapa} de 6`;
    }

    if (percentualTexto) {
        percentualTexto.textContent =
            nome === "sucesso"
                ? "100%"
                : `${percentual}%`;
    }
}


/* ==================================================
   FUNÇÕES AUXILIARES
================================================== */

function adicionarBolha(texto, tipo = "user") {
    const chat = document.getElementById("chat");

    if (!chat) {
        return;
    }

    const bolha = document.createElement("div");

    bolha.className = `bubble ${tipo}`;
    bolha.textContent = texto;

    const etapaAtiva = chat.querySelector(
        ".step.active"
    );

    if (etapaAtiva) {
        chat.insertBefore(bolha, etapaAtiva);
    } else {
        chat.appendChild(bolha);
    }
}


function formatarMoeda(valor) {
    return Number(valor || 0).toLocaleString(
        "pt-BR",
        {
            style: "currency",
            currency: "BRL"
        }
    );
}


function limparTexto(valor) {
    return String(valor || "").trim();
}


/* ==================================================
   ETAPA: NOME
================================================== */

function avancarNome() {
    const campoNome = document.getElementById("nome");

    if (!campoNome) {
        alert("O campo de nome não foi encontrado.");
        return;
    }

    const nome = limparTexto(campoNome.value);

    if (!nome) {
        alert("Digite seu nome.");
        campoNome.focus();
        return;
    }

    if (nome.length < 2) {
        alert("Digite um nome válido.");
        campoNome.focus();
        return;
    }

    estado.cliente_nome = nome;

    adicionarBolha(nome);
    mostrarEtapa("telefone");
}


/* ==================================================
   ETAPA: TELEFONE
================================================== */

function avancarTelefone() {
    const campoTelefone =
        document.getElementById("telefone");

    if (!campoTelefone) {
        alert(
            "O campo de telefone não foi encontrado."
        );

        return;
    }

    const telefone = limparTexto(
        campoTelefone.value
    );

    const somenteNumeros = telefone.replace(
        /\D/g,
        ""
    );

    if (!telefone) {
        alert("Digite seu WhatsApp.");
        campoTelefone.focus();
        return;
    }

    if (somenteNumeros.length < 10) {
        alert(
            "Digite um WhatsApp válido com DDD."
        );

        campoTelefone.focus();
        return;
    }

    estado.cliente_telefone = telefone;

    adicionarBolha(telefone);
    mostrarEtapa("servico");
}


/* ==================================================
   ETAPA: MÚLTIPLOS SERVIÇOS
================================================== */

function selecionarServico(botao) {
    if (!botao) {
        return;
    }

    const servicoId = Number(
        botao.dataset.id
    );

    const servicoNome = limparTexto(
        botao.dataset.nome
    );

    const servicoValor = Number(
        botao.dataset.valor || 0
    );

    const servicoDuracao = Number(
        botao.dataset.duracao || 0
    );

    if (!servicoId || !servicoNome) {
        console.error(
            "Os dados do serviço estão incompletos."
        );

        return;
    }

    const indiceExistente =
        estado.servicos.findIndex(
            (servico) =>
                servico.id === servicoId
        );

    if (indiceExistente >= 0) {
        estado.servicos.splice(
            indiceExistente,
            1
        );

        botao.classList.remove("selected");
        botao.setAttribute(
            "aria-pressed",
            "false"
        );
    } else {
        estado.servicos.push({
            id: servicoId,
            nome: servicoNome,
            valor: servicoValor,
            duracao: servicoDuracao
        });

        botao.classList.add("selected");
        botao.setAttribute(
            "aria-pressed",
            "true"
        );
    }

    sincronizarServicosSelecionados();
    atualizarResumoServicos();
}


function sincronizarServicosSelecionados() {
    estado.servico_ids =
        estado.servicos.map(
            (servico) => servico.id
        );

    estado.servicos_nomes =
        estado.servicos.map(
            (servico) => servico.nome
        );

    estado.valor_total =
        estado.servicos.reduce(
            (total, servico) =>
                total + Number(servico.valor),
            0
        );

    estado.duracao_total =
        estado.servicos.reduce(
            (total, servico) =>
                total + Number(servico.duracao),
            0
        );
}


function atualizarResumoServicos() {
    const quantidadeElemento =
        document.getElementById(
            "servicosSelecionadosQuantidade"
        );

    const listaElemento =
        document.getElementById(
            "servicosSelecionadosLista"
        );

    const valorElemento =
        document.getElementById(
            "servicosSelecionadosValor"
        );

    const duracaoElemento =
        document.getElementById(
            "servicosSelecionadosDuracao"
        );

    const botaoContinuar =
        document.getElementById(
            "continuarServicos"
        );

    const quantidade =
        estado.servicos.length;

    if (quantidadeElemento) {
        quantidadeElemento.textContent =
            quantidade === 1
                ? "1 serviço selecionado"
                : `${quantidade} serviços selecionados`;
    }

    if (listaElemento) {
        listaElemento.innerHTML = "";

        estado.servicos.forEach(
            (servico) => {
                const item =
                    document.createElement("div");

                item.className =
                    "selected-service-item";

                item.innerHTML = `
                    <span>
                        ✓ ${servico.nome}
                    </span>

                    <strong>
                        ${formatarMoeda(servico.valor)}
                    </strong>
                `;

                listaElemento.appendChild(item);
            }
        );
    }

    if (valorElemento) {
        valorElemento.textContent =
            formatarMoeda(
                estado.valor_total
            );
    }

    if (duracaoElemento) {
        duracaoElemento.textContent =
            `${estado.duracao_total} minutos`;
    }

    if (botaoContinuar) {
        botaoContinuar.disabled =
            quantidade === 0;

        botaoContinuar.classList.toggle(
            "disabled",
            quantidade === 0
        );
    }
}


function avancarServicos() {
    if (estado.servicos.length === 0) {
        alert(
            "Escolha pelo menos um serviço."
        );

        return;
    }

    const nomes =
        estado.servicos_nomes.join(" + ");

    adicionarBolha(nomes);
    mostrarEtapa("funcionario");
}

/* ==================================================
   BYTECH AGENDA
   AGENDAMENTO COM MÚLTIPLOS SERVIÇOS — PARTE 2
================================================== */


/* ==================================================
   ETAPA: FUNCIONÁRIO
================================================== */

function selecionarFuncionario(botao) {
    if (!botao) {
        return;
    }

    const funcionarioId = Number(
        botao.dataset.id
    );

    const funcionarioNome = limparTexto(
        botao.dataset.nome
    );

    if (!funcionarioId || !funcionarioNome) {
        console.error(
            "Os dados do funcionário estão incompletos."
        );

        return;
    }

    estado.funcionario_id = funcionarioId;
    estado.funcionario_nome = funcionarioNome;

    document
        .querySelectorAll(
            '[data-step="funcionario"] .booking-option'
        )
        .forEach((item) => {
            item.classList.remove("selected");

            item.setAttribute(
                "aria-pressed",
                "false"
            );
        });

    botao.classList.add("selected");

    botao.setAttribute(
        "aria-pressed",
        "true"
    );

    adicionarBolha(funcionarioNome);
    mostrarEtapa("data");
}


/* ==================================================
   ETAPA: DATA
================================================== */

async function selecionarData(botao) {
    if (!botao) {
        return;
    }

    const dataValor = limparTexto(
        botao.dataset.data
    );

    const dataTexto = limparTexto(
        botao.textContent
    );

    if (!dataValor) {
        alert("Não foi possível identificar a data.");

        return;
    }

    if (!estado.funcionario_id) {
        alert(
            "Escolha um barbeiro antes de selecionar a data."
        );

        mostrarEtapa("funcionario");
        return;
    }

    if (estado.servicos.length === 0) {
        alert(
            "Escolha pelo menos um serviço antes de continuar."
        );

        mostrarEtapa("servico");
        return;
    }

    estado.data = dataValor;
    estado.data_texto = dataTexto;

    document
        .querySelectorAll(
            '[data-step="data"] .booking-date-option'
        )
        .forEach((item) => {
            item.classList.remove("selected");

            item.setAttribute(
                "aria-pressed",
                "false"
            );
        });

    botao.classList.add("selected");

    botao.setAttribute(
        "aria-pressed",
        "true"
    );

    adicionarBolha(dataTexto);

    await carregarHorariosDisponiveis();
}


/* ==================================================
   BUSCA DE HORÁRIOS
================================================== */

async function carregarHorariosDisponiveis() {
    const container =
        document.getElementById("horarios");

    if (!container) {
        console.error(
            "O container de horários não foi encontrado."
        );

        return;
    }

    container.innerHTML = `
        <div class="booking-loading">
            <span class="booking-loading-spinner"></span>
            <p>Buscando horários disponíveis...</p>
        </div>
    `;

    mostrarEtapa("hora");

    try {
        const parametros = new URLSearchParams({
            data: estado.data,
            funcionario_id:
                String(estado.funcionario_id),
            duracao_total:
                String(
                    estado.duracao_total || 40
                )
        });

        estado.servico_ids.forEach(
            (servicoId) => {
                parametros.append(
                    "servico_ids",
                    String(servicoId)
                );
            }
        );

        const url =
            `/api/${window.APP_CONFIG.slug}/horarios?` +
            parametros.toString();

        const resposta = await fetch(
            url,
            {
                headers: {
                    "Accept": "application/json"
                },
                cache: "no-store"
            }
        );

        const dados = await resposta.json();

        if (!resposta.ok) {
            throw new Error(
                dados.erro ||
                "Não foi possível buscar os horários."
            );
        }

        renderizarHorarios(
            dados.horarios || []
        );
    } catch (erro) {
        console.error(
            "Erro ao buscar horários:",
            erro
        );

        container.innerHTML = `
            <div class="booking-empty-message">
                <strong>
                    Não foi possível carregar os horários.
                </strong>

                <span>
                    Tente escolher a data novamente.
                </span>
            </div>
        `;
    }
}


function renderizarHorarios(horarios) {
    const container =
        document.getElementById("horarios");

    if (!container) {
        return;
    }

    container.innerHTML = "";

    if (!Array.isArray(horarios) ||
        horarios.length === 0) {
        container.innerHTML = `
            <div class="booking-empty-message">
                <strong>
                    Nenhum horário disponível.
                </strong>

                <span>
                    Escolha outra data ou outro profissional.
                </span>
            </div>
        `;

        return;
    }

    horarios.forEach((hora) => {
        const botao =
            document.createElement("button");

        botao.type = "button";
        botao.className =
            "option booking-time-option";

        botao.dataset.hora = hora;

        botao.setAttribute(
            "aria-pressed",
            "false"
        );

        botao.innerHTML = `
            <span>${hora}</span>
        `;

        botao.addEventListener(
            "click",
            () => {
                selecionarHora(botao);
            }
        );

        container.appendChild(botao);
    });
}


/* ==================================================
   ETAPA: HORÁRIO
================================================== */

function selecionarHora(botaoOuHora) {
    let hora = "";
    let botao = null;

    if (
        typeof botaoOuHora === "string"
    ) {
        hora = limparTexto(botaoOuHora);
    } else if (botaoOuHora) {
        botao = botaoOuHora;

        hora = limparTexto(
            botao.dataset.hora ||
            botao.textContent
        );
    }

    if (!hora) {
        alert(
            "Não foi possível identificar o horário."
        );

        return;
    }

    estado.hora = hora;

    document
        .querySelectorAll(
            ".booking-time-option"
        )
        .forEach((item) => {
            item.classList.remove("selected");

            item.setAttribute(
                "aria-pressed",
                "false"
            );
        });

    if (botao) {
        botao.classList.add("selected");

        botao.setAttribute(
            "aria-pressed",
            "true"
        );
    }

    adicionarBolha(hora);

    montarResumoAgendamento();

    mostrarEtapa("confirmacao");
}


/* ==================================================
   RESUMO FINAL
================================================== */

function montarResumoAgendamento() {
    const resumo =
        document.getElementById("resumo");

    if (!resumo) {
        console.error(
            "O resumo do agendamento não foi encontrado."
        );

        return;
    }

    const servicosHtml =
        estado.servicos
            .map(
                (servico) => `
                    <div class="booking-summary-service">
                        <span>
                            ${servico.nome}
                        </span>

                        <strong>
                            ${formatarMoeda(servico.valor)}
                        </strong>
                    </div>
                `
            )
            .join("");

    resumo.innerHTML = `
        <div class="booking-summary-section">

            <span class="booking-summary-label">
                Cliente
            </span>

            <strong>
                ${estado.cliente_nome}
            </strong>

            <small>
                ${estado.cliente_telefone}
            </small>

        </div>

        <div class="booking-summary-section">

            <span class="booking-summary-label">
                Serviços
            </span>

            <div class="booking-summary-services">
                ${servicosHtml}
            </div>

        </div>

        <div class="booking-summary-row">

            <div>
                <span class="booking-summary-label">
                    Profissional
                </span>

                <strong>
                    ${estado.funcionario_nome}
                </strong>
            </div>

            <div>
                <span class="booking-summary-label">
                    Data e horário
                </span>

                <strong>
                    ${estado.data_texto || formatarData(estado.data)}
                    às ${estado.hora}
                </strong>
            </div>

        </div>

        <div class="booking-summary-total">

            <div>
                <span>
                    Tempo estimado
                </span>

                <strong>
                    ${estado.duracao_total} minutos
                </strong>
            </div>

            <div>
                <span>
                    Valor total
                </span>

                <strong>
                    ${formatarMoeda(
                        estado.valor_total
                    )}
                </strong>
            </div>

        </div>
    `;
}


function formatarData(dataIso) {
    const data = limparTexto(dataIso);

    if (!data) {
        return "";
    }

    const partes = data.split("-");

    if (partes.length !== 3) {
        return data;
    }

    return (
        `${partes[2]}/` +
        `${partes[1]}/` +
        `${partes[0]}`
    );
}


/* ==================================================
   VALIDAÇÃO ANTES DE ENVIAR
================================================== */

function validarAgendamentoCompleto() {
    if (!estado.cliente_nome) {
        alert("Informe o nome do cliente.");
        mostrarEtapa("nome");
        return false;
    }

    if (!estado.cliente_telefone) {
        alert("Informe o WhatsApp.");
        mostrarEtapa("telefone");
        return false;
    }

    if (estado.servicos.length === 0) {
        alert(
            "Escolha pelo menos um serviço."
        );

        mostrarEtapa("servico");
        return false;
    }

    if (!estado.funcionario_id) {
        alert("Escolha um barbeiro.");
        mostrarEtapa("funcionario");
        return false;
    }

    if (!estado.data) {
        alert("Escolha uma data.");
        mostrarEtapa("data");
        return false;
    }

    if (!estado.hora) {
        alert("Escolha um horário.");
        mostrarEtapa("hora");
        return false;
    }

    return true;
}

/* ==================================================
   BYTECH AGENDA
   AGENDAMENTO COM MÚLTIPLOS SERVIÇOS — PARTE 3
================================================== */


/* ==================================================
   ENVIO DO AGENDAMENTO
================================================== */

async function confirmarAgendamento() {
    if (!validarAgendamentoCompleto()) {
        return;
    }

    const botaoConfirmar =
        document.querySelector(
            '[data-step="confirmacao"] ' +
            '.booking-primary-button'
        );

    const textoOriginal =
        botaoConfirmar
            ? botaoConfirmar.innerHTML
            : "";

    if (botaoConfirmar) {
        botaoConfirmar.disabled = true;
        botaoConfirmar.classList.add("disabled");

        botaoConfirmar.innerHTML = `
            <span class="booking-button-loading">
                <span class="booking-loading-spinner"></span>
                Salvando agendamento...
            </span>
        `;
    }

    const dadosEnvio = {
        cliente_nome:
            estado.cliente_nome,

        cliente_telefone:
            estado.cliente_telefone,

        servico_ids:
            estado.servico_ids,

        servicos:
            estado.servicos.map(
                (servico) => ({
                    id: servico.id,
                    nome: servico.nome,
                    valor: servico.valor,
                    duracao: servico.duracao
                })
            ),

        valor_total:
            estado.valor_total,

        duracao_total:
            estado.duracao_total,

        funcionario_id:
            estado.funcionario_id,

        data:
            estado.data,

        hora:
            estado.hora
    };

    try {
        const resposta = await fetch(
            `/api/${window.APP_CONFIG.slug}/agendamentos`,
            {
                method: "POST",

                headers: {
                    "Content-Type":
                        "application/json",

                    "Accept":
                        "application/json"
                },

                body: JSON.stringify(
                    dadosEnvio
                )
            }
        );

        let dadosResposta = {};

        try {
            dadosResposta =
                await resposta.json();
        } catch (erroJson) {
            console.error(
                "A resposta da API não é JSON:",
                erroJson
            );
        }

        if (!resposta.ok) {
            tratarErroAgendamento(
                resposta.status,
                dadosResposta
            );

            return;
        }

        configurarLinkWhatsApp(
            dadosResposta
        );

        mostrarEtapa("sucesso");
    } catch (erro) {
        console.error(
            "Erro ao concluir o agendamento:",
            erro
        );

        alert(
            "Não foi possível concluir o " +
            "agendamento. Verifique sua conexão " +
            "e tente novamente."
        );
    } finally {
        if (botaoConfirmar) {
            botaoConfirmar.disabled = false;

            botaoConfirmar.classList.remove(
                "disabled"
            );

            botaoConfirmar.innerHTML =
                textoOriginal;
        }
    }
}


/* ==================================================
   TRATAMENTO DE ERROS
================================================== */

function tratarErroAgendamento(
    status,
    dadosResposta
) {
    const mensagem =
        dadosResposta.erro ||
        dadosResposta.mensagem ||
        "Não foi possível concluir o agendamento.";

    if (status === 409) {
        alert(
            mensagem ||
            "Este horário acabou de ser ocupado."
        );

        estado.hora = "";

        carregarHorariosDisponiveis();

        mostrarEtapa("hora");

        return;
    }

    if (status === 400) {
        alert(mensagem);
        return;
    }

    if (status === 404) {
        alert(
            mensagem ||
            "A barbearia não foi encontrada."
        );

        return;
    }

    alert(mensagem);
}


/* ==================================================
   WHATSAPP
================================================== */

function configurarLinkWhatsApp(
    dadosResposta
) {
    const link =
        document.getElementById(
            "whatsappLink"
        );

    if (!link) {
        return;
    }

    const numero =
        String(
            window.APP_CONFIG.telefone || ""
        ).replace(/\D/g, "");

    if (!numero) {
        link.style.display = "none";
        return;
    }

    const mensagem =
        dadosResposta.whatsapp ||
        montarMensagemWhatsApp();

    const numeroComPais =
        numero.startsWith("55")
            ? numero
            : `55${numero}`;

    link.href =
        `https://wa.me/${numeroComPais}` +
        `?text=${encodeURIComponent(mensagem)}`;

    link.style.display = "flex";
}


function montarMensagemWhatsApp() {
    const listaServicos =
        estado.servicos
            .map(
                (servico) =>
                    `• ${servico.nome}`
            )
            .join("\n");

    return (
        `Olá! Meu nome é ` +
        `${estado.cliente_nome}.\n\n` +

        `Realizei um agendamento:\n\n` +

        `Serviços:\n` +
        `${listaServicos}\n\n` +

        `Profissional: ` +
        `${estado.funcionario_nome}\n` +

        `Data: ` +
        `${estado.data_texto || formatarData(estado.data)}\n` +

        `Horário: ${estado.hora}\n\n` +

        `Tempo estimado: ` +
        `${estado.duracao_total} minutos\n` +

        `Valor total: ` +
        `${formatarMoeda(estado.valor_total)}`
    );
}


/* ==================================================
   MELHORIAS DE USABILIDADE
================================================== */

function configurarMascaraTelefone() {
    const campoTelefone =
        document.getElementById("telefone");

    if (!campoTelefone) {
        return;
    }

    campoTelefone.addEventListener(
        "input",
        () => {
            let valor =
                campoTelefone.value.replace(
                    /\D/g,
                    ""
                );

            valor = valor.slice(0, 11);

            if (valor.length <= 10) {
                valor = valor.replace(
                    /^(\d{2})(\d)/,
                    "($1) $2"
                );

                valor = valor.replace(
                    /(\d{4})(\d)/,
                    "$1-$2"
                );
            } else {
                valor = valor.replace(
                    /^(\d{2})(\d)/,
                    "($1) $2"
                );

                valor = valor.replace(
                    /(\d{5})(\d)/,
                    "$1-$2"
                );
            }

            campoTelefone.value = valor;
        }
    );
}


function configurarEnterNosCampos() {
    const campoNome =
        document.getElementById("nome");

    const campoTelefone =
        document.getElementById(
            "telefone"
        );

    if (campoNome) {
        campoNome.addEventListener(
            "keydown",
            (evento) => {
                if (evento.key === "Enter") {
                    evento.preventDefault();
                    avancarNome();
                }
            }
        );
    }

    if (campoTelefone) {
        campoTelefone.addEventListener(
            "keydown",
            (evento) => {
                if (evento.key === "Enter") {
                    evento.preventDefault();
                    avancarTelefone();
                }
            }
        );
    }
}


/* ==================================================
   INICIALIZAÇÃO
================================================== */

document.addEventListener(
    "DOMContentLoaded",
    () => {
        configurarMascaraTelefone();
        configurarEnterNosCampos();
        atualizarResumoServicos();

        const campoNome =
            document.getElementById("nome");

        if (campoNome) {
            setTimeout(() => {
                campoNome.focus();
            }, 300);
        }
    }
);