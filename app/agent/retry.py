"""Regras puras de tentativa, troca de modelo e mensagens de erro do LLM."""
from __future__ import annotations

from typing import List

RETRY_DELAYS = (2,)  # segundos de espera entre tentativas no mesmo modelo
RETRYABLE_MARKERS = ("503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED")


def model_chain(primary: str, fallbacks: str) -> List[str]:
    """Modelo principal seguido dos alternativos, sem repetições."""
    chain: List[str] = []
    for name in [primary] + fallbacks.split(","):
        name = name.strip()
        if name and name not in chain:
            chain.append(name)
    return chain


def is_skippable(error: str) -> bool:
    """O modelo não existe para esta conta ou a cota diária acabou: vale tentar o próximo."""
    return "NOT_FOUND" in error or "PerDay" in error


def is_retryable(error: str) -> bool:
    """Sobrecarga ou limite por minuto: vale esperar e tentar de novo."""
    return "PerDay" not in error and any(marker in error for marker in RETRYABLE_MARKERS)


def friendly_message(error: str) -> str:
    if "PerDay" in error:
        return "O limite diário gratuito dos modelos acabou. Tente novamente amanhã ou ajuste GEMINI_MODEL no .env."
    if is_retryable(error):
        return "Os modelos estão sobrecarregados ou no limite de uso. Tente de novo em instantes."
    if "NOT_FOUND" in error:
        return "Nenhum dos modelos configurados está disponível. Ajuste GEMINI_MODEL no .env."
    return f"Falha ao consultar o modelo: {error}"
