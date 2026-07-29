import {
    avancarNome,
    avancarTelefone,
    selecionarData,
    selecionarFuncionario,
    configurarEnterNosCampos,
    configurarMascaraTelefone,
} from "./fluxo.js";
import {
    avancarServicos,
    atualizarResumoServicos,
    selecionarServico,
} from "./servicos.js";
import {
    carregarHorariosDisponiveis,
    selecionarHora,
} from "./horarios.js";
import { confirmarAgendamento } from "./api.js";
import { mostrarEtapa, voltarEtapa } from "./interface.js";

/*
 * Os templates atuais usam onclick no HTML.
 * Por isso, as ações públicas são expostas no objeto window.
 */
Object.assign(window, {
    avancarNome,
    avancarTelefone,
    selecionarServico,
    avancarServicos,
    selecionarFuncionario,
    selecionarData,
    carregarHorariosDisponiveis,
    selecionarHora,
    confirmarAgendamento,
    mostrarEtapa,
    voltarEtapa,
});

document.addEventListener("DOMContentLoaded", () => {
    configurarMascaraTelefone();
    configurarEnterNosCampos();
    atualizarResumoServicos();

    setTimeout(() => {
        document.getElementById("nome")?.focus();
    }, 300);
});
