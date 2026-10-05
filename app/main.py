"""Entrypoint FastAPI: API em /api e interface web estática na raiz."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.agent.agent import ChefAgent
from app.api.routes import router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.feedback.engine import FeedbackEngine
from app.prompts.manager import PromptRepository
from app.vectorstore.store import KnowledgeBase

logger = logging.getLogger(__name__)
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    repo = PromptRepository(settings.db_path)
    kb = KnowledgeBase(settings.chroma_path, settings.knowledge_dir)
    try:
        kb.ingest_if_empty()
    except Exception:
        logger.exception("knowledge ingestion failed; will retry on first search")
    agent = ChefAgent(repo, kb)
    app.state.settings = settings
    app.state.repo = repo
    app.state.agent = agent
    app.state.engine = FeedbackEngine(repo, agent, settings)
    yield


app = FastAPI(title="Chef de Geladeira", lifespan=lifespan)
app.include_router(router)
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
