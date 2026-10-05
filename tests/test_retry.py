from app.agent.retry import friendly_message, is_retryable, is_skippable, model_chain


def test_model_chain_dedupes_and_keeps_order():
    assert model_chain("a", "b, a ,c,,") == ["a", "b", "c"]


def test_daily_quota_skips_model_and_is_not_retried():
    error = "429 RESOURCE_EXHAUSTED ... GenerateRequestsPerDayPerProjectPerModel-FreeTier"
    assert is_skippable(error)
    assert not is_retryable(error)


def test_overload_is_retried_not_skipped():
    error = "503 UNAVAILABLE. This model is currently experiencing high demand."
    assert is_retryable(error)
    assert not is_skippable(error)


def test_missing_model_is_skipped():
    assert is_skippable("404 NOT_FOUND. This model is no longer available to new users.")


def test_friendly_messages():
    assert "diário" in friendly_message("PerDay")
    assert "sobrecarregados" in friendly_message("503 UNAVAILABLE")
    assert "Falha ao consultar" in friendly_message("400 INVALID_ARGUMENT")
