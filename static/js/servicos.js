import { estado } from "./estado.js";
import { formatarMoeda, limparTexto } from "./util.js";
import { adicionarBolha, mostrarEtapa } from "./interface.js";

export function selecionarServico(botao) {
    if (!botao) return;

    const servico = {
        id: Number(botao.dataset.id),
        nome: limparTexto(botao.dataset.nome),
        valor: Number(botao.dataset.valor || 0),
        duracao: Number(botao.dataset.duracao || 0),
    };

    if (!servico.id || !servico.nome) {
        console.error("Os dados do serviço estão incompletos.");
        return;
    }

    const indice = estado.servicos.findIndex(
        (item) => item.id === servico.id
    );

    if (indice >= 0) {
        estado.servicos.splice(indice, 1);
        botao.classList.remove("selected");
        botao.setAttribute("aria-pressed", "false");
    } else {
        estado.servicos.push(servico);
        botao.classList.add("selected");
        botao.setAttribute("aria-pressed", "true");
    }

    sincronizarServicos();
    atualizarResumoServicos();
}

export function sincronizarServicos() {
    estado.servico_ids = estado.servicos.map((item) => item.id);
    estado.servicos_nomes = estado.servicos.map((item) => item.nome);
    estado.valor_total = estado.servicos.reduce(
        (total, item) => total + Number(item.valor),
        0
    );
    estado.duracao_total = estado.servicos.reduce(
        (total, item) => total + Number(item.duracao),
        0
    );
}

export function atualizarResumoServicos() {
    const quantidade = estado.servicos.length;
    const quantidadeEl = document.getElementById(
        "servicosSelecionadosQuantidade"
    );
    const listaEl = document.getElementById(
        "servicosSelecionadosLista"
    );
    const valorEl = document.getElementById(
        "servicosSelecionadosValor"
    );
    const duracaoEl = document.getElementById(
        "servicosSelecionadosDuracao"
    );
    const continuarEl = document.getElementById("continuarServicos");

    if (quantidadeEl) {
        quantidadeEl.textContent = quantidade === 1
            ? "1 serviço selecionado"
            : `${quantidade} serviços selecionados`;
    }

    if (listaEl) {
        listaEl.innerHTML = estado.servicos.map((item) => `
            <div class="selected-service-item">
                <span>✓ ${item.nome}</span>
                <strong>${formatarMoeda(item.valor)}</strong>
            </div>
        `).join("");
    }

    if (valorEl) valorEl.textContent = formatarMoeda(estado.valor_total);
    if (duracaoEl) {
        duracaoEl.textContent = `${estado.duracao_total} minutos`;
    }

    if (continuarEl) {
        continuarEl.disabled = quantidade === 0;
        continuarEl.classList.toggle("disabled", quantidade === 0);
    }
}

export function avancarServicos() {
    if (!estado.servicos.length) {
        alert("Escolha pelo menos um serviço.");
        return;
    }

    adicionarBolha(estado.servicos_nomes.join(" + "));
    mostrarEtapa("funcionario");
}
