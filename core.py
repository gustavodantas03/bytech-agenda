from datetime import date, datetime, timedelta
from functools import wraps
import json
import os
import secrets
import time
from uuid import uuid4

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for

from database import get_connection, init_db, DatabaseError, DatabaseIntegrityError
from config import Config
from logging_config import configurar_logs

configurar_logs()


from werkzeug.utils import secure_filename
from security import eh_hash_de_senha, gerar_hash_senha, senha_confere

DIAS_SEMANA = [
    "Segunda-feira",
    "Terça-feira",
    "Quarta-feira",
    "Quinta-feira",
    "Sexta-feira",
    "Sábado",
    "Domingo",
]

MESES = [
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
]


def saudacao():
    hora = datetime.now().hour

    if hora < 12:
        return "☀️ Bom dia"

    if hora < 18:
        return "☀️ Boa tarde"

    return "🌙 Boa noite"


def data_brasileira():
    hoje = datetime.now()

    return (
        f"{DIAS_SEMANA[hoje.weekday()]}, "
        f"{hoje.day} de "
        f"{MESES[hoje.month-1]} de "
        f"{hoje.year}"
    )

def normalizar_telefone(telefone):
    return "".join(
        caractere
        for caractere in str(telefone or "")
        if caractere.isdigit()
    )


LIMITE_TENTATIVAS_LOGIN = 5
BLOQUEIO_LOGIN_MINUTOS = 15

# Tabelas cujo login usa o mecanismo de bloqueio por tentativas — nunca
# vindas de entrada do usuário, sempre um destes dois literais fixos.
_TABELAS_LOGIN_PERMITIDAS = {"usuarios", "usuarios_master"}


def valor_linha(linha, chave, padrao=None):
    """Lê uma coluna de qualquer linha do banco (usuário, empresa, etc.)
    com segurança: nunca derruba a página se a coluna não existir na linha
    (ex.: banco de dados que ainda não passou pela migração mais recente).
    """

    if not linha:
        return padrao
    try:
        valor = linha[chave]
    except (IndexError, KeyError):
        return padrao
    return padrao if valor is None else valor


