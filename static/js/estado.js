export const estado = {
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
    hora: "",
};

export function limparAgendamento() {
    estado.cliente_nome = "";
    estado.cliente_telefone = "";
    estado.servicos = [];
    estado.servico_ids = [];
    estado.servicos_nomes = [];
    estado.valor_total = 0;
    estado.duracao_total = 0;
    estado.funcionario_id = null;
    estado.funcionario_nome = "";
    estado.data = "";
    estado.data_texto = "";
    estado.hora = "";
}
