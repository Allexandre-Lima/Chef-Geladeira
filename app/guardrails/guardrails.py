"""Guardrails de entrada, saída e de atualização de prompt."""
from __future__ import annotations

import re
from typing import Tuple

MAX_INPUT_CHARS = 1000

INJECTION_PATTERNS = [
    r"ignor[ae]\s+(todas?\s+)?(as\s+)?(instru[cç][õo]es|regras)",
    r"esque[cç]a\s+(todas?\s+)?(as\s+)?(instru[cç][õo]es|regras)",
    r"ignore\s+(all\s+|any\s+)?(previous|prior|above)\s+instructions",
    r"(reveal|show)\s+(your\s+)?(system\s+)?prompt",
    r"(mostre|revele)\s+(o\s+)?(seu\s+)?prompt",
    r"voc[êe]\s+agora\s+[ée]",
    r"you\s+are\s+now",
]

ALLERGEN_TERMS = ["alergi", "intoler", "gluten", "glúten", "lactose", "amendoim", "celíac", "celiac"]

ALLERGY_NOTICE = (
    "\n\n⚠️ Aviso: se você tem alergia ou intolerância, confira sempre o rótulo "
    "dos produtos e consulte um profissional de saúde. Não posso garantir que "
    "uma receita seja segura para o seu caso."
)


def _matches_injection(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(p, lowered) for p in INJECTION_PATTERNS)


def check_user_input(text: str) -> Tuple[bool, str]:
    """Retorna (ok, motivo). Bloqueia entradas vazias, longas ou com injection."""
    if not text or not text.strip():
        return False, "Mensagem vazia."
    if len(text) > MAX_INPUT_CHARS:
        return False, f"Mensagem muito longa (máx. {MAX_INPUT_CHARS} caracteres)."
    if _matches_injection(text):
        return False, "Não posso seguir instruções que tentam alterar minhas regras."
    return True, ""


def sanitize_output(text: str) -> str:
    """Garante o aviso de alergia sempre que a resposta tocar no assunto."""
    lowered = text.lower()
    if any(term in lowered for term in ALLERGEN_TERMS) and ALLERGY_NOTICE.strip() not in text:
        return text + ALLERGY_NOTICE
    return text


def validate_style_prompt(text: str, max_chars: int) -> Tuple[bool, str]:
    """Valida a seção de estilo proposta pelo motor de feedback."""
    if not text or not text.strip():
        return False, "Prompt vazio."
    if len(text) > max_chars:
        return False, f"Prompt excede {max_chars} caracteres."
    if _matches_injection(text):
        return False, "Prompt contém instrução suspeita (possível prompt injection)."
    if "[regras fixas]" in text.lower():
        return False, "O estilo não pode redefinir as regras fixas."
    return True, ""
