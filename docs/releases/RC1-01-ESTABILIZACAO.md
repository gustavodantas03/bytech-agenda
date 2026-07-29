# Release Candidate RC1.0.1

Primeiro checkpoint da finalização do Bytech Agenda.

## Alterações reais desta entrega

- Identificação da versão instalada no menu lateral (`RC1.0.1`).
- Assistente do WhatsApp mantido como tela obrigatória quando URL/API Key não existem.
- Texto do assistente corrigido: a Bytech configura a Evolution na VPS; o cliente apenas lê o QR Code.
- JavaScript do WhatsApp separado do HTML.
- Cache dos arquivos do módulo atualizado.
- Grade de indicadores corrigida para quatro cartões.
- Script `verificar_release.py` para auditar ambiente, banco, arquivos, segredo e modo debug.

## Teste imediato

1. Extraia esta versão em uma pasta nova.
2. Instale as dependências: `py -m pip install -r requirements.txt`.
3. Execute: `py verificar_release.py`.
4. Inicie o sistema e confirme no menu lateral a versão `RC1.0.1`.
5. Abra **Comunicação**. Sem URL/API Key, o assistente deve aparecer.

## Evolution API

Na VPS, a instalação terá uma URL própria, por exemplo:

`https://evolution.bytechce.com.br`

A API Key será criada na instalação. Cada empresa terá uma instância própria e conectará seu número por QR Code.
