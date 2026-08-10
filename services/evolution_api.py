"""Cliente e regras do módulo de comunicação via Evolution API.

A integração foi isolada do restante do sistema para permitir troca futura de
provedor sem alterar as rotas de agenda.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from urllib import error, parse, request

from database import get_connection


MODELOS_PADRAO = {
    "confirmacao": (
        "Confirmação de agendamento",
        "Olá {{nome}}! 👋\n\nRecebemos seu agendamento na {{empresa}}.\n\n"
        "📅 {{data}}\n⏰ {{hora}}\n✨ {{servico}}\n👤 {{profissional}}\n\n"
        "Responda com:\n1️⃣ Confirmar\n2️⃣ Reagendar\n3️⃣ Cancelar",
    ),
    "lembrete_24h": (
        "Lembrete de 24 horas",
        "Olá {{nome}}! Passando para lembrar do seu atendimento amanhã na "
        "{{empresa}}, às {{hora}}. Serviço: {{servico}}.",
    ),
    "lembrete_2h": (
        "Lembrete de 2 horas",
        "Olá {{nome}}! Seu atendimento na {{empresa}} começa às {{hora}}. "
        "Estamos esperando por você!",
    ),
    "cancelamento": (
        "Cancelamento",
        "Olá {{nome}}. Seu agendamento de {{servico}}, marcado para {{data}} "
        "às {{hora}}, foi cancelado.",
    ),
    "pos_atendimento": (
        "Pós-atendimento",
        "Olá {{nome}}! Obrigado por escolher a {{empresa}}. Esperamos que tenha "
        "gostado do atendimento. 😊",
    ),
}


@dataclass
class EvolutionResult:
    ok: bool
    data: dict
    status_code: int | None = None
    error: str | None = None


class EvolutionClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 15):
        self.base_url = (base_url or "").strip().rstrip("/")
        self.api_key = (api_key or "").strip()
        self.timeout = max(int(timeout or 15), 3)

    def _call(self, method: str, path: str, payload: dict | None = None) -> EvolutionResult:
        if not self.base_url or not self.api_key:
            return EvolutionResult(False, {}, error="URL ou API Key não configurada.")

        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"apikey": self.api_key, "Content-Type": "application/json"}
        req = request.Request(
            f"{self.base_url}{path}", data=body, headers=headers, method=method
        )
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
                data = json.loads(raw) if raw else {}
                return EvolutionResult(True, data, response.status)
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                data = {"resposta": raw}
            message = data.get("message") or data.get("error") or f"HTTP {exc.code}"
            return EvolutionResult(False, data, exc.code, str(message))
        except (error.URLError, TimeoutError, ValueError) as exc:
            return EvolutionResult(False, {}, error=str(exc))

    def criar_instancia(self, instance_name: str) -> EvolutionResult:
        return self._call(
            "POST",
            "/instance/create",
            {
                "instanceName": instance_name,
                "integration": "WHATSAPP-BAILEYS",
                "qrcode": True,
            },
        )

    def conectar(self, instance_name: str, numero: str | None = None) -> EvolutionResult:
        caminho = f"/instance/connect/{instance_name}"
        if numero:
            caminho += f"?number={parse.quote(numero, safe='')}"
        return self._call("GET", caminho)

    def estado(self, instance_name: str) -> EvolutionResult:
        return self._call("GET", f"/instance/connectionState/{instance_name}")

    def detalhes_instancia(self, instance_name: str) -> EvolutionResult:
        nome = parse.quote(instance_name, safe="")
        return self._call("GET", f"/instance/fetchInstances?instanceName={nome}")

    def logout(self, instance_name: str) -> EvolutionResult:
        return self._call("DELETE", f"/instance/logout/{instance_name}")

    def enviar_texto(self, instance_name: str, number: str, text: str) -> EvolutionResult:
        return self._call(
            "POST",
            f"/message/sendText/{instance_name}",
            {"number": number, "text": text},
        )



def extrair_perfil_instancia(data: dict, instance_name: str = "") -> dict:
    """Normaliza os dados de perfil retornados por diferentes builds da Evolution v2."""
    itens = data if isinstance(data, list) else data.get("instances", data.get("data", data))
    if isinstance(itens, dict):
        itens = [itens]
    if not isinstance(itens, list):
        itens = []

    escolhido = {}
    for item in itens:
        if not isinstance(item, dict):
            continue
        instancia = item.get("instance") if isinstance(item.get("instance"), dict) else item
        nome = instancia.get("instanceName") or instancia.get("name") or item.get("name")
        if not instance_name or nome == instance_name:
            escolhido = item
            break
    if not escolhido and itens:
        escolhido = itens[0] if isinstance(itens[0], dict) else {}

    instancia = escolhido.get("instance") if isinstance(escolhido.get("instance"), dict) else escolhido
    numero = (instancia.get("ownerJid") or instancia.get("number") or instancia.get("phone")
              or escolhido.get("ownerJid") or escolhido.get("number") or "")
    numero = str(numero).split("@")[0].split(":")[0]
    return {
        "numero": numero,
        "nome": instancia.get("profileName") or instancia.get("name") or escolhido.get("profileName") or "",
        "foto": instancia.get("profilePicUrl") or instancia.get("profilePictureUrl")
                or escolhido.get("profilePicUrl") or escolhido.get("profilePictureUrl") or "",
    }

def obter_configuracao_global() -> tuple[str, str, int]:
    """Retorna as credenciais da Evolution mantidas pela infraestrutura Bytech.

    As variáveis globais têm prioridade. Os campos por empresa permanecem no
    banco apenas por compatibilidade com instalações anteriores.
    """
    base_url = os.getenv("EVOLUTION_BASE_URL", "").strip().rstrip("/")
    api_key = os.getenv("EVOLUTION_API_KEY", "").strip()
    try:
        timeout = max(int(os.getenv("EVOLUTION_TIMEOUT", "15")), 3)
    except ValueError:
        timeout = 15
    return base_url, api_key, timeout


def infraestrutura_evolution_configurada() -> bool:
    base_url, api_key, _ = obter_configuracao_global()
    return bool(base_url and api_key)


def cliente_evolution_para_config(config) -> "EvolutionClient":
    """Cria o cliente usando primeiro as credenciais globais do servidor."""
    base_url, api_key, timeout_global = obter_configuracao_global()
    if not base_url:
        base_url = (config["base_url"] or "").strip()
    if not api_key:
        api_key = (config["api_key"] or "").strip()
    timeout = config["timeout_segundos"] or timeout_global
    return EvolutionClient(base_url, api_key, timeout)


def garantir_configuracao_empresa(conn, empresa_id: int) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO whatsapp_configuracoes
        (empresa_id, instance_name, timeout_segundos, max_tentativas)
        VALUES (?, ?, 15, 3)
        """,
        (empresa_id, f"bytech_empresa_{empresa_id}"),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO whatsapp_automacoes
        (empresa_id, confirmacao_ativa, lembrete_24h_ativo, lembrete_2h_ativo,
         cancelamento_ativo, pos_atendimento_ativo, aniversario_ativo,
         cliente_inativo_ativo)
        VALUES (?, 1, 1, 1, 1, 0, 0, 0)
        """,
        (empresa_id,),
    )
    for tipo, (nome, mensagem) in MODELOS_PADRAO.items():
        conn.execute(
            """
            INSERT OR IGNORE INTO whatsapp_modelos
            (empresa_id, tipo, nome, mensagem, ativo)
            VALUES (?, ?, ?, ?, 1)
            """,
            (empresa_id, tipo, nome, mensagem),
        )
    conn.commit()


def normalizar_numero_whatsapp(numero: str) -> str:
    digitos = re.sub(r"\D", "", str(numero or ""))
    if not digitos:
        return ""
    # Telefones brasileiros cadastrados sem DDI recebem 55 automaticamente.
    if len(digitos) in (10, 11):
        digitos = "55" + digitos
    return digitos


def renderizar_modelo(texto: str, dados: dict) -> str:
    resultado = texto or ""
    for chave, valor in dados.items():
        resultado = resultado.replace("{{" + chave + "}}", str(valor or ""))
    return resultado


def _dados_agendamento(conn, empresa_id: int, agendamento_id: int):
    return conn.execute(
        """
        SELECT a.*, e.nome AS empresa_nome, e.telefone AS empresa_telefone,
               s.nome AS servico_nome, f.nome AS profissional_nome
        FROM agendamentos a
        JOIN empresas e ON e.id = a.empresa_id
        JOIN servicos s ON s.id = a.servico_id
        LEFT JOIN funcionarios f ON f.id = a.funcionario_id
        WHERE a.id = ? AND a.empresa_id = ?
        """,
        (agendamento_id, empresa_id),
    ).fetchone()


def enviar_mensagem_agendamento(empresa_id: int, agendamento_id: int, tipo: str) -> EvolutionResult:
    """Compatibilidade: adiciona a mensagem à fila sem bloquear o agendamento."""
    from services.communication_queue import enfileirar_mensagem_agendamento
    return enfileirar_mensagem_agendamento(empresa_id, agendamento_id, tipo)