def minutos_bloqueio_restante(conta):
    """Se a conta estiver temporariamente bloqueada por tentativas erradas,
    devolve quantos minutos faltam para liberar. Caso contrário, None."""

    bloqueado_ate = valor_linha(conta, "bloqueado_ate")
    if not bloqueado_ate:
        return None
    try:
        expira_em = datetime.strptime(bloqueado_ate, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None
    restante = (expira_em - datetime.now()).total_seconds()
    if restante <= 0:
        return None
    return max(1, int(restante // 60) + 1)


def registrar_falha_login(conn, tabela, conta_id, tentativas_atuais):
    """Soma uma tentativa errada; bloqueia a conta temporariamente ao
    atingir o limite."""

    if tabela not in _TABELAS_LOGIN_PERMITIDAS:
        raise ValueError("Tabela de login inválida.")

    novas_tentativas = (tentativas_atuais or 0) + 1
    bloqueado_ate = None
    if novas_tentativas >= LIMITE_TENTATIVAS_LOGIN:
        bloqueado_ate = (
            datetime.now() + timedelta(minutes=BLOQUEIO_LOGIN_MINUTOS)
        ).strftime("%Y-%m-%d %H:%M:%S")
        novas_tentativas = 0

    try:
        conn.execute(
            f"UPDATE {tabela} SET tentativas_falhas = ?, bloqueado_ate = ? WHERE id = ?",
            (novas_tentativas, bloqueado_ate, conta_id),
        )
        conn.commit()
    except Exception:
        # Banco ainda não migrado (colunas novas ausentes) — não deixa o
        # login quebrar por causa disso; a proteção de bloqueio volta a
        # valer normalmente assim que a migração automática for concluída.
        conn.rollback()
        return False
    return bloqueado_ate is not None


def limpar_falhas_login(conn, tabela, conta_id):
    if tabela not in _TABELAS_LOGIN_PERMITIDAS:
        raise ValueError("Tabela de login inválida.")

    try:
        conn.execute(
            f"UPDATE {tabela} SET tentativas_falhas = 0, bloqueado_ate = NULL WHERE id = ?",
            (conta_id,),
        )
        conn.commit()
    except Exception:
        conn.rollback()


def mes_atual_competencia():
    """Retorna o mês corrente no formato YYYY-MM, calculado em Python.

    Evita depender de funções específicas de PostgreSQL (TO_CHAR) que não
    existem no SQLite.
    """

    return date.today().strftime("%Y-%m")


def meses_recentes(quantidade=6):
    """Retorna uma lista com as últimas `quantidade` competências (YYYY-MM),
    da mais antiga para a mais recente, incluindo o mês atual.

    Calculado inteiramente em Python para funcionar da mesma forma no
    SQLite e no PostgreSQL (substitui combinações de DATE_TRUNC/
    generate_series/INTERVAL, que são exclusivas do PostgreSQL).
    """

    hoje = date.today()
    competencias = []
    ano, mes = hoje.year, hoje.month
    for indice in range(quantidade - 1, -1, -1):
        mes_calculado = mes - indice
        ano_calculado = ano
        while mes_calculado <= 0:
            mes_calculado += 12
            ano_calculado -= 1
        competencias.append(f"{ano_calculado:04d}-{mes_calculado:02d}")
    return competencias


def buscar_ou_criar_cliente(
    conn,
    empresa_id,
    nome,
    telefone,
):
    telefone_normalizado = normalizar_telefone(
        telefone
    )

    cliente = conn.execute(
        """
        SELECT *
        FROM clientes
        WHERE empresa_id = ?
          AND telefone = ?
        """,
        (
            empresa_id,
            telefone_normalizado,
        ),
    ).fetchone()

    if cliente:
        conn.execute(
            """
            UPDATE clientes
            SET
                nome = ?,
                atualizado_em = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                nome,
                cliente["id"],
            ),
        )

        return cliente["id"]

    cursor = conn.execute(
        """
        INSERT INTO clientes (
            empresa_id,
            nome,
            telefone
        )
        VALUES (?, ?, ?)
        """,
        (
            empresa_id,
            nome,
            telefone_normalizado,
        ),
    )

    return cursor.lastrowid

SEGMENTOS = {
    "barbearia": {
        "nome": "Barbearia",
        "icone": "💈",
        "template_admin": "barbearia",
        "template_cliente": "premium",
        "cor_principal": "#1E3A8A",
        "cor_secundaria": "#60A5FA",
        "cor_botao": "#2563EB",
        "cor_sidebar": "#0F172A",
        "servicos": [
            ("Corte masculino", 25.00, 40),
            ("Barba", 15.00, 30),
            ("Corte + barba", 35.00, 60),
        ],
        "funcionarios": [
            ("Barbeiro 1", "Barbeiro"),
        ],
    },
    "manicure": {
        "nome": "Manicure",
        "icone": "💅",
        "template_admin": "manicure",
        "template_cliente": "premium",
        "cor_principal": "#EC4899",
        "cor_secundaria": "#FBCFE8",
        "cor_botao": "#DB2777",
        "cor_sidebar": "#831843",
        "servicos": [
            ("Manicure", 35.00, 60),
            ("Pedicure", 40.00, 60),
            ("Manicure + pedicure", 70.00, 120),
        ],
        "funcionarios": [
            ("Manicure 1", "Manicure"),
        ],
    },
    "depilacao": {
        "nome": "Depilação",
        "icone": "✨",
        "template_admin": "depilacao",
        "template_cliente": "premium",
        "cor_principal": "#14B8A6",
        "cor_secundaria": "#99F6E4",
        "cor_botao": "#0D9488",
        "cor_sidebar": "#115E59",
        "servicos": [
            ("Axila", 25.00, 20),
            ("Meia perna", 40.00, 40),
            ("Perna completa", 60.00, 60),
            ("Virilha", 45.00, 40),
        ],
        "funcionarios": [
            ("Depiladora 1", "Depiladora"),
        ],
    },
    "salao": {
        "nome": "Salão de Beleza",
        "icone": "💇",
        "template_admin": "salao",
        "template_cliente": "premium",
        "cor_principal": "#7C3AED",
        "cor_secundaria": "#DDD6FE",
        "cor_botao": "#8B5CF6",
        "cor_sidebar": "#4C1D95",
        "servicos": [
            ("Corte feminino", 60.00, 60),
            ("Escova", 50.00, 50),
            ("Hidratação", 70.00, 60),
            ("Coloração", 120.00, 120),
            ("Luzes", 250.00, 180),
            ("Progressiva", 180.00, 180),
            ("Penteado", 100.00, 90),
            ("Maquiagem", 120.00, 90),
        ],
        "funcionarios": [
            ("Cabeleireira 1", "Cabeleireira"),
        ],
    },
    "estetica": {
        "nome": "Estética",
        "icone": "💆",
        "template_admin": "estetica",
        "template_cliente": "premium",
        "cor_principal": "#059669",
        "cor_secundaria": "#A7F3D0",
        "cor_botao": "#10B981",
        "cor_sidebar": "#065F46",
        "servicos": [
            ("Limpeza de pele", 120.00, 90),
            ("Peeling facial", 150.00, 60),
            ("Drenagem linfática", 100.00, 60),
            ("Massagem modeladora", 110.00, 60),
            ("Tratamento facial", 180.00, 90),
            ("Tratamento corporal", 200.00, 90),
        ],
        "funcionarios": [
            ("Esteticista 1", "Esteticista"),
        ],
    },
    "maquiagem": {
        "nome": "Maquiagem",
        "icone": "💄",
        "template_admin": "maquiagem",
        "template_cliente": "premium",
        "cor_principal": "#B91C1C",
        "cor_secundaria": "#FECACA",
        "cor_botao": "#DC2626",
        "cor_sidebar": "#7F1D1D",
        "servicos": [
            ("Maquiagem social", 120.00, 90),
            ("Maquiagem para festa", 150.00, 90),
            ("Maquiagem para noiva", 300.00, 150),
            ("Maquiagem artística", 200.00, 120),
            ("Curso de automaquiagem", 250.00, 180),
        ],
        "funcionarios": [
            ("Maquiadora 1", "Maquiadora"),
        ],
    },
    "nail_designer": {
        "nome": "Nail Designer",
        "icone": "💍",
        "template_admin": "nail_designer",
        "template_cliente": "premium",
        "cor_principal": "#4F46E5",
        "cor_secundaria": "#C7D2FE",
        "cor_botao": "#6366F1",
        "cor_sidebar": "#312E81",
        "servicos": [
            ("Alongamento em gel", 150.00, 150),
            ("Manutenção de alongamento", 100.00, 120),
            ("Banho de gel", 80.00, 90),
            ("Blindagem", 70.00, 60),
            ("Nail art", 40.00, 40),
            ("Remoção de alongamento", 50.00, 60),
        ],
        "funcionarios": [
            ("Nail Designer 1", "Nail Designer"),
        ],
    },
    "harmonizacao": {
        "nome": "Harmonização Facial",
        "icone": "💉",
        "template_admin": "harmonizacao",
        "template_cliente": "premium",
        "cor_principal": "#0284C7",
        "cor_secundaria": "#BAE6FD",
        "cor_botao": "#0EA5E9",
        "cor_sidebar": "#0C4A6E",
        "servicos": [
            ("Avaliação facial", 100.00, 40),
            ("Toxina botulínica", 900.00, 60),
            ("Preenchimento labial", 1000.00, 60),
            ("Preenchimento facial", 1200.00, 90),
            ("Bioestimulador de colágeno", 1500.00, 90),
        ],
        "funcionarios": [
            ("Especialista 1", "Especialista"),
        ],
    },
    "massoterapia": {
        "nome": "Massoterapia",
        "icone": "💆",
        "template_admin": "massoterapia",
        "template_cliente": "premium",
        "cor_principal": "#65A30D",
        "cor_secundaria": "#D9F99D",
        "cor_botao": "#84CC16",
        "cor_sidebar": "#365314",
        "servicos": [
            ("Massagem relaxante", 100.00, 60),
            ("Massagem terapêutica", 120.00, 60),
            ("Massagem desportiva", 130.00, 60),
            ("Drenagem linfática", 110.00, 60),
            ("Liberação miofascial", 140.00, 60),
        ],
        "funcionarios": [
            ("Massoterapeuta 1", "Massoterapeuta"),
        ],
    },
    "podologia": {
        "nome": "Podologia",
        "icone": "🦶",
        "template_admin": "podologia",
        "template_cliente": "premium",
        "cor_principal": "#0F766E",
        "cor_secundaria": "#CCFBF1",
        "cor_botao": "#14B8A6",
        "cor_sidebar": "#134E4A",
        "servicos": [
            ("Avaliação podológica", 60.00, 30),
            ("Podologia completa", 120.00, 60),
            ("Tratamento de unha encravada", 150.00, 60),
            ("Tratamento de calosidades", 100.00, 60),
            ("Hidratação dos pés", 70.00, 40),
        ],
        "funcionarios": [
            ("Podóloga 1", "Podóloga"),
        ],
    },
    "clinica_capilar": {
        "nome": "Clínica Capilar",
        "icone": "💇‍♂️",
        "template_admin": "clinica_capilar",
        "template_cliente": "premium",
        "cor_principal": "#475569",
        "cor_secundaria": "#E2E8F0",
        "cor_botao": "#64748B",
        "cor_sidebar": "#1E293B",
        "servicos": [
            ("Avaliação capilar", 100.00, 40),
            ("Terapia capilar", 180.00, 60),
            ("Hidratação profunda", 150.00, 60),
            ("Tratamento antiqueda", 250.00, 90),
            ("Detox do couro cabeludo", 170.00, 60),
        ],
        "funcionarios": [
            ("Terapeuta Capilar 1", "Terapeuta Capilar"),
        ],
    },
    "banho_tosa": {
        "nome": "Banho e Tosa",
        "icone": "🐶",
        "template_admin": "banho_tosa",
        "template_cliente": "premium",
        "cor_principal": "#F59E0B",
        "cor_secundaria": "#93C5FD",
        "cor_botao": "#2563EB",
        "cor_sidebar": "#7C4A21",
        "servicos": [
            ("Banho pequeno porte", 50.00, 60),
            ("Banho médio porte", 70.00, 75),
            ("Banho grande porte", 90.00, 90),
            ("Tosa higiênica", 45.00, 40),
            ("Tosa completa", 100.00, 90),
            ("Corte de unhas", 20.00, 20),
        ],
        "funcionarios": [
            ("Pet Groomer 1", "Pet Groomer"),
        ],
    },
    "sobrancelhas": {
        "nome": "Design de Sobrancelhas",
        "icone": "👁️",
        "template_admin": "sobrancelhas",
        "template_cliente": "premium",
        "cor_principal": "#D97706",
        "cor_secundaria": "#FDE68A",
        "cor_botao": "#B45309",
        "cor_sidebar": "#78350F",
        "servicos": [
            ("Design de sobrancelhas", 35.00, 30),
            ("Design com henna", 45.00, 40),
            ("Brow lamination", 90.00, 60),
        ],
        "funcionarios": [
            ("Designer 1", "Designer"),
        ],
    },
}


def obter_config_segmento(segmento):
    segmento = (segmento or "barbearia").strip().lower()
    return SEGMENTOS.get(segmento, SEGMENTOS["barbearia"])



def obter_ui_segmento(segmento):
    segmento = (segmento or "barbearia").strip().lower()

    interfaces = {
        "barbearia": {
            "icone": "💈",
            "nome_segmento": "Barbearia",
            "nome_empresa": "barbearia",
            "nome_empresa_titulo": "Barbearia",
            "menu_empresa": "Minha barbearia",
            "profissional_singular": "barbeiro",
            "profissional_plural": "barbeiros",
            "cargo_padrao": "Barbeiro",

            "hero_titulo": "Seu próximo corte",
            "hero_destaque": "começa aqui.",
            "hero_descricao": (
                "Escolha seus serviços, o barbeiro e o melhor "
                "horário para cuidar do seu visual."
            ),
        },

        "manicure": {
            "icone": "💅",
            "nome_segmento": "Manicure",
            "nome_empresa": "espaço de manicure",
            "nome_empresa_titulo": "Espaço de manicure",
            "menu_empresa": "Meu espaço",
            "profissional_singular": "manicure",
            "profissional_plural": "manicures",
            "cargo_padrao": "Manicure",

            "hero_titulo": "Suas unhas",
            "hero_destaque": "merecem cuidado.",
            "hero_descricao": (
                "Escolha seus serviços, a manicure e o melhor "
                "horário para cuidar das suas unhas."
            ),
        },

        "depilacao": {
            "icone": "✨",
            "nome_segmento": "Depilação",
            "nome_empresa": "espaço de depilação",
            "nome_empresa_titulo": "Espaço de depilação",
            "menu_empresa": "Meu espaço",
            "profissional_singular": "depiladora",
            "profissional_plural": "depiladoras",
            "cargo_padrao": "Depiladora",

            "hero_titulo": "Seu cuidado",
            "hero_destaque": "começa aqui.",
            "hero_descricao": (
                "Escolha o procedimento, a depiladora e o melhor "
                "horário para o seu atendimento."
            ),
        },

        "salao": {
            "icone": "💇",
            "nome_segmento": "Salão de Beleza",
            "nome_empresa": "salão de beleza",
            "nome_empresa_titulo": "Salão de Beleza",
            "menu_empresa": "Meu salão",
            "profissional_singular": "cabeleireira",
            "profissional_plural": "cabeleireiras",
            "cargo_padrao": "Cabeleireira",

            "hero_titulo": "Transforme",
            "hero_destaque": "o seu visual.",
            "hero_descricao": (
                "Escolha seus serviços, a profissional e o melhor "
                "horário para renovar sua beleza."
            ),
            "mockup": {
    "saudacao": "Olá! Qual serviço deseja agendar?",
    "servicos": [
        {
            "icone": "✨",
            "nome": "Serviço principal",
            "valor": "R$ 50,00",
        },
        {
            "icone": "⭐",
            "nome": "Serviço especial",
            "valor": "R$ 80,00",
        },
    ],
    "card_confirmacao_titulo": "Agendamento confirmado",
    "card_confirmacao_texto": "Hoje às 14:40",
    "card_horario_titulo": "Próximo horário",
    "card_horario_texto": "15:20 disponível",
    "card_profissional_titulo": "Profissionais",
    "card_profissional_texto": "Escolha seu profissional",
},
        },

        "estetica": {
            "icone": "💆",
            "nome_segmento": "Estética",
            "nome_empresa": "clínica de estética",
            "nome_empresa_titulo": "Clínica de Estética",
            "menu_empresa": "Minha clínica",
            "profissional_singular": "esteticista",
            "profissional_plural": "esteticistas",
            "cargo_padrao": "Esteticista",

            "hero_titulo": "Cuide de você",
            "hero_destaque": "por inteiro.",
            "hero_descricao": (
                "Escolha seu tratamento, a esteticista e o melhor "
                "horário para o seu momento de cuidado."
            ),
            "mockup": {
    "saudacao": "Olá! Qual serviço deseja agendar?",
    "servicos": [
        {
            "icone": "✨",
            "nome": "Serviço principal",
            "valor": "R$ 50,00",
        },
        {
            "icone": "⭐",
            "nome": "Serviço especial",
            "valor": "R$ 80,00",
        },
    ],
    "card_confirmacao_titulo": "Agendamento confirmado",
    "card_confirmacao_texto": "Hoje às 14:40",
    "card_horario_titulo": "Próximo horário",
    "card_horario_texto": "15:20 disponível",
    "card_profissional_titulo": "Profissionais",
    "card_profissional_texto": "Escolha seu profissional",
},
        },

        "maquiagem": {
            "icone": "💄",
            "nome_segmento": "Maquiagem",
            "nome_empresa": "studio de maquiagem",
            "nome_empresa_titulo": "Studio de Maquiagem",
            "menu_empresa": "Meu studio",
            "profissional_singular": "maquiadora",
            "profissional_plural": "maquiadoras",
            "cargo_padrao": "Maquiadora",

            "hero_titulo": "Realce",
            "hero_destaque": "a sua beleza.",
            "hero_descricao": (
                "Escolha o estilo de maquiagem, a profissional "
                "e o melhor horário para sua produção."
            ),
            "mockup": {
    "saudacao": "Olá! Qual serviço deseja agendar?",
    "servicos": [
        {
            "icone": "✨",
            "nome": "Serviço principal",
            "valor": "R$ 50,00",
        },
        {
            "icone": "⭐",
            "nome": "Serviço especial",
            "valor": "R$ 80,00",
        },
    ],
    "card_confirmacao_titulo": "Agendamento confirmado",
    "card_confirmacao_texto": "Hoje às 14:40",
    "card_horario_titulo": "Próximo horário",
    "card_horario_texto": "15:20 disponível",
    "card_profissional_titulo": "Profissionais",
    "card_profissional_texto": "Escolha seu profissional",
},
        },

        "nail_designer": {
            "icone": "💍",
            "nome_segmento": "Nail Designer",
            "nome_empresa": "studio nail designer",
            "nome_empresa_titulo": "Studio Nail Designer",
            "menu_empresa": "Meu studio",
            "profissional_singular": "nail designer",
            "profissional_plural": "nail designers",
            "cargo_padrao": "Nail Designer",

            "hero_titulo": "Unhas que",
            "hero_destaque": "expressam seu estilo.",
            "hero_descricao": (
                "Escolha o procedimento, a nail designer e o melhor "
                "horário para transformar suas unhas."
            ),
            "mockup": {
    "saudacao": "Olá! Qual serviço deseja agendar?",
    "servicos": [
        {
            "icone": "✨",
            "nome": "Serviço principal",
            "valor": "R$ 50,00",
        },
        {
            "icone": "⭐",
            "nome": "Serviço especial",
            "valor": "R$ 80,00",
        },
    ],
    "card_confirmacao_titulo": "Agendamento confirmado",
    "card_confirmacao_texto": "Hoje às 14:40",
    "card_horario_titulo": "Próximo horário",
    "card_horario_texto": "15:20 disponível",
    "card_profissional_titulo": "Profissionais",
    "card_profissional_texto": "Escolha seu profissional",
},
        },

        "harmonizacao": {
            "icone": "💉",
            "nome_segmento": "Harmonização Facial",
            "nome_empresa": "clínica de harmonização facial",
            "nome_empresa_titulo": "Clínica de Harmonização Facial",
            "menu_empresa": "Minha clínica",
            "profissional_singular": "especialista",
            "profissional_plural": "especialistas",
            "cargo_padrao": "Especialista",

            "hero_titulo": "Valorize",
            "hero_destaque": "sua melhor versão.",
            "hero_descricao": (
                "Escolha o procedimento, o especialista e o melhor "
                "horário para sua avaliação ou atendimento."
            ),
            "mockup": {
    "saudacao": "Olá! Qual serviço deseja agendar?",
    "servicos": [
        {
            "icone": "✨",
            "nome": "Serviço principal",
            "valor": "R$ 50,00",
        },
        {
            "icone": "⭐",
            "nome": "Serviço especial",
            "valor": "R$ 80,00",
        },
    ],
    "card_confirmacao_titulo": "Agendamento confirmado",
    "card_confirmacao_texto": "Hoje às 14:40",
    "card_horario_titulo": "Próximo horário",
    "card_horario_texto": "15:20 disponível",
    "card_profissional_titulo": "Profissionais",
    "card_profissional_texto": "Escolha seu profissional",
},
        },

        "massoterapia": {
            "icone": "💆",
            "nome_segmento": "Massoterapia",
            "nome_empresa": "espaço de massoterapia",
            "nome_empresa_titulo": "Espaço de Massoterapia",
            "menu_empresa": "Meu espaço",
            "profissional_singular": "massoterapeuta",
            "profissional_plural": "massoterapeutas",
            "cargo_padrao": "Massoterapeuta",

            "hero_titulo": "Relaxe o corpo",
            "hero_destaque": "e renove a mente.",
            "hero_descricao": (
                "Escolha a massagem, o massoterapeuta e o melhor "
                "horário para o seu momento de bem-estar."
            ),
            "mockup": {
    "saudacao": "Olá! Qual serviço deseja agendar?",
    "servicos": [
        {
            "icone": "✨",
            "nome": "Serviço principal",
            "valor": "R$ 50,00",
        },
        {
            "icone": "⭐",
            "nome": "Serviço especial",
            "valor": "R$ 80,00",
        },
    ],
    "card_confirmacao_titulo": "Agendamento confirmado",
    "card_confirmacao_texto": "Hoje às 14:40",
    "card_horario_titulo": "Próximo horário",
    "card_horario_texto": "15:20 disponível",
    "card_profissional_titulo": "Profissionais",
    "card_profissional_texto": "Escolha seu profissional",
},
        },

        "podologia": {
            "icone": "🦶",
            "nome_segmento": "Podologia",
            "nome_empresa": "clínica de podologia",
            "nome_empresa_titulo": "Clínica de Podologia",
            "menu_empresa": "Minha clínica",
            "profissional_singular": "podóloga",
            "profissional_plural": "podólogas",
            "cargo_padrao": "Podóloga",

            "hero_titulo": "Seus pés",
            "hero_destaque": "merecem atenção.",
            "hero_descricao": (
                "Escolha o atendimento, a podóloga e o melhor "
                "horário para cuidar da saúde dos seus pés."
            ),
            "mockup": {
    "saudacao": "Olá! Qual serviço deseja agendar?",
    "servicos": [
        {
            "icone": "✨",
            "nome": "Serviço principal",
            "valor": "R$ 50,00",
        },
        {
            "icone": "⭐",
            "nome": "Serviço especial",
            "valor": "R$ 80,00",
        },
    ],
    "card_confirmacao_titulo": "Agendamento confirmado",
    "card_confirmacao_texto": "Hoje às 14:40",
    "card_horario_titulo": "Próximo horário",
    "card_horario_texto": "15:20 disponível",
    "card_profissional_titulo": "Profissionais",
    "card_profissional_texto": "Escolha seu profissional",
},
        },

        "clinica_capilar": {
            "icone": "💇‍♂️",
            "nome_segmento": "Clínica Capilar",
            "nome_empresa": "clínica capilar",
            "nome_empresa_titulo": "Clínica Capilar",
            "menu_empresa": "Minha clínica",
            "profissional_singular": "terapeuta capilar",
            "profissional_plural": "terapeutas capilares",
            "cargo_padrao": "Terapeuta Capilar",

            "hero_titulo": "Saúde e cuidado",
            "hero_destaque": "para seus cabelos.",
            "hero_descricao": (
                "Escolha seu tratamento, o terapeuta capilar "
                "e o melhor horário para o atendimento."
            ),
            "mockup": {
    "saudacao": "Olá! Qual serviço deseja agendar?",
    "servicos": [
        {
            "icone": "✨",
            "nome": "Serviço principal",
            "valor": "R$ 50,00",
        },
        {
            "icone": "⭐",
            "nome": "Serviço especial",
            "valor": "R$ 80,00",
        },
    ],
    "card_confirmacao_titulo": "Agendamento confirmado",
    "card_confirmacao_texto": "Hoje às 14:40",
    "card_horario_titulo": "Próximo horário",
    "card_horario_texto": "15:20 disponível",
    "card_profissional_titulo": "Profissionais",
    "card_profissional_texto": "Escolha seu profissional",
},
        },

   "banho_tosa": {
    "icone": "🐶",
    "nome_segmento": "Banho e Tosa",
    "nome_empresa": "pet shop",
    "nome_empresa_titulo": "Banho e Tosa",
    "menu_empresa": "Meu pet shop",

    "profissional_singular": "pet groomer",
    "profissional_plural": "pet groomers",
    "cargo_padrao": "Pet Groomer",

    "hero_titulo": "Seu melhor amigo",
    "hero_destaque": "merece esse cuidado.",
    "hero_descricao": (
        "Agende banho, tosa e outros cuidados para o seu pet "
        "em poucos cliques."
    ),

    "mockup": {
        "saudacao": "Olá! Como podemos cuidar do seu pet?",
        "servicos": [
            {
                "icone": "🛁",
                "nome": "Banho",
                "valor": "R$ 70,00",
            },
            {
                "icone": "✂️",
                "nome": "Tosa higiênica",
                "valor": "R$ 45,00",
            },
        ],
        "card_confirmacao_titulo": "Banho confirmado",
        "card_confirmacao_texto": "Hoje às 14:40",
        "card_horario_titulo": "Próximo horário",
        "card_horario_texto": "15:20 disponível",
        "card_profissional_titulo": "Pet groomers",
        "card_profissional_texto": "Escolha seu profissional",
    },
},

        "sobrancelhas": {
            "icone": "👁️",
            "nome_segmento": "Design de sobrancelhas",
            "nome_empresa": "studio de sobrancelhas",
            "nome_empresa_titulo": "Studio de sobrancelhas",
            "menu_empresa": "Meu studio",
            "profissional_singular": "designer",
            "profissional_plural": "designers",
            "cargo_padrao": "Designer",

            "hero_titulo": "Valorize",
            "hero_destaque": "o seu olhar.",
            "hero_descricao": (
                "Escolha o procedimento, a designer e o melhor "
                "horário para destacar sua beleza."
            ),
            "mockup": {
    "saudacao": "Olá! Qual serviço deseja agendar?",
    "servicos": [
        {
            "icone": "✨",
            "nome": "Serviço principal",
            "valor": "R$ 50,00",
        },
        {
            "icone": "⭐",
            "nome": "Serviço especial",
            "valor": "R$ 80,00",
        },
    ],
    "card_confirmacao_titulo": "Agendamento confirmado",
    "card_confirmacao_texto": "Hoje às 14:40",
    "card_horario_titulo": "Próximo horário",
    "card_horario_texto": "15:20 disponível",
    "card_profissional_titulo": "Profissionais",
    "card_profissional_texto": "Escolha seu profissional",
},
        },
    }



    return interfaces.get(segmento, interfaces["barbearia"])


app = Flask(__name__)
app.config.from_object(Config)

UPLOAD_FOLDER = app.config["UPLOAD_FOLDER"]
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ---------------------------------------------------------------------------
# Proteção CSRF
# ---------------------------------------------------------------------------
# Implementação própria e leve (sem depender do Flask-WTF): cada sessão
# recebe um token aleatório; toda requisição que muda dados (POST/PUT/
# PATCH/DELETE) precisa devolver esse mesmo token, seja num campo de
# formulário oculto (_csrf_token) seja no header X-CSRFToken (usado pelas
# chamadas via JavaScript/fetch). Isso impede que outro site force o
# navegador de alguém já logado a executar uma ação sem que a pessoa saiba.

_METODOS_PROTEGIDOS_CSRF = {"POST", "PUT", "PATCH", "DELETE"}

# Módulos isentos: rotas públicas de agendamento (sem sessão autenticada de
# dono de empresa) e o webhook da Evolution API (chamada servidor-a-servidor,
# sem navegador e sem cookie de sessão envolvidos).
_MODULOS_ISENTOS_CSRF = {"routes.publico", "routes.webhooks"}


def csrf_token():
    """Gera (uma vez por sessão) e devolve o token CSRF atual."""

    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_hex(32)
        session["_csrf_token"] = token
    return token


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def protecao_csrf():
    if request.method not in _METODOS_PROTEGIDOS_CSRF:
        return

    endpoint = request.endpoint
    if endpoint and endpoint in app.view_functions:
        if app.view_functions[endpoint].__module__ in _MODULOS_ISENTOS_CSRF:
            return

    token_esperado = session.get("_csrf_token")
    token_enviado = request.form.get("_csrf_token") or request.headers.get("X-CSRFToken")
    if not token_enviado and request.is_json:
        token_enviado = (request.get_json(silent=True) or {}).get("_csrf_token")

    if not token_esperado or not token_enviado or not secrets.compare_digest(
        str(token_esperado), str(token_enviado)
    ):
        if request.is_json or request.path.startswith("/api/"):
            return jsonify(
                sucesso=False,
                erro="Sessão expirada ou inválida. Atualize a página e tente novamente.",
            ), 400
        flash(
            "Sua sessão expirou ou a página ficou aberta por muito tempo. Tente novamente.",
            "erro",
        )
        return redirect(request.referrer or url_for("admin_dashboard"))


def arquivo_permitido(nome_arquivo):
    return (
        "." in nome_arquivo
        and nome_arquivo.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )

def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("empresa_id"):
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapped_view


def recurso_required(chave_recurso):
    """Restringe uma rota administrativa ao recurso contratado pela empresa."""
    def decorator(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            empresa_id = session.get("empresa_id")
            if not empresa_id:
                return redirect(url_for("admin_login"))

            from services.recursos import empresa_tem_recurso
            conn = get_connection()
            permitido = empresa_tem_recurso(conn, empresa_id, chave_recurso)
            conn.close()

            if not permitido:
                flash(
                    "Este recurso não está incluído no plano atual. Fale com a Bytech para liberar o módulo.",
                    "erro",
                )
                return redirect(url_for("admin_dashboard"))
            return view(*args, **kwargs)
        return wrapped_view
    return decorator


# ---------------------------------------------------------------------------
# Permissões por usuário (equipe)
# ---------------------------------------------------------------------------
# Além do plano contratado (recurso_required, acima), cada login individual
# dentro de uma empresa pode ter acesso restrito a algumas seções. O
# "proprietario" sempre tem acesso total; um "colaborador" só acessa as
# seções marcadas em session["permissoes"].

PERMISSOES_DISPONIVEIS = {
    "agenda": "Agenda",
    "clientes": "Clientes / CRM",
    "fidelidade": "Fidelidade",
    "servicos": "Serviços",
    "funcionarios": "Profissionais",
    "whatsapp": "Comunicação (WhatsApp)",
    "relatorios": "Relatórios",
    "configuracoes": "Dados do estabelecimento",
}

# Mapeia o módulo (arquivo routes/*.py) para a chave de permissão da seção.
# Rotas de arquivos não listados aqui (ex.: dashboard, minha conta, equipe)
# ficam sempre acessíveis a qualquer usuário logado da empresa.
_MODULO_PERMISSAO = {
    "routes.agenda": "agenda",
    "routes.clientes": "clientes",
    "routes.crm_inteligencia": "clientes",
    "routes.fidelidade": "fidelidade",
    "routes.servicos": "servicos",
    "routes.funcionarios": "funcionarios",
    "routes.whatsapp": "whatsapp",
    "routes.relatorios": "relatorios",
}

# Endpoints específicos que sobrescrevem a regra do módulo (têm prioridade
# sobre o mapa acima). Usado quando um arquivo mistura rotas restritas com
# rotas que devem ficar sempre abertas (ex.: conta.py).
_ENDPOINT_PERMISSAO = {
    "admin_meu_espaco": "configuracoes",
    "admin_barbearia": "configuracoes",
}


def _permissoes_da_sessao():
    bruto = session.get("permissoes")
    return bruto if isinstance(bruto, list) else []


@app.before_request
def verificar_permissoes_colaborador():
    """Bloqueia colaboradores fora das seções liberadas para eles.

    Não afeta o proprietário (acesso sempre total) nem sessões do painel
    master, que não têm session["papel"] == "colaborador".
    """

    if session.get("papel") != "colaborador":
        return

    endpoint = request.endpoint
    if not endpoint or endpoint not in app.view_functions:
        return

    chave = _ENDPOINT_PERMISSAO.get(endpoint)
    if chave is None:
        modulo = app.view_functions[endpoint].__module__
        chave = _MODULO_PERMISSAO.get(modulo)

    if not chave:
        return

    if chave not in _permissoes_da_sessao():
        flash(
            "Você não tem permissão para acessar esta área. Fale com o responsável da empresa.",
            "erro",
        )
        return redirect(url_for("admin_dashboard"))


def apenas_proprietario(view):
    """Restringe a rota ao usuário com papel 'proprietario' da empresa."""

    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("empresa_id"):
            return redirect(url_for("admin_login"))
        if session.get("papel") == "colaborador":
            flash(
                "Apenas o proprietário da conta pode gerenciar a equipe.",
                "erro",
            )
            return redirect(url_for("admin_dashboard"))
        return view(*args, **kwargs)
    return wrapped_view


def gerar_horarios():
    horarios = []
    inicio = datetime.strptime("09:00", "%H:%M")
    fim = datetime.strptime("18:00", "%H:%M")
    intervalo = timedelta(minutes=40)

    atual = inicio
    while atual < fim:
        horarios.append(atual.strftime("%H:%M"))
        atual += intervalo

    return horarios


# ---------------------------------------------------------------------------
# Horário de funcionamento configurável por empresa
# ---------------------------------------------------------------------------
# Cada empresa pode definir, por dia da semana, se abre e em que horário.
# Guardado como JSON na coluna empresas.horarios_funcionamento:
#   {"0": {"aberto": true, "abertura": "09:00", "fechamento": "20:00"}, ...}
# onde a chave é o dia da semana no padrão de Python (0=segunda ... 6=domingo).

DIAS_SEMANA_LABELS = [
    "Segunda-feira",
    "Terça-feira",
    "Quarta-feira",
    "Quinta-feira",
    "Sexta-feira",
    "Sábado",
    "Domingo",
]


def _valor_empresa(empresa, chave, padrao=None):
    """Lê uma coluna da empresa com segurança, funcionando tanto com
    sqlite3.Row quanto com o dict-like do PostgresConnection, mesmo que a
    coluna não tenha sido incluída na consulta original."""

    if not empresa:
        return padrao
    try:
        valor = empresa[chave]
    except (IndexError, KeyError):
        return padrao
    return padrao if valor is None else valor


def horarios_funcionamento_padrao():
    """Configuração de fábrica: todo dia aberto das 09:00 às 18:00 — igual
    ao comportamento fixo que o sistema tinha antes desta função existir.
    É o que vale para qualquer empresa que ainda não personalizou nada."""

    return {
        str(dia): {"aberto": True, "abertura": "09:00", "fechamento": "18:00"}
        for dia in range(7)
    }


def obter_horarios_funcionamento(empresa):
    """Lê e valida o horário de funcionamento salvo da empresa, caindo no
    padrão de fábrica se não estiver configurado ou estiver corrompido."""

    padrao = horarios_funcionamento_padrao()
    bruto = _valor_empresa(empresa, "horarios_funcionamento")
    if not bruto:
        return padrao

    try:
        configurado = json.loads(bruto)
    except (TypeError, ValueError):
        return padrao

    if not isinstance(configurado, dict):
        return padrao

    resultado = {}
    for dia in range(7):
        chave = str(dia)
        item = configurado.get(chave)
        if (
            isinstance(item, dict)
            and isinstance(item.get("abertura"), str)
            and isinstance(item.get("fechamento"), str)
        ):
            resultado[chave] = {
                "aberto": bool(item.get("aberto", True)),
                "abertura": item["abertura"],
                "fechamento": item["fechamento"],
            }
        else:
            resultado[chave] = padrao[chave]
    return resultado


def gerar_horarios_do_dia(empresa, data_referencia):
    """Gera os horários disponíveis (ex.: ['09:00', '09:40', ...]) para uma
    empresa numa data específica, respeitando o dia da semana configurado e
    o intervalo entre agendamentos. Devolve lista vazia se a empresa não
    abre naquele dia."""

    configuracao = obter_horarios_funcionamento(empresa)
    dia = configuracao.get(str(data_referencia.weekday()))

    if not dia or not dia.get("aberto"):
        return []

    try:
        inicio = datetime.strptime(dia["abertura"], "%H:%M")
        fim = datetime.strptime(dia["fechamento"], "%H:%M")
    except (KeyError, ValueError):
        return []

    try:
        intervalo_minutos = int(_valor_empresa(empresa, "intervalo_agendamento_minutos", 40))
    except (TypeError, ValueError):
        intervalo_minutos = 40
    intervalo_minutos = max(5, intervalo_minutos)
    intervalo = timedelta(minutes=intervalo_minutos)

    horarios = []
    atual = inicio
    while atual < fim:
        horarios.append(atual.strftime("%H:%M"))
        atual += intervalo
    return horarios

def master_login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("master_id"):
            return redirect(url_for("master_login"))

        return view(*args, **kwargs)

    return wrapped_view




@app.context_processor
def contexto_admin_multissegmento():
    empresa_id = session.get("empresa_id")

    if not empresa_id:
        return {}

    conn = get_connection()
    empresa_admin = conn.execute(
        "SELECT * FROM empresas WHERE id = ?",
        (empresa_id,),
    ).fetchone()
    if not empresa_admin:
        conn.close()
        return {}

    from services.recursos import obter_recursos_empresa, uso_do_plano
    recursos_empresa = obter_recursos_empresa(conn, empresa_id)
    uso_plano = uso_do_plano(conn, empresa_id)
    conn.close()

    segmento = (
        empresa_admin["segmento"]
        if "segmento" in empresa_admin.keys()
        else "barbearia"
    )

    return {
        "empresa_admin": empresa_admin,
        "ui": obter_ui_segmento(segmento),
        "recursos_empresa": recursos_empresa,
        "uso_plano": uso_plano,
        "tem_recurso": lambda chave: chave in recursos_empresa,
    }



@app.get("/health")
def healthcheck():
    """Verificação simples para VPS, proxy reverso e monitoramento."""
    try:
        conn = get_connection()
        conn.execute("SELECT 1").fetchone()
        migrations = conn.execute("SELECT COUNT(*) AS total FROM schema_migrations").fetchone()
        conn.close()
        return jsonify(status="ok", banco="ok", migrations=migrations["total"]), 200
    except Exception as exc:
        app.logger.exception("Falha no healthcheck")
        return jsonify(status="erro", banco="erro", detalhe=str(exc)), 503


_db_initialized = False
_worker_embutido_iniciado = False


def _iniciar_worker_embutido():
    """Inicia, em uma thread separada, o processamento automático da fila
    de mensagens do WhatsApp (confirmações, lembretes e cancelamentos).

    Sem isso, as mensagens ficavam apenas enfileiradas e só eram enviadas
    quando alguém clicava manualmente em "Atualizar status" no painel de
    Comunicação, ou quando o script separado do worker era executado à parte.

    Pode ser desativado com BYTECH_EMBED_WORKER=0 no .env — por exemplo, ao
    publicar com múltiplos workers/processos do Gunicorn, caso em que o envio
    deve ficar a cargo do processo único em scripts/evolution/executar_worker.py
    (ou do atalho INICIAR-WORKER-WHATSAPP.bat) para não haver duplicidade.
    """

    global _worker_embutido_iniciado
    if _worker_embutido_iniciado:
        return

    if os.getenv("BYTECH_EMBED_WORKER", "1") != "1":
        return

    # Com o reloader de debug do Flask, o processo "monitor" reinicia o
    # processo real e não deve rodar o worker (senão ele roda em dobro).
    debug_ligado = os.getenv("BYTECH_DEBUG", "0") == "1"
    if debug_ligado and os.getenv("WERKZEUG_RUN_MAIN") != "true":
        return

    import logging
    import threading

    def _loop():
        from services.scheduler_service import SchedulerConfig, executar_ciclo

        logger = logging.getLogger("bytech.worker_embutido")
        config = SchedulerConfig.from_env()
        logger.info(
            "Worker embutido iniciado (intervalo=%ss, lote=%s).",
            config.intervalo_segundos,
            config.lote,
        )
        while True:
            try:
                executar_ciclo(config)
            except Exception:
                logger.exception(
                    "Falha no ciclo automático de mensagens; nova tentativa no próximo intervalo."
                )
            time.sleep(config.intervalo_segundos)

    threading.Thread(target=_loop, name="bytech-worker-embutido", daemon=True).start()
    _worker_embutido_iniciado = True


@app.before_request
def setup():
    """Garante a estrutura do banco e o worker de mensagens uma única vez por processo."""
    global _db_initialized
    if not _db_initialized:
        init_db()
        _db_initialized = True
    _iniciar_worker_embutido()


















































