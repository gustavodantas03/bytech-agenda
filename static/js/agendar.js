const estado = {
    cliente_nome: "",
    cliente_telefone: "",
    servico_id: null,
    servico_nome: "",
    funcionario_id: null,
    funcionario_nome: "",
    data: "",
    hora: ""
};

function mostrarEtapa(nome) {
    const etapas = {
        nome: 1,
        telefone: 2,
        servico: 3,
        funcionario: 4,
        data: 5,
        hora: 6,
        confirmacao: 6,
        sucesso: 6
    };

    document
        .querySelectorAll(".step")
        .forEach((step) => {
            step.classList.remove("active");
        });

    const etapaAtual = document.querySelector(
        `[data-step="${nome}"]`
    );

    if (etapaAtual) {
        etapaAtual.classList.add("active");
    }

    const numeroEtapa = etapas[nome] || 1;
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

    setTimeout(() => {
        const card = document.getElementById("chat");

        if (card) {
            card.scrollIntoView({
                behavior: "smooth",
                block: "start"
            });
        }
    }, 80);
}

function adicionarBolha(texto, tipo = "user") {
    const chat = document.getElementById("chat");
    const bolha = document.createElement("div");
    bolha.className = `bubble ${tipo}`;
    bolha.textContent = texto;
    chat.insertBefore(bolha, chat.querySelector(".step.active"));
}

function avancarNome() {
    const nome = document.getElementById("nome").value.trim();
    if (!nome) return alert("Digite seu nome.");
    estado.cliente_nome = nome;
    adicionarBolha(nome);
    mostrarEtapa("telefone");
}

function avancarTelefone() {
    const telefone = document.getElementById("telefone").value.trim();
    if (!telefone) return alert("Digite seu telefone.");
    estado.cliente_telefone = telefone;
    adicionarBolha(telefone);
    mostrarEtapa("servico");
}

function selecionarServico(botao) {
    estado.servico_id = Number(botao.dataset.id);
    estado.servico_nome = botao.dataset.nome;
    adicionarBolha(estado.servico_nome);
    mostrarEtapa("funcionario");
}

function selecionarFuncionario(botao) {
    estado.funcionario_id = Number(botao.dataset.id);
    estado.funcionario_nome = botao.dataset.nome;
    adicionarBolha(estado.funcionario_nome);
    mostrarEtapa("data");
}

async function selecionarData(botao) {
    estado.data = botao.dataset.data;
    adicionarBolha(botao.textContent.trim());

    const url = `/api/${window.APP_CONFIG.slug}/horarios?data=${estado.data}&funcionario_id=${estado.funcionario_id}`;
    const resposta = await fetch(url);
    const dados = await resposta.json();

    const container = document.getElementById("horarios");
    container.innerHTML = "";

    if (!dados.horarios || dados.horarios.length === 0) {
        container.innerHTML = "<p>Nenhum horário disponível nesta data.</p>";
    } else {
        dados.horarios.forEach(hora => {
            const elemento = document.createElement("button");
            elemento.className = "option";
            elemento.textContent = hora;
            elemento.onclick = () => selecionarHora(hora);
            container.appendChild(elemento);
        });
    }

    mostrarEtapa("hora");
}

function selecionarHora(hora) {
    estado.hora = hora;
    adicionarBolha(hora);

    document.getElementById("resumo").innerHTML = `
        <p><strong>Cliente:</strong> ${estado.cliente_nome}</p>
        <p><strong>WhatsApp:</strong> ${estado.cliente_telefone}</p>
        <p><strong>Serviço:</strong> ${estado.servico_nome}</p>
        <p><strong>Barbeiro:</strong> ${estado.funcionario_nome}</p>
        <p><strong>Data:</strong> ${estado.data}</p>
        <p><strong>Horário:</strong> ${estado.hora}</p>
    `;

    mostrarEtapa("confirmacao");
}

async function confirmarAgendamento() {
    const resposta = await fetch(`/api/${window.APP_CONFIG.slug}/agendamentos`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(estado)
    });

    const dados = await resposta.json();

    if (!resposta.ok) {
        alert(dados.erro || "Não foi possível concluir o agendamento.");
        if (resposta.status === 409) mostrarEtapa("data");
        return;
    }

    const numero = window.APP_CONFIG.telefone.replace(/\D/g, "");
    document.getElementById("whatsappLink").href =
        `https://wa.me/55${numero}?text=${encodeURIComponent(dados.whatsapp)}`;

    mostrarEtapa("sucesso");
}
