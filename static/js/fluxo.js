import { estado } from "./estado.js";
import { artigoProfissional, rotulos } from "./config.js";
import { limparTexto } from "./util.js";
import {
    adicionarBolha,
    marcarOpcao,
    mostrarEtapa,
} from "./interface.js";
import { carregarHorariosDisponiveis } from "./horarios.js";

export function avancarNome() {
    const campo = document.getElementById("nome");
    if (!campo) return alert("O campo de nome não foi encontrado.");

    const nome = limparTexto(campo.value);
    if (nome.length < 2) {
        alert("Digite um nome válido.");
        campo.focus();
        return;
    }

    estado.cliente_nome = nome;
    adicionarBolha(nome);
    mostrarEtapa("telefone");
}

export function avancarTelefone() {
    const campo = document.getElementById("telefone");
    if (!campo) return alert("O campo de telefone não foi encontrado.");

    const telefone = limparTexto(campo.value);
    const numeros = telefone.replace(/\D/g, "");

    if (numeros.length < 10) {
        alert("Digite um WhatsApp válido com DDD.");
        campo.focus();
        return;
    }

    estado.cliente_telefone = telefone;
    adicionarBolha(telefone);
    mostrarEtapa("servico");
}

export function selecionarFuncionario(botao) {
    if (!botao) return;

    const id = Number(botao.dataset.id);
    const nome = limparTexto(botao.dataset.nome);

    if (!id || !nome) {
        console.error("Os dados do profissional estão incompletos.");
        return;
    }

    estado.funcionario_id = id;
    estado.funcionario_nome = nome;

    marcarOpcao(
        '[data-step="funcionario"] .booking-option',
        botao
    );

    adicionarBolha(nome);
    mostrarEtapa("data");
}

export async function selecionarData(botao) {
    if (!botao) return;

    if (!estado.funcionario_id) {
        alert(
            `Escolha ${artigoProfissional()} ` +
            `${rotulos.profissionalSingular} antes de selecionar a data.`
        );
        mostrarEtapa("funcionario");
        return;
    }

    if (!estado.servicos.length) {
        alert("Escolha pelo menos um serviço antes de continuar.");
        mostrarEtapa("servico");
        return;
    }

    const data = limparTexto(botao.dataset.data);
    if (!data) return alert("Não foi possível identificar a data.");

    estado.data = data;
    estado.data_texto = limparTexto(botao.textContent);
    marcarOpcao('[data-step="data"] .booking-date-option', botao);
    adicionarBolha(estado.data_texto);

    await carregarHorariosDisponiveis();
}

export function configurarMascaraTelefone() {
    const campo = document.getElementById("telefone");
    if (!campo) return;

    campo.addEventListener("input", () => {
        let valor = campo.value.replace(/\D/g, "").slice(0, 11);

        if (valor.length <= 10) {
            valor = valor
                .replace(/^(\d{2})(\d)/, "($1) $2")
                .replace(/(\d{4})(\d)/, "$1-$2");
        } else {
            valor = valor
                .replace(/^(\d{2})(\d)/, "($1) $2")
                .replace(/(\d{5})(\d)/, "$1-$2");
        }

        campo.value = valor;
    });
}

export function configurarEnterNosCampos() {
    document.getElementById("nome")?.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            e.preventDefault();
            avancarNome();
        }
    });

    document.getElementById("telefone")?.addEventListener(
        "keydown",
        (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                avancarTelefone();
            }
        }
    );
}
