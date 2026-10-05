"""Persistência (SQLite) de versões do prompt e do histórico de feedbacks."""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, List, Optional

DEFAULT_STYLE_PROMPT = """Você é o Chef de Geladeira, um assistente culinário simpático e prático.
Ajude a pessoa a decidir o que cozinhar com os ingredientes que ela tem em casa.
- Tom amigável e objetivo, sem enrolação.
- Sugira até 3 receitas, com modo de preparo em passos numerados e curtos.
- Quando faltar um ingrediente, sugira uma substituição simples.
- Responda sempre em português do Brasil."""

# Marcador de feedback analisado sem gerar versão (ex.: proposta bloqueada por guardrail).
DISCARDED = 0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class PromptRepository:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._init_schema()
        if self.get_active() is None:
            self.create_version(DEFAULT_STYLE_PROMPT, "Versão inicial", pass_rate=None, activate=True)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS prompt_versions (
                    version INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    reason TEXT,
                    pass_rate REAL,
                    active INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS feedbacks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    rating INTEGER NOT NULL,
                    comment TEXT NOT NULL DEFAULT '',
                    category TEXT,
                    processed_in_version INTEGER,
                    created_at TEXT NOT NULL
                );
                """
            )
            columns = {row["name"] for row in c.execute("PRAGMA table_info(prompt_versions)")}
            if "details" not in columns:  # migração de bancos criados em versões anteriores
                c.execute("ALTER TABLE prompt_versions ADD COLUMN details TEXT")

    # ---- versões do prompt -------------------------------------------------
    @staticmethod
    def _version_row(row: sqlite3.Row) -> Dict:
        data = dict(row)
        raw = data.get("details")
        data["details"] = json.loads(raw) if raw else []
        return data

    def get_active(self) -> Optional[Dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM prompt_versions WHERE active = 1").fetchone()
        return self._version_row(row) if row else None

    def list_versions(self) -> List[Dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM prompt_versions ORDER BY version DESC").fetchall()
        return [self._version_row(r) for r in rows]

    def create_version(
        self, content: str, reason: str, pass_rate: Optional[float], activate: bool, details: Optional[List] = None
    ) -> int:
        with self._conn() as c:
            if activate:
                c.execute("UPDATE prompt_versions SET active = 0")
            cur = c.execute(
                "INSERT INTO prompt_versions (content, reason, pass_rate, active, created_at, details) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (content, reason, pass_rate, 1 if activate else 0, _now(),
                 json.dumps(details, ensure_ascii=False) if details else None),
            )
            return int(cur.lastrowid)

    def activate(self, version: int) -> bool:
        with self._conn() as c:
            exists = c.execute("SELECT 1 FROM prompt_versions WHERE version = ?", (version,)).fetchone()
            if not exists:
                return False
            c.execute("UPDATE prompt_versions SET active = 0")
            c.execute("UPDATE prompt_versions SET active = 1 WHERE version = ?", (version,))
        return True

    # ---- feedbacks ---------------------------------------------------------
    def add_feedback(self, question: str, answer: str, rating: int, comment: str) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO feedbacks (question, answer, rating, comment, created_at) VALUES (?, ?, ?, ?, ?)",
                (question, answer, rating, comment, _now()),
            )
            return int(cur.lastrowid)

    def list_feedbacks(self, limit: int = 100) -> List[Dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM feedbacks ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def pending_feedbacks(self) -> List[Dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM feedbacks WHERE processed_in_version IS NULL ORDER BY id"
            ).fetchall()
        return [dict(r) for r in rows]

    def pending_useful_count(self) -> int:
        """Feedbacks ainda não analisados que têm comentário ou nota negativa."""
        with self._conn() as c:
            row = c.execute(
                "SELECT COUNT(*) AS n FROM feedbacks "
                "WHERE processed_in_version IS NULL AND (TRIM(comment) != '' OR rating < 0)"
            ).fetchone()
        return int(row["n"])

    def negative_feedbacks(self, limit: int = 8) -> List[Dict]:
        """Respostas mal avaliadas de todo o histórico: base dos testes de regressão."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM feedbacks WHERE rating < 0 AND answer != '' ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def set_category(self, feedback_id: int, category: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE feedbacks SET category = ? WHERE id = ?", (category, feedback_id))

    def mark_processed(self, feedback_ids: List[int], version: int) -> None:
        with self._conn() as c:
            c.executemany(
                "UPDATE feedbacks SET processed_in_version = ? WHERE id = ?",
                [(version, fid) for fid in feedback_ids],
            )
