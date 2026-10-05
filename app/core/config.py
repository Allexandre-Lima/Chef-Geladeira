"""Configurações da aplicação, lidas de variáveis de ambiente / .env."""
from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str = ""
    # Modelo principal e alternativos (separados por vírgula), usados quando o
    # principal está indisponível, sem acesso ou sem cota.
    gemini_model: str = "gemini-3.7-flash"
    gemini_fallback_models: str = "gemini-3.8-flash,gemini-3.6-flash,gemini-3.5-flash-lite"
    embedding_model: str = "gemini-embedding-001"
    data_dir: str = "data"
    knowledge_dir: str = "knowledge"
    log_level: str = "INFO"
    # Fração mínima de casos de regressão aprovados para ativar um prompt novo.
    regression_pass_threshold: float = 0.8
    max_prompt_chars: int = 2000
    # Atualização automática: roda a análise a cada N feedbacks úteis.
    auto_improve: bool = True
    auto_improve_threshold: int = 3

    @property
    def db_path(self) -> str:
        return os.path.join(self.data_dir, "app.db")

    @property
    def chroma_path(self) -> str:
        return os.path.join(self.data_dir, "chroma")


@lru_cache
def get_settings() -> Settings:
    return Settings()
