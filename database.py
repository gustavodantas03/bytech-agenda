"""Camada de banco do Bytech Agenda.

Produção: PostgreSQL quando DATABASE_URL estiver configurada.
Desenvolvimento: SQLite como fallback para facilitar testes locais.
"""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable

BASE_DIR = Path(__file__).resolve().parent
DATABASE_DIR = BASE_DIR / "database"
DB_PATH = DATABASE_DIR / "bytech_agenda.db"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
USING_POSTGRES = DATABASE_URL.startswith(("postgresql://", "postgres://"))

try:
    import psycopg
    DatabaseError = psycopg.Error
    DatabaseIntegrityError = psycopg.IntegrityError
except ImportError:
    DatabaseError = sqlite3.Error
    DatabaseIntegrityError = sqlite3.IntegrityError


def _replace_qmarks(sql: str) -> str:
    """Troca placeholders ? por %s sem alterar interrogações dentro de strings."""
    out: list[str] = []
    in_single = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        if ch == "'":
            out.append(ch)
            if in_single and i + 1 < len(sql) and sql[i + 1] == "'":
                out.append("'")
                i += 2
                continue
            in_single = not in_single
        elif ch == "?" and not in_single:
            out.append("%s")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _translate_sql(sql: str) -> str:
    """Traduz construções SQL legadas do SQLite para PostgreSQL.

    Esta função só é usada pela conexão PostgreSQL. Assim, as consultas
    originais continuam compatíveis com o fallback SQLite.
    """
    sql = sql.replace("COLLATE NOCASE", "")
    # SQLite usa GROUP_CONCAT; no PostgreSQL o equivalente é STRING_AGG.
    # As consultas do projeto utilizam a mesma assinatura com expressão e
    # separador, portanto a troca do nome preserva os parâmetros existentes.
    sql = re.sub(r"\bGROUP_CONCAT\s*\(", "STRING_AGG(", sql, flags=re.I)
    sql = re.sub(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT INTO", sql, flags=re.I)
    if re.search(r"^\s*INSERT\s+INTO\b", sql, flags=re.I) and " OR IGNORE " not in sql.upper():
        # As consultas originalmente INSERT OR IGNORE já foram alteradas acima.
        # Marca pelo texto original usando uma heurística segura.
        pass
    sql = _replace_qmarks(sql)
    return sql


def _split_sql_script(script: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_single = False
    in_double = False
    for ch in script:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        if ch == ";" and not in_single and not in_double:
            stmt = "".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
        else:
            current.append(ch)
    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


class PostgresCursor:
    def __init__(self, cursor, lastrowid: int | None = None):
        self._cursor = cursor
        self.lastrowid = lastrowid

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def __iter__(self):
        return iter(self._cursor)


class PostgresConnection:
    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql: str, params: Iterable[Any] | None = None):
        original = sql
        ignore_conflict = bool(re.search(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", original, re.I))
        translated = _translate_sql(sql)
        if ignore_conflict and "ON CONFLICT" not in translated.upper():
            translated = translated.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"

        cursor = self._conn.cursor()
        cursor.execute(translated, tuple(params or ()))
        lastrowid = None
        if re.match(r"^\s*INSERT\s+INTO\b", translated, re.I):
            try:
                seq_cursor = self._conn.cursor()
                seq_cursor.execute("SELECT LASTVAL() AS id")
                row = seq_cursor.fetchone()
                lastrowid = row["id"] if row else None
                seq_cursor.close()
            except Exception:
                self._conn.rollback()
                raise
        return PostgresCursor(cursor, lastrowid)

    def executemany(self, sql: str, seq_of_params: Iterable[Iterable[Any]]):
        """Executa a mesma instrução para vários conjuntos de parâmetros.

        Mantém a interface usada pelo sqlite3 e traduz placeholders/conflitos
        para o psycopg 3.
        """
        original = sql
        ignore_conflict = bool(re.search(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", original, re.I))
        translated = _translate_sql(sql)
        if ignore_conflict and "ON CONFLICT" not in translated.upper():
            translated = translated.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"

        cursor = self._conn.cursor()
        cursor.executemany(translated, [tuple(params) for params in seq_of_params])
        return PostgresCursor(cursor)

    def executescript(self, script: str):
        for statement in _split_sql_script(script):
            statement = re.sub(
                r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT",
                "BIGSERIAL PRIMARY KEY",
                statement,
                flags=re.I,
            )
            self.execute(statement)
        return self

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def cursor(self):
        return self._conn.cursor()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()


def get_connection():
    if USING_POSTGRES:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError(
                "PostgreSQL configurado, mas o pacote psycopg não está instalado. "
                "Execute: pip install -r requirements.txt"
            ) from exc
        conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        return PostgresConnection(conn)

    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _column_exists(conn, table, column):
    if USING_POSTGRES:
        row = conn.execute(
            """
            SELECT 1
              FROM information_schema.columns
             WHERE table_schema = 'public'
               AND table_name = ?
               AND column_name = ?
            """,
            (table, column),
        ).fetchone()
        return bool(row)

    columns = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(item["name"] == column for item in columns)
def init_db():
    conn = get_connection()

    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS empresas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                telefone TEXT,
                instagram TEXT,
                endereco TEXT,
                maps_url TEXT,
                descricao TEXT,
                logo TEXT,
                segmento TEXT NOT NULL DEFAULT 'barbearia',
                template_admin TEXT NOT NULL DEFAULT 'barbearia',
                template_cliente TEXT NOT NULL DEFAULT 'premium',
                cor_principal TEXT DEFAULT '#111827',
                cor_secundaria TEXT DEFAULT '#d4af37',
                cor_botao TEXT DEFAULT '#d4af37',
                cor_sidebar TEXT DEFAULT '#0f172a',
                horario_texto TEXT,
                ativo INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS usuarios_master (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT NOT NULL UNIQUE,
                senha TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL,
                nome TEXT NOT NULL,
                telefone TEXT NOT NULL,
                email TEXT,
                data_nascimento TEXT,
                instagram TEXT,
                observacoes TEXT,
                pontos_fidelidade INTEGER NOT NULL DEFAULT 0,
                recompensas_disponiveis INTEGER NOT NULL DEFAULT 0,
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                atualizado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (empresa_id)
                    REFERENCES empresas(id),
                UNIQUE (empresa_id, telefone)
            );

            CREATE TABLE IF NOT EXISTS servicos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL,
                nome TEXT NOT NULL,
                valor REAL NOT NULL DEFAULT 0,
                duracao INTEGER NOT NULL DEFAULT 40,
                ativo INTEGER DEFAULT 1,
                FOREIGN KEY (empresa_id)
                    REFERENCES empresas(id)
            );

            CREATE TABLE IF NOT EXISTS funcionarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL,
                nome TEXT NOT NULL,
                cargo TEXT DEFAULT 'Barbeiro',
                ativo INTEGER DEFAULT 1,
                FOREIGN KEY (empresa_id)
                    REFERENCES empresas(id)
            );

            CREATE TABLE IF NOT EXISTS agendamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL,
                cliente_id INTEGER,
                cliente_nome TEXT NOT NULL,
                cliente_telefone TEXT NOT NULL,
                servico_id INTEGER NOT NULL,
                funcionario_id INTEGER,
                data TEXT NOT NULL,
                hora TEXT NOT NULL,
                status TEXT DEFAULT 'agendado',
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                duracao_total INTEGER NOT NULL DEFAULT 40,
                valor_total REAL NOT NULL DEFAULT 0,
                FOREIGN KEY (empresa_id)
                    REFERENCES empresas(id),
                FOREIGN KEY (cliente_id)
                    REFERENCES clientes(id),
                FOREIGN KEY (servico_id)
                    REFERENCES servicos(id),
                FOREIGN KEY (funcionario_id)
                    REFERENCES funcionarios(id)
            );

            CREATE TABLE IF NOT EXISTS agendamento_servicos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agendamento_id INTEGER NOT NULL,
                servico_id INTEGER NOT NULL,
                ordem INTEGER DEFAULT 1,
                FOREIGN KEY (agendamento_id)
                    REFERENCES agendamentos(id)
                    ON DELETE CASCADE,
                FOREIGN KEY (servico_id)
                    REFERENCES servicos(id),
                UNIQUE (agendamento_id, servico_id)
            );

            CREATE TABLE IF NOT EXISTS fidelidade_movimentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL,
                cliente_id INTEGER NOT NULL,
                agendamento_id INTEGER,
                tipo TEXT NOT NULL,
                quantidade INTEGER NOT NULL DEFAULT 1,
                descricao TEXT,
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (empresa_id)
                    REFERENCES empresas(id),
                FOREIGN KEY (cliente_id)
                    REFERENCES clientes(id),
                FOREIGN KEY (agendamento_id)
                    REFERENCES agendamentos(id)
                    ON DELETE CASCADE,
                UNIQUE (agendamento_id, tipo)
            );

            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL,
                usuario TEXT NOT NULL UNIQUE,
                senha TEXT NOT NULL,
                FOREIGN KEY (empresa_id)
                    REFERENCES empresas(id)
            );

            CREATE TABLE IF NOT EXISTS cobrancas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL,
                competencia TEXT NOT NULL,
                descricao TEXT,
                valor REAL NOT NULL DEFAULT 0,
                vencimento TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'aberta',
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                atualizado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (empresa_id) REFERENCES empresas(id),
                UNIQUE (empresa_id, competencia)
            );

            CREATE TABLE IF NOT EXISTS pagamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL,
                cobranca_id INTEGER NOT NULL,
                valor REAL NOT NULL,
                data_pagamento TEXT NOT NULL,
                forma_pagamento TEXT DEFAULT 'Pix',
                observacoes TEXT,
                recibo_numero TEXT NOT NULL UNIQUE,
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (empresa_id) REFERENCES empresas(id),
                FOREIGN KEY (cobranca_id) REFERENCES cobrancas(id)
            );

            CREATE TABLE IF NOT EXISTS logs_financeiros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER,
                cobranca_id INTEGER,
                pagamento_id INTEGER,
                acao TEXT NOT NULL,
                descricao TEXT,
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (empresa_id) REFERENCES empresas(id),
                FOREIGN KEY (cobranca_id) REFERENCES cobrancas(id),
                FOREIGN KEY (pagamento_id) REFERENCES pagamentos(id)
            );

            CREATE TABLE IF NOT EXISTS whatsapp_configuracoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL UNIQUE,
                base_url TEXT,
                api_key TEXT,
                instance_name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'desconectado',
                numero_conectado TEXT,
                qr_code TEXT,
                timeout_segundos INTEGER NOT NULL DEFAULT 15,
                max_tentativas INTEGER NOT NULL DEFAULT 3,
                ultima_sincronizacao TEXT,
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                atualizado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS whatsapp_automacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL UNIQUE,
                confirmacao_ativa INTEGER NOT NULL DEFAULT 1,
                lembrete_24h_ativo INTEGER NOT NULL DEFAULT 1,
                lembrete_2h_ativo INTEGER NOT NULL DEFAULT 1,
                cancelamento_ativo INTEGER NOT NULL DEFAULT 1,
                pos_atendimento_ativo INTEGER NOT NULL DEFAULT 0,
                aniversario_ativo INTEGER NOT NULL DEFAULT 0,
                cliente_inativo_ativo INTEGER NOT NULL DEFAULT 0,
                atualizado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS whatsapp_modelos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL,
                tipo TEXT NOT NULL,
                nome TEXT NOT NULL,
                mensagem TEXT NOT NULL,
                ativo INTEGER NOT NULL DEFAULT 1,
                atualizado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE,
                UNIQUE (empresa_id, tipo)
            );

            CREATE TABLE IF NOT EXISTS whatsapp_historico (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL,
                agendamento_id INTEGER,
                cliente_id INTEGER,
                tipo TEXT NOT NULL,
                telefone TEXT NOT NULL,
                mensagem TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pendente',
                erro TEXT,
                resposta_api TEXT,
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                enviado_em TEXT,
                FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE,
                FOREIGN KEY (agendamento_id) REFERENCES agendamentos(id) ON DELETE SET NULL,
                FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_whatsapp_historico_empresa_data
                ON whatsapp_historico (empresa_id, criado_em);


            CREATE TABLE IF NOT EXISTS whatsapp_fila (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL,
                agendamento_id INTEGER,
                cliente_id INTEGER,
                tipo TEXT NOT NULL,
                telefone TEXT NOT NULL,
                mensagem TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pendente',
                tentativas INTEGER NOT NULL DEFAULT 0,
                max_tentativas INTEGER NOT NULL DEFAULT 3,
                agendado_para TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                proxima_tentativa_em TEXT,
                ultimo_erro TEXT,
                resposta_api TEXT,
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                atualizado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                enviado_em TEXT,
                FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE,
                FOREIGN KEY (agendamento_id) REFERENCES agendamentos(id) ON DELETE CASCADE,
                FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON DELETE SET NULL,
                UNIQUE (empresa_id, agendamento_id, tipo)
            );

            CREATE INDEX IF NOT EXISTS idx_whatsapp_fila_processamento
                ON whatsapp_fila (status, agendado_para, proxima_tentativa_em);
            CREATE INDEX IF NOT EXISTS idx_whatsapp_fila_empresa
                ON whatsapp_fila (empresa_id, criado_em);

            CREATE TABLE IF NOT EXISTS crm_configuracoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL UNIQUE,
                dias_inatividade INTEGER NOT NULL DEFAULT 60,
                dias_risco INTEGER NOT NULL DEFAULT 30,
                vip_valor_minimo REAL NOT NULL DEFAULT 500,
                vip_visitas_minimas INTEGER NOT NULL DEFAULT 8,
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                atualizado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS crm_campanhas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL,
                nome TEXT NOT NULL,
                publico_alvo TEXT NOT NULL DEFAULT 'todos',
                mensagem TEXT NOT NULL,
                data_inicio TEXT,
                data_fim TEXT,
                status TEXT NOT NULL DEFAULT 'rascunho',
                ativo INTEGER NOT NULL DEFAULT 0,
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                atualizado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_crm_campanhas_empresa
                ON crm_campanhas (empresa_id, criado_em);

            CREATE TABLE IF NOT EXISTS configuracoes_financeiras (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                dia_vencimento_padrao INTEGER NOT NULL DEFAULT 10,
                tolerancia_dias_padrao INTEGER NOT NULL DEFAULT 5,
                bloquear_apos_dias_padrao INTEGER NOT NULL DEFAULT 15,
                multa_percentual REAL NOT NULL DEFAULT 0,
                juros_mensal_percentual REAL NOT NULL DEFAULT 0,
                desconto_antecipacao_percentual REAL NOT NULL DEFAULT 0,
                forma_pagamento_padrao TEXT NOT NULL DEFAULT 'Pix',
                mensagem_cobranca TEXT,
                atualizado_em TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS planos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL UNIQUE,
                descricao TEXT,
                valor REAL NOT NULL DEFAULT 0,
                limite_profissionais INTEGER,
                limite_usuarios INTEGER,
                limite_agendamentos INTEGER,
                ativo INTEGER NOT NULL DEFAULT 1,
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                atualizado_em TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS recursos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chave TEXT NOT NULL UNIQUE,
                nome TEXT NOT NULL,
                descricao TEXT,
                ativo INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS plano_recursos (
                plano_id INTEGER NOT NULL,
                recurso_id INTEGER NOT NULL,
                PRIMARY KEY (plano_id, recurso_id),
                FOREIGN KEY (plano_id) REFERENCES planos(id) ON DELETE CASCADE,
                FOREIGN KEY (recurso_id) REFERENCES recursos(id) ON DELETE CASCADE
            );
            """
        )

        if not _column_exists(conn, "empresas", "logo"):
            conn.execute(
                "ALTER TABLE empresas ADD COLUMN logo TEXT"
            )

        campos_cliente = {
            "email": "TEXT",
            "data_nascimento": "TEXT",
            "instagram": "TEXT",
            "observacoes": "TEXT",
            "ativo": "INTEGER NOT NULL DEFAULT 1",
        }

        for coluna, definicao in campos_cliente.items():
            if not _column_exists(conn, "clientes", coluna):
                conn.execute(
                    f"ALTER TABLE clientes ADD COLUMN {coluna} {definicao}"
                )

        campos_empresa = {
            "segmento": "TEXT NOT NULL DEFAULT 'barbearia'",
            "template_admin": "TEXT NOT NULL DEFAULT 'barbearia'",
            "template_cliente": "TEXT NOT NULL DEFAULT 'premium'",
            "cor_secundaria": "TEXT DEFAULT '#d4af37'",
            "cor_botao": "TEXT DEFAULT '#d4af37'",
            "cor_sidebar": "TEXT DEFAULT '#0f172a'",
            "plano": "TEXT NOT NULL DEFAULT 'Essencial'",
            "mensalidade": "REAL NOT NULL DEFAULT 0",
            "dia_vencimento": "INTEGER NOT NULL DEFAULT 10",
            "status_pagamento": "TEXT NOT NULL DEFAULT 'em_dia'",
            "proximo_vencimento": "TEXT",
            "ultimo_pagamento": "TEXT",
            "tolerancia_dias": "INTEGER NOT NULL DEFAULT 5",
            "bloquear_apos_dias": "INTEGER NOT NULL DEFAULT 15",
            "dias_atraso": "INTEGER NOT NULL DEFAULT 0",
            "bloqueado_financeiro": "INTEGER NOT NULL DEFAULT 0",
            "bloqueio_manual": "INTEGER NOT NULL DEFAULT 0",
            "financeiro_atualizado_em": "TEXT",
            "plano_id": "INTEGER",
        }

        for coluna, definicao in campos_empresa.items():
            if not _column_exists(conn, "empresas", coluna):
                conn.execute(
                    f"ALTER TABLE empresas ADD COLUMN {coluna} {definicao}"
                )

        campos_whatsapp = {
            "nome_perfil": "TEXT",
            "foto_perfil": "TEXT",
            "conectado_em": "TEXT",
        }
        for coluna, definicao in campos_whatsapp.items():
            if not _column_exists(conn, "whatsapp_configuracoes", coluna):
                conn.execute(f"ALTER TABLE whatsapp_configuracoes ADD COLUMN {coluna} {definicao}")

        campos_cobranca = {
            "desconto": "REAL NOT NULL DEFAULT 0",
            "acrescimo": "REAL NOT NULL DEFAULT 0",
            "valor_final": "REAL",
            "cancelada_em": "TEXT",
            "motivo_cancelamento": "TEXT",
        }
        for coluna, definicao in campos_cobranca.items():
            if not _column_exists(conn, "cobrancas", coluna):
                conn.execute(f"ALTER TABLE cobrancas ADD COLUMN {coluna} {definicao}")

        campos_pagamento = {
            "valor_original": "REAL NOT NULL DEFAULT 0",
            "desconto": "REAL NOT NULL DEFAULT 0",
            "acrescimo": "REAL NOT NULL DEFAULT 0",
            "valor_final": "REAL NOT NULL DEFAULT 0",
            "estornado": "INTEGER NOT NULL DEFAULT 0",
            "estornado_em": "TEXT",
            "motivo_estorno": "TEXT",
        }
        for coluna, definicao in campos_pagamento.items():
            if not _column_exists(conn, "pagamentos", coluna):
                conn.execute(f"ALTER TABLE pagamentos ADD COLUMN {coluna} {definicao}")

        conn.execute("UPDATE cobrancas SET valor_final = COALESCE(valor_final, valor + COALESCE(acrescimo,0) - COALESCE(desconto,0))")

        recursos_padrao = [
            ("agenda", "Agenda", "Agenda e agendamento público"),
            ("crm", "CRM", "Cadastro e histórico de clientes"),
            ("financeiro", "Financeiro", "Controle financeiro da empresa"),
            ("fidelidade", "Fidelidade", "Pontos e recompensas"),
            ("whatsapp", "WhatsApp", "Comunicações e lembretes"),
            ("relatorios", "Relatórios", "Indicadores e relatórios gerenciais"),
            ("api", "API", "Integrações externas"),
        ]
        conn.executemany(
            "INSERT OR IGNORE INTO recursos (chave, nome, descricao) VALUES (?, ?, ?)",
            recursos_padrao,
        )

        planos_padrao = [
            ("Essencial", "Agenda, CRM e lembretes pelo WhatsApp para começar.", 49.90, 2, 2, 150),
            ("Profissional", "CRM, fidelidade, financeiro e relatórios.", 99.90, None, None, None),
            ("Premium", "Todos os recursos e integrações avançadas.", 149.90, None, None, None),
        ]
        conn.executemany(
            """
            INSERT OR IGNORE INTO planos
            (nome, descricao, valor, limite_profissionais, limite_usuarios, limite_agendamentos)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            planos_padrao,
        )

        mapa_recursos = {
            "Essencial": ("agenda", "crm", "whatsapp"),
            "Profissional": ("agenda", "crm", "financeiro", "fidelidade", "relatorios", "whatsapp"),
            "Premium": ("agenda", "crm", "financeiro", "fidelidade", "relatorios", "whatsapp", "api"),
        }
        for nome_plano, chaves in mapa_recursos.items():
            plano = conn.execute("SELECT id FROM planos WHERE nome = ?", (nome_plano,)).fetchone()
            if not plano:
                continue
            for chave in chaves:
                recurso = conn.execute("SELECT id FROM recursos WHERE chave = ?", (chave,)).fetchone()
                if recurso:
                    conn.execute(
                        "INSERT OR IGNORE INTO plano_recursos (plano_id, recurso_id) VALUES (?, ?)",
                        (plano["id"], recurso["id"]),
                    )

        conn.execute(
            """
            UPDATE empresas
            SET plano_id = (SELECT id FROM planos WHERE planos.nome = empresas.plano)
            WHERE plano_id IS NULL
            """
        )

        conn.execute("""
            INSERT OR IGNORE INTO configuracoes_financeiras
            (id, dia_vencimento_padrao, tolerancia_dias_padrao, bloquear_apos_dias_padrao,
             multa_percentual, juros_mensal_percentual, desconto_antecipacao_percentual,
             forma_pagamento_padrao, mensagem_cobranca)
            VALUES (1, 10, 5, 15, 0, 0, 0, 'Pix',
                    'Olá! Identificamos uma mensalidade pendente do Bytech Agenda.')
        """)

        conn.execute(
            """
            UPDATE empresas
            SET
                segmento = COALESCE(NULLIF(segmento, ''), 'barbearia'),
                template_admin = COALESCE(NULLIF(template_admin, ''), 'barbearia'),
                template_cliente = COALESCE(NULLIF(template_cliente, ''), 'premium'),
                cor_principal = COALESCE(NULLIF(cor_principal, ''), '#111827'),
                cor_secundaria = COALESCE(NULLIF(cor_secundaria, ''), '#d4af37'),
                cor_botao = COALESCE(NULLIF(cor_botao, ''), '#d4af37'),
                cor_sidebar = COALESCE(NULLIF(cor_sidebar, ''), '#0f172a')
            """
        )

        if not _column_exists(
            conn,
            "agendamentos",
            "funcionario_id",
        ):
            conn.execute(
                """
                ALTER TABLE agendamentos
                ADD COLUMN funcionario_id INTEGER
                """
            )

        if not _column_exists(
            conn,
            "agendamentos",
            "duracao_total",
        ):
            conn.execute(
                """
                ALTER TABLE agendamentos
                ADD COLUMN duracao_total INTEGER
                NOT NULL DEFAULT 40
                """
            )

        if not _column_exists(
            conn,
            "agendamentos",
            "valor_total",
        ):
            conn.execute(
                """
                ALTER TABLE agendamentos
                ADD COLUMN valor_total REAL
                NOT NULL DEFAULT 0
                """
            )

        if not _column_exists(
            conn,
            "agendamentos",
            "cliente_id",
        ):
            conn.execute(
                """
                ALTER TABLE agendamentos
                ADD COLUMN cliente_id INTEGER
                """
            )

        if not _column_exists(
            conn,
            "agendamento_servicos",
            "ordem",
        ):
            conn.execute(
                """
                ALTER TABLE agendamento_servicos
                ADD COLUMN ordem INTEGER DEFAULT 1
                """
            )

        conn.execute(
            """
            INSERT OR IGNORE INTO agendamento_servicos (
                agendamento_id,
                servico_id,
                ordem
            )
            SELECT
                id,
                servico_id,
                1
            FROM agendamentos
            WHERE servico_id IS NOT NULL
            """
        )

        conn.execute(
            """
            UPDATE agendamentos
            SET duracao_total = COALESCE(
                (
                    SELECT duracao
                    FROM servicos
                    WHERE servicos.id =
                        agendamentos.servico_id
                ),
                40
            )
            WHERE
                duracao_total IS NULL
                OR duracao_total <= 0
            """
        )

        conn.execute(
            """
            UPDATE agendamentos
            SET valor_total = COALESCE(
                (
                    SELECT valor
                    FROM servicos
                    WHERE servicos.id =
                        agendamentos.servico_id
                ),
                0
            )
            WHERE
                valor_total IS NULL
                OR valor_total <= 0
            """
        )

        # Cria clientes a partir dos agendamentos antigos e vincula cliente_id.
        agendamentos_sem_cliente = conn.execute(
            """
            SELECT
                id,
                empresa_id,
                cliente_nome,
                cliente_telefone
            FROM agendamentos
            WHERE cliente_id IS NULL
            ORDER BY id
            """
        ).fetchall()

        for agendamento in agendamentos_sem_cliente:
            telefone_normalizado = "".join(
                caractere
                for caractere in str(
                    agendamento["cliente_telefone"] or ""
                )
                if caractere.isdigit()
            )

            if not telefone_normalizado:
                telefone_normalizado = (
                    f"sem-telefone-{agendamento['id']}"
                )

            cliente = conn.execute(
                """
                SELECT id
                FROM clientes
                WHERE empresa_id = ?
                  AND telefone = ?
                """,
                (
                    agendamento["empresa_id"],
                    telefone_normalizado,
                ),
            ).fetchone()

            if cliente:
                cliente_id = cliente["id"]
                conn.execute(
                    """
                    UPDATE clientes
                    SET
                        nome = ?,
                        atualizado_em = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        agendamento["cliente_nome"],
                        cliente_id,
                    ),
                )
            else:
                cursor_cliente = conn.execute(
                    """
                    INSERT INTO clientes (
                        empresa_id,
                        nome,
                        telefone
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        agendamento["empresa_id"],
                        agendamento["cliente_nome"],
                        telefone_normalizado,
                    ),
                )
                cliente_id = cursor_cliente.lastrowid

            conn.execute(
                """
                UPDATE agendamentos
                SET cliente_id = ?
                WHERE id = ?
                """,
                (
                    cliente_id,
                    agendamento["id"],
                ),
            )

        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
            idx_agendamento_funcionario_horario
            ON agendamentos (
                empresa_id,
                funcionario_id,
                data,
                hora
            )
            WHERE status != 'cancelado'
            """
        )

        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
            idx_agendamento_servico_unico
            ON agendamento_servicos (
                agendamento_id,
                servico_id
            )
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_agendamento_servicos_agendamento
            ON agendamento_servicos (
                agendamento_id
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_clientes_empresa_nome
            ON clientes (
                empresa_id,
                nome
            )
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_clientes_empresa_telefone
            ON clientes (
                empresa_id,
                telefone
            )
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_fidelidade_cliente
            ON fidelidade_movimentos (
                cliente_id
            )
            """
        )
        empresa = conn.execute(
            """
            SELECT id
            FROM empresas
            WHERE slug = 'demo'
            """
        ).fetchone()

        if not empresa:
            cursor = conn.execute(
                """
                INSERT INTO empresas (
                    nome,
                    slug,
                    telefone,
                    instagram,
                    endereco,
                    maps_url,
                    descricao,
                    segmento,
                    template_admin,
                    template_cliente,
                    cor_principal,
                    cor_secundaria,
                    cor_botao,
                    cor_sidebar,
                    horario_texto
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "Barbearia do Bairro",
                    "demo",
                    "(85) 99999-9999",
                    "@barbeariadobairro",
                    "Rua Exemplo, 123",
                    "https://www.google.com/maps",
                    (
                        "Cortes modernos, barba e atendimento "
                        "com hora marcada."
                    ),
                    "barbearia",
                    "barbearia",
                    "premium",
                    "#111827",
                    "#d4af37",
                    "#d4af37",
                    "#0f172a",
                    "Segunda a sábado, das 09h às 18h",
                ),
            )

            empresa_id = cursor.lastrowid

            servicos = [
                ("Corte masculino", 25.00, 40),
                ("Barba", 15.00, 30),
                ("Corte + barba", 35.00, 60),
                ("Corte infantil", 20.00, 40),
            ]

            conn.executemany(
                """
                INSERT INTO servicos (
                    empresa_id,
                    nome,
                    valor,
                    duracao
                )
                VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        empresa_id,
                        nome,
                        valor,
                        duracao,
                    )
                    for nome, valor, duracao
                    in servicos
                ],
            )

            conn.executemany(
                """
                INSERT INTO funcionarios (
                    empresa_id,
                    nome,
                    cargo
                )
                VALUES (?, ?, ?)
                """,
                [
                    (empresa_id, "João", "Barbeiro"),
                    (empresa_id, "Carlos", "Barbeiro"),
                ],
            )

            conn.execute(
                """
                INSERT INTO usuarios (
                    empresa_id,
                    usuario,
                    senha
                )
                VALUES (?, ?, ?)
                """,
                (
                    empresa_id,
                    "admin",
                    "admin123",
                ),
            )
        else:
            empresa_id = empresa["id"]

            total_func = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM funcionarios
                WHERE empresa_id = ?
                """,
                (empresa_id,),
            ).fetchone()["total"]

            if total_func == 0:
                conn.executemany(
                    """
                    INSERT INTO funcionarios (
                        empresa_id,
                        nome,
                        cargo
                    )
                    VALUES (?, ?, ?)
                    """,
                    [
                        (empresa_id, "João", "Barbeiro"),
                        (empresa_id, "Carlos", "Barbeiro"),
                    ],
                )

        master = conn.execute(
            """
            SELECT id
            FROM usuarios_master
            WHERE usuario = ?
            """,
            ("bytech",),
        ).fetchone()

        if not master:
            conn.execute(
                """
                INSERT INTO usuarios_master (
                    usuario,
                    senha
                )
                VALUES (?, ?)
                """,
                (
                    "bytech",
                    "trocar123",
                ),
            )

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS fidelidade_configuracoes (
                empresa_id INTEGER PRIMARY KEY,
                ativo INTEGER NOT NULL DEFAULT 1,
                tipo_pontuacao TEXT NOT NULL DEFAULT 'valor',
                pontos_por_atendimento INTEGER NOT NULL DEFAULT 1,
                valor_por_ponto REAL NOT NULL DEFAULT 10,
                validade_dias INTEGER,
                permitir_ajuste_manual INTEGER NOT NULL DEFAULT 1,
                atualizado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS fidelidade_recompensas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL,
                nome TEXT NOT NULL,
                descricao TEXT,
                pontos_necessarios INTEGER NOT NULL,
                tipo TEXT NOT NULL DEFAULT 'brinde',
                valor_desconto REAL NOT NULL DEFAULT 0,
                ativo INTEGER NOT NULL DEFAULT 1,
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                atualizado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS fidelidade_resgates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL,
                cliente_id INTEGER NOT NULL,
                recompensa_id INTEGER NOT NULL,
                pontos_utilizados INTEGER NOT NULL,
                observacoes TEXT,
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE,
                FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON DELETE CASCADE,
                FOREIGN KEY (recompensa_id) REFERENCES fidelidade_recompensas(id)
            );

            CREATE INDEX IF NOT EXISTS idx_fidelidade_movimentos_cliente
            ON fidelidade_movimentos (empresa_id, cliente_id, criado_em);
            CREATE INDEX IF NOT EXISTS idx_fidelidade_recompensas_empresa
            ON fidelidade_recompensas (empresa_id, ativo);
            """
        )

        empresas_ids = conn.execute("SELECT id FROM empresas").fetchall()
        for empresa_item in empresas_ids:
            conn.execute(
                """INSERT OR IGNORE INTO fidelidade_configuracoes (empresa_id)
                   VALUES (?)""",
                (empresa_item["id"],),
            )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()
