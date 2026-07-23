import { config, artigoProfissional, rotulos } from "./config.js";
import { estado } from "./estado.js";
import { formatarData, formatarMoeda } from "./util.js";
import { mostrarEtapa } from "./interface.js";
import { carregarHorariosDisponiveis } from "./horarios.js";

function validarAgendamento() {
    const validacoes = [
        [estado.cliente_nome, "Informe o nome do cliente.", "nome"],
        [estado.cliente_telefone, "Informe o WhatsApp.", "telefone"],
        [estado.servicos.length, "Escolha pelo menos um serviço.", "servico"],
        [
            estado.funcionario_id,
            `Escolha ${artigoProfissional()} ${rotulos.profissionalSingular}.`,
            "funcionario",
        ],
        [estado.data, "Escolha uma data.", "data"],
        [estado.hora, "Escolha um horário.", "hora"],
    ];

    for (const [valido, mensagem, etapa] of validacoes) {
        if (!valido) {
            alert(mensagem);
            mostrarEtapa(etapa);
            return false;
        }
    }

    return true;
}

export async function confirmarAgendamento() {
    if (!validarAgendamento()) return;

    const botao = document.querySelector(
        '[data-step="confirmacao"] .booking-primary-button'
    );
    const original = botao?.innerHTML || "";

    if (botao) {
        botao.disabled = true;
        botao.classList.add("disabled");
        botao.innerHTML = `
            <span class="booking-button-loading">
                <span class="booking-loading-spinner"></span>
                Salvando agendamento...
            </span>
        `;
    }

    try {
        const resposta = await fetch(
            `/api/${config.slug}/agendamentos`,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    Accept: "application/json",
                },
                body: JSON.stringify({
                    cliente_nome: estado.cliente_nome,
                    cliente_telefone: estado.cliente_telefone,
                    servico_ids: estado.servico_ids,
                    servicos: estado.servicos,
                    valor_total: estado.valor_total,
                    duracao_total: estado.duracao_total,
                    funcionario_id: estado.funcionario_id,
                    data: estado.data,
                    hora: estado.hora,
                }),
            }
        );

        let dados = {};
        try {
            dados = await resposta.json();
        } catch {
            throw new Error("A API retornou uma resposta inválida.");
        }

        if (!resposta.ok) {
            tratarErro(resposta.status, dados);
            return;
        }

        configurarLinkWhatsApp(dados);
        mostrarEtapa("sucesso");
    } catch (erro) {
        console.error("Erro ao concluir o agendamento:", erro);
        alert(
            "Não foi possível concluir o agendamento. " +
            "Verifique sua conexão e tente novamente."
        );
    } finally {
        if (botao) {
            botao.disabled = false;
            botao.classList.remove("disabled");
            botao.innerHTML = original;
        }
    }
}

function tratarErro(status, dados) {
    const mensagem =
        dados.erro ||
        dados.mensagem ||
        "Não foi possível concluir o agendamento.";

    if (status === 409) {
        alert(mensagem || "Este horário acabou de ser ocupado.");
        estado.hora = "";
        carregarHorariosDisponiveis();
        mostrarEtapa("hora");
        return;
    }

    if (status === 404) {
        alert(mensagem || "A empresa não foi encontrada.");
        return;
    }

    alert(mensagem);
}

function configurarLinkWhatsApp(dados) {
    const link = document.getElementById("whatsappLink");
    if (!link) return;

    const numero = String(config.telefone || "").replace(/\D/g, "");
    if (!numero) {
        link.style.display = "none";
        return;
    }

    const numeroComPais = numero.startsWith("55") ? numero : `55${numero}`;
    const mensagem = dados.whatsapp || montarMensagemWhatsApp();

    link.href =
        `https://wa.me/${numeroComPais}` +
        `?text=${encodeURIComponent(mensagem)}`;
    link.style.display = "flex";
}

function montarMensagemWhatsApp() {
    const lista = estado.servicos
        .map((item) => `• ${item.nome}`)
        .join("\n");

    return [
        `Olá! Meu nome é ${estado.cliente_nome}.`,
        "",
        "Realizei um agendamento:",
        "",
        "Serviços:",
        lista,
        "",
        `Profissional: ${estado.funcionario_nome}`,
        `Data: ${estado.data_texto || formatarData(estado.data)}`,
        `Horário: ${estado.hora}`,
        "",
        `Tempo estimado: ${estado.duracao_total} minutos`,
        `Valor total: ${formatarMoeda(estado.valor_total)}`,
    ].join("\n");
}
