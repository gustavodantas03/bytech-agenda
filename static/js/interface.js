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

export function mostrarEtapa(nome) {
    selecionarTodos(".step").forEach((step) => {
        step.classList.remove("active");
    });

    const etapaAtual = document.querySelector(`[data-step="${nome}"]`);
    if (!etapaAtual) {
        console.error(`A etapa "${nome}" não foi encontrada.`);
        return;
    }

    etapaAtual.classList.add("active");
    atualizarProgresso(nome);

    setTimeout(() => {
        document.getElementById("chat")?.scrollIntoView({
            behavior: "smooth",
            block: "start",
        });
    }, 100);
}

export function atualizarProgresso(nome) {
    const numero = etapas[nome] || 1;
    const percentual = Math.round((numero / 6) * 100);
    const concluido = nome === "sucesso";

    const barra = document.getElementById("bookingProgressBar");
    const texto = document.getElementById("bookingProgressText");
    const percentualTexto = document.getElementById(
        "bookingProgressPercent"
    );

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

    const bolha = document.createElement("div");
    bolha.className = `bubble ${tipo}`;
    bolha.textContent = texto;

    const etapaAtiva = chat.querySelector(".step.active");
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
