import { selecionarTodos } from "./util.js";

const etapas = {
    nome: 1,
    telefone: 2,
    servico: 3,
    funcionario: 4,
    data: 5,
    hora: 6,
    confirmacao: 6,
    sucesso: 6,
};

const historicoEtapas = ["nome"];
let etapaAtualNome = "nome";

function exibirEtapa(nome) {
    selecionarTodos(".step").forEach((step) => {
        step.classList.remove("active");
    });

    const etapaAtual = document.querySelector(`[data-step="${nome}"]`);
    if (!etapaAtual) {
        console.error(`A etapa "${nome}" não foi encontrada.`);
        return false;
    }

    etapaAtual.classList.add("active");
    etapaAtualNome = nome;
    atualizarProgresso(nome);

    setTimeout(() => {
        document.getElementById("chat")?.scrollIntoView({
            behavior: "smooth",
            block: "start",
        });
    }, 100);

    return true;
}

export function mostrarEtapa(nome, opcoes = {}) {
    const { registrarHistorico = true } = opcoes;
    if (!exibirEtapa(nome)) return;

    if (registrarHistorico) {
        const ultima = historicoEtapas.at(-1);
        if (ultima !== nome) historicoEtapas.push(nome);
    }
}

export function voltarEtapa() {
    if (etapaAtualNome === "sucesso") {
        window.location.href = window.APP_CONFIG?.landingUrl || "/";
        return;
    }

    if (historicoEtapas.length <= 1) {
        window.location.href = window.APP_CONFIG?.landingUrl || "/";
        return;
    }

    historicoEtapas.pop();
    const etapaAnterior = historicoEtapas.at(-1) || "nome";
    exibirEtapa(etapaAnterior);

    const campoFoco = {
        nome: "nome",
        telefone: "telefone",
    }[etapaAnterior];

    if (campoFoco) {
        setTimeout(() => document.getElementById(campoFoco)?.focus(), 250);
    }
}

export function atualizarProgresso(nome) {
    const numero = etapas[nome] || 1;
    const percentual = Math.round((numero / 6) * 100);
    const concluido = nome === "sucesso";

    const barra = document.getElementById("bookingProgressBar");
    const texto = document.getElementById("bookingProgressText");
    const percentualTexto = document.getElementById("bookingProgressPercent");

    if (barra) barra.style.width = `${percentual}%`;
    if (texto) {
        texto.textContent = concluido
            ? "Agendamento concluído"
            : `Etapa ${numero} de 6`;
    }
    if (percentualTexto) {
        percentualTexto.textContent = concluido ? "100%" : `${percentual}%`;
    }
}

export function adicionarBolha(texto, tipo = "user") {
    const chat = document.getElementById("chat");
    if (!chat) return;

    const etapaAtiva = chat.querySelector(".step.active");
    const origem = etapaAtiva?.dataset.step || "desconhecida";
    const existente = chat.querySelector(`.bubble[data-origin-step="${origem}"]`);

    if (existente) {
        existente.textContent = texto;
        existente.className = `bubble ${tipo}`;
        existente.dataset.originStep = origem;
        return;
    }

    const bolha = document.createElement("div");
    bolha.className = `bubble ${tipo}`;
    bolha.textContent = texto;
    bolha.dataset.originStep = origem;

    etapaAtiva
        ? chat.insertBefore(bolha, etapaAtiva)
        : chat.appendChild(bolha);
}

export function marcarOpcao(seletor, botao) {
    selecionarTodos(seletor).forEach((item) => {
        item.classList.remove("selected");
        item.setAttribute("aria-pressed", "false");
    });

    if (botao) {
        botao.classList.add("selected");
        botao.setAttribute("aria-pressed", "true");
    }
}
