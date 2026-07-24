(function () {
    const tipo = document.getElementById('tipoPontuacao');
    const valorPonto = document.getElementById('valorPonto');
    const pontosAtendimento = document.getElementById('pontosAtendimento');
    const simuladorValor = document.getElementById('simuladorValor');
    const simuladorResultado = document.getElementById('simuladorResultado');
    const simuladorLabel = document.getElementById('simuladorLabel');

    function numero(valor) {
      const parsed = parseFloat(String(valor || '').replace(',', '.'));
      return Number.isFinite(parsed) ? parsed : 0;
    }

    function atualizarSimulador() {
      const modo = tipo ? tipo.value : 'valor';
      let pontos = 0;

      if (modo === 'atendimento') {
        simuladorLabel.textContent = 'Quantidade de atendimentos';
        simuladorValor.step = '1';
        pontos = Math.floor(numero(simuladorValor.value)) * Math.max(1, numero(pontosAtendimento.value));
      } else {
        simuladorLabel.textContent = 'Valor gasto pelo cliente';
        simuladorValor.step = '0.01';
        const divisor = numero(valorPonto.value);
        pontos = divisor > 0 ? Math.floor(numero(simuladorValor.value) / divisor) : 0;
      }

      simuladorResultado.textContent = pontos + (pontos === 1 ? ' ponto' : ' pontos');
    }

    [tipo, valorPonto, pontosAtendimento, simuladorValor].forEach(function (elemento) {
      if (elemento) {
        elemento.addEventListener('input', atualizarSimulador);
        elemento.addEventListener('change', atualizarSimulador);
      }
    });



    document.querySelectorAll(".ranking-item[data-percent]").forEach(function (item) {
      const percentual = Math.max(0, Math.min(100, Number(item.dataset.percent || 0)));
      const barra = item.querySelector(".ranking-fill");
      if (barra) barra.style.width = percentual + "%";
    });

    atualizarSimulador();
  })();
