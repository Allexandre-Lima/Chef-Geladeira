import sqlite3

from app.prompts.manager import PromptRepository


def test_seeds_default_version(tmp_path):
    repo = PromptRepository(str(tmp_path / "t.db"))
    assert repo.get_active()["version"] == 1


def test_new_version_activation_and_rollback(tmp_path):
    repo = PromptRepository(str(tmp_path / "t.db"))
    v2 = repo.create_version("novo estilo", "teste", 0.9, activate=True)
    assert repo.get_active()["version"] == v2
    assert repo.activate(1)
    assert repo.get_active()["version"] == 1
    assert not repo.activate(999)


def test_version_stores_regression_details(tmp_path):
    repo = PromptRepository(str(tmp_path / "t.db"))
    details = [{"question": "q", "passed": False, "reason": "ainda longo"}]
    version = repo.create_version("x", "REJEITADA: teste", 0.0, activate=False, details=details)
    stored = next(v for v in repo.list_versions() if v["version"] == version)
    assert stored["details"] == details


def test_feedback_flow_and_pending_count(tmp_path):
    repo = PromptRepository(str(tmp_path / "t.db"))
    fid = repo.add_feedback("q", "a", -1, "muito longa")
    repo.add_feedback("q2", "a2", 1, "")  # nota positiva sem comentário não conta
    assert repo.pending_useful_count() == 1
    repo.mark_processed([fid], 1)
    assert repo.pending_useful_count() == 0
    assert len(repo.negative_feedbacks()) == 1


def test_general_suggestions_are_not_regression_cases(tmp_path):
    repo = PromptRepository(str(tmp_path / "t.db"))
    repo.add_feedback("(sugestão geral)", "", -1, "respostas mais curtas")
    assert repo.negative_feedbacks() == []


def test_migrates_old_database_without_details_column(tmp_path):
    path = str(tmp_path / "old.db")
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE prompt_versions (version INTEGER PRIMARY KEY AUTOINCREMENT, content TEXT NOT NULL, "
        "reason TEXT, pass_rate REAL, active INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);"
        "INSERT INTO prompt_versions (content, reason, active, created_at) VALUES ('antigo', 'v1', 1, 'agora');"
    )
    conn.commit()
    conn.close()
    repo = PromptRepository(path)
    assert repo.get_active()["details"] == []
