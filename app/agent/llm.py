"""Camada fina sobre o SDK do Gemini (geração, JSON e embeddings)."""
from __future__ import annotations

import json
import logging
import time
from typing import List, Optional

from google import genai
from google.genai import types

from app.agent.errors import LLMError
from app.agent.retry import RETRY_DELAYS, friendly_message, is_retryable, is_skippable, model_chain
from app.core.config import get_settings

logger = logging.getLogger(__name__)
_client: Optional[genai.Client] = None

__all__ = ["LLMError", "generate", "generate_json", "embed"]


def _get_client() -> genai.Client:
    global _client
    settings = get_settings()
    if not settings.gemini_api_key:
        raise LLMError("GEMINI_API_KEY não configurada. Preencha o arquivo .env.")
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def generate(system: str, contents: List[types.Content], tools: Optional[list] = None, json_mode: bool = False):
    """Chama o modelo. Com `tools`, o SDK executa o function calling automaticamente.

    Em sobrecarga (503) ou limite por minuto (429), espera e tenta de novo. Se o
    modelo não existir ou a cota diária acabar, passa para o próximo da lista.
    """
    cfg = types.GenerateContentConfig(system_instruction=system, tools=tools, temperature=0.4)
    if json_mode:
        cfg.response_mime_type = "application/json"
    settings = get_settings()
    client = _get_client()
    last_error = ""
    for model in model_chain(settings.gemini_model, settings.gemini_fallback_models):
        for attempt in range(len(RETRY_DELAYS) + 1):
            try:
                response = client.models.generate_content(model=model, contents=contents, config=cfg)
                if model != settings.gemini_model:
                    logger.info("fallback model used", extra={"extra_data": {"model": model}})
                return response
            except Exception as exc:  # o SDK levanta vários tipos (cota, rede, etc.)
                last_error = str(exc)
                logger.warning(
                    "llm call failed",
                    extra={"extra_data": {"model": model, "attempt": attempt + 1, "error": last_error[:300]}},
                )
                if is_skippable(last_error):
                    break
                if not is_retryable(last_error):
                    raise LLMError(friendly_message(last_error)) from exc
                if attempt < len(RETRY_DELAYS):
                    time.sleep(RETRY_DELAYS[attempt])
    raise LLMError(friendly_message(last_error))


def generate_json(system: str, prompt: str) -> dict:
    content = [types.Content(role="user", parts=[types.Part(text=prompt)])]
    text = generate(system, content, json_mode=True).text or "{}"
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError("O modelo devolveu JSON inválido.") from exc


def embed(texts: List[str]) -> List[List[float]]:
    try:
        res = _get_client().models.embed_content(model=get_settings().embedding_model, contents=texts)
        return [e.values for e in res.embeddings]
    except LLMError:
        raise
    except Exception as exc:
        raise LLMError(f"Falha ao gerar embeddings: {exc}") from exc
