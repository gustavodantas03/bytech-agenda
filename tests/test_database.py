import tempfile
import unittest
from pathlib import Path

import database


class DatabaseTest(unittest.TestCase):
    def test_placeholders_preservam_interrogacao_em_texto(self):
        sql = "SELECT '?' AS literal, id FROM empresas WHERE id=?"
        self.assertEqual(
            database._replace_qmarks(sql),
            "SELECT '?' AS literal, id FROM empresas WHERE id=%s",
        )

    def test_migracoes_sao_idempotentes_no_sqlite(self):
        with tempfile.TemporaryDirectory() as pasta:
            original_path = database.DB_PATH
            original_dir = database.DATABASE_DIR
            try:
                database.DATABASE_DIR = Path(pasta)
                database.DB_PATH = Path(pasta) / "teste.db"
                database.init_db()
                database.init_db()
                conn = database.get_connection()
                total = conn.execute(
                    "SELECT COUNT(*) AS total FROM schema_migrations"
                ).fetchone()["total"]
                conn.close()
                self.assertEqual(total, len(database.MIGRATIONS))
            finally:
                database.DB_PATH = original_path
                database.DATABASE_DIR = original_dir


if __name__ == "__main__":
    unittest.main()
