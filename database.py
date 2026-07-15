import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATABASE_DIR = BASE_DIR / "database"
DB_PATH = DATABASE_DIR / "bytech_agenda.db"


def get_connection():
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _column_exists(conn, table, column):
    columns = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(item["name"] == column for item in columns)


def init_db():
    conn = get_connection()

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
    cor_principal TEXT DEFAULT '#111827',
    horario_texto TEXT,
    ativo INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS usuarios_master (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario TEXT NOT NULL UNIQUE,
    senha TEXT NOT NULL
);

        CREATE TABLE IF NOT EXISTS servicos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER NOT NULL,
            nome TEXT NOT NULL,
            valor REAL NOT NULL DEFAULT 0,
            duracao INTEGER NOT NULL DEFAULT 40,
            ativo INTEGER DEFAULT 1,
            FOREIGN KEY (empresa_id) REFERENCES empresas(id)
        );

        CREATE TABLE IF NOT EXISTS funcionarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER NOT NULL,
            nome TEXT NOT NULL,
            cargo TEXT DEFAULT 'Barbeiro',
            ativo INTEGER DEFAULT 1,
            FOREIGN KEY (empresa_id) REFERENCES empresas(id)
        );

        CREATE TABLE IF NOT EXISTS agendamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER NOT NULL,
            cliente_nome TEXT NOT NULL,
            cliente_telefone TEXT NOT NULL,
            servico_id INTEGER NOT NULL,
            funcionario_id INTEGER,
            data TEXT NOT NULL,
            hora TEXT NOT NULL,
            status TEXT DEFAULT 'agendado',
            criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (empresa_id) REFERENCES empresas(id),
            FOREIGN KEY (servico_id) REFERENCES servicos(id),
            FOREIGN KEY (funcionario_id) REFERENCES funcionarios(id)
        );

        CREATE TABLE IF NOT EXISTS agendamento_servicos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agendamento_id INTEGER NOT NULL,
            servico_id INTEGER NOT NULL,
            FOREIGN KEY (agendamento_id) REFERENCES agendamentos(id) ON DELETE CASCADE,
            FOREIGN KEY (servico_id) REFERENCES servicos(id),
            UNIQUE (agendamento_id, servico_id)
        );

        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER NOT NULL,
            usuario TEXT NOT NULL UNIQUE,
            senha TEXT NOT NULL,
            FOREIGN KEY (empresa_id) REFERENCES empresas(id)
        );
        """
        
    )

    if not _column_exists(conn, "empresas", "logo"):
        conn.execute("ALTER TABLE empresas ADD COLUMN logo TEXT")

    if not _column_exists(conn, "agendamentos", "funcionario_id"):
        conn.execute("ALTER TABLE agendamentos ADD COLUMN funcionario_id INTEGER")

    if not _column_exists(conn, "agendamentos", "duracao_total"):
        conn.execute(
            "ALTER TABLE agendamentos ADD COLUMN duracao_total INTEGER NOT NULL DEFAULT 40"
        )

    if not _column_exists(conn, "agendamentos", "valor_total"):
        conn.execute(
            "ALTER TABLE agendamentos ADD COLUMN valor_total REAL NOT NULL DEFAULT 0"
        )

    # Migra agendamentos antigos para a nova relação de múltiplos serviços.
    conn.execute(
        """
        INSERT OR IGNORE INTO agendamento_servicos (agendamento_id, servico_id)
        SELECT id, servico_id
        FROM agendamentos
        WHERE servico_id IS NOT NULL
        """
    )

    # Preenche duração e valor dos registros antigos quando ainda estiverem zerados.
    conn.execute(
        """
        UPDATE agendamentos
        SET duracao_total = COALESCE(
                (SELECT duracao FROM servicos WHERE servicos.id = agendamentos.servico_id),
                40
            ),
            valor_total = COALESCE(
                (SELECT valor FROM servicos WHERE servicos.id = agendamentos.servico_id),
                0
            )
        WHERE valor_total = 0
        """
    )

    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_agendamento_funcionario_horario
        ON agendamentos (empresa_id, funcionario_id, data, hora)
        WHERE status != 'cancelado'
        """
    )

    empresa = conn.execute("SELECT id FROM empresas WHERE slug = 'demo'").fetchone()

    if not empresa:
        cursor = conn.execute(
            """
            INSERT INTO empresas
            (nome, slug, telefone, instagram, endereco, maps_url, descricao, cor_principal, horario_texto)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "Barbearia do Bairro",
                "demo",
                "(85) 99999-9999",
                "@barbeariadobairro",
                "Rua Exemplo, 123",
                "https://www.google.com/maps",
                "Cortes modernos, barba e atendimento com hora marcada.",
                "#111827",
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
            "INSERT INTO servicos (empresa_id, nome, valor, duracao) VALUES (?, ?, ?, ?)",
            [(empresa_id, nome, valor, duracao) for nome, valor, duracao in servicos],
        )

        conn.executemany(
            "INSERT INTO funcionarios (empresa_id, nome, cargo) VALUES (?, ?, ?)",
            [
                (empresa_id, "João", "Barbeiro"),
                (empresa_id, "Carlos", "Barbeiro"),
            ],
        )

        conn.execute(
            "INSERT INTO usuarios (empresa_id, usuario, senha) VALUES (?, ?, ?)",
            (empresa_id, "admin", "admin123"),
        )
    else:
        empresa_id = empresa["id"]
        total_func = conn.execute(
            "SELECT COUNT(*) AS total FROM funcionarios WHERE empresa_id = ?",
            (empresa_id,),
        ).fetchone()["total"]
        if total_func == 0:
            conn.executemany(
                "INSERT INTO funcionarios (empresa_id, nome, cargo) VALUES (?, ?, ?)",
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
            INSERT INTO usuarios_master (usuario, senha)
            VALUES (?, ?)
            """,
            ("bytech", "trocar123"),
        )
    conn.commit()
    conn.close()