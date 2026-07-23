import { config } from "./config.js";
import { estado } from "./estado.js";
import { limparTexto } from "./util.js";
import {
    adicionarBolha,
    marcarOpcao,
    mostrarEtapa,
} from "./interface.js";
import { montarResumoAgendamento } from "./resumo.js";

export async function carregarHorariosDisponiveis() {
    const container = document.getElementById("horarios");
    if (!container) return;

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
            funcionario_id: String(estado.funcionario_id),
            duracao_total: String(estado.duracao_total || 40),
        });

        estado.servico_ids.forEach((id) => {
            parametros.append("servico_ids", String(id));
        });

        const resposta = await fetch(
            `/api/${config.slug}/horarios?${parametros}`,
            {
                headers: { Accept: "application/json" },
                cache: "no-store",
            }
        );

        const dados = await resposta.json();
        if (!resposta.ok) {
            throw new Error(
                dados.erro || "Não foi possível buscar os horários."
            );
        }

        renderizarHorarios(dados.horarios || []);
    } catch (erro) {
        console.error("Erro ao buscar horários:", erro);
        container.innerHTML = `
            <div class="booking-empty-message">
                <strong>Não foi possível carregar os horários.</strong>
                <span>Tente escolher a data novamente.</span>
            </div>
        `;
    }
}

export function renderizarHorarios(horarios) {
    const container = document.getElementById("horarios");
    if (!container) return;

    if (!Array.isArray(horarios) || !horarios.length) {
        container.innerHTML = `
            <div class="booking-empty-message">
                <strong>Nenhum horário disponível.</strong>
                <span>Escolha outra data ou outro profissional.</span>
            </div>
        `;
        return;
    }

    container.innerHTML = "";

    horarios.forEach((hora) => {
        const botao = document.createElement("button");
        botao.type = "button";
        botao.className = "option booking-time-option";
        botao.dataset.hora = hora;
        botao.setAttribute("aria-pressed", "false");
        botao.innerHTML = `<span>${hora}</span>`;
        botao.addEventListener("click", () => selecionarHora(botao));
        container.appendChild(botao);
    });
}

export function selecionarHora(botaoOuHora) {
    const botao = typeof botaoOuHora === "string" ? null : botaoOuHora;
    const hora = limparTexto(
        typeof botaoOuHora === "string"
            ? botaoOuHora
            : botao?.dataset.hora || botao?.textContent
    );

    if (!hora) return alert("Não foi possível identificar o horário.");

    estado.hora = hora;
    marcarOpcao(".booking-time-option", botao);
    adicionarBolha(hora);
    montarResumoAgendamento();
    mostrarEtapa("confirmacao");
}
