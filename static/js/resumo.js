import { estado } from "./estado.js";
import { formatarData, formatarMoeda } from "./util.js";

export function montarResumoAgendamento() {
    const resumo = document.getElementById("resumo");
    if (!resumo) return;

    const servicos = estado.servicos.map((item) => `
        <div class="booking-summary-service">
            <span>${item.nome}</span>
            <strong>${formatarMoeda(item.valor)}</strong>
        </div>
    `).join("");

    resumo.innerHTML = `
        <div class="booking-summary-section">
            <span class="booking-summary-label">Cliente</span>
            <strong>${estado.cliente_nome}</strong>
            <small>${estado.cliente_telefone}</small>
        </div>

        <div class="booking-summary-section">
            <span class="booking-summary-label">Serviços</span>
            <div class="booking-summary-services">${servicos}</div>
        </div>

        <div class="booking-summary-row">
            <div>
                <span class="booking-summary-label">Profissional</span>
                <strong>${estado.funcionario_nome}</strong>
            </div>
            <div>
                <span class="booking-summary-label">Data e horário</span>
                <strong>
                    ${estado.data_texto || formatarData(estado.data)}
                    às ${estado.hora}
                </strong>
            </div>
        </div>

        <div class="booking-summary-total">
            <div>
                <span>Tempo estimado</span>
                <strong>${estado.duracao_total} minutos</strong>
            </div>
            <div>
                <span>Valor total</span>
                <strong>${formatarMoeda(estado.valor_total)}</strong>
            </div>
        </div>
    `;
}
