export function limparTexto(valor) {
    return String(valor || "").trim();
}

export function formatarMoeda(valor) {
    return Number(valor || 0).toLocaleString("pt-BR", {
        style: "currency",
        currency: "BRL",
    });
}

export function formatarData(dataIso) {
    const data = limparTexto(dataIso);
    if (!data) return "";

    const partes = data.split("-");
    if (partes.length !== 3) return data;

    return `${partes[2]}/${partes[1]}/${partes[0]}`;
}

export function selecionarTodos(seletor) {
    return Array.from(document.querySelectorAll(seletor));
}
