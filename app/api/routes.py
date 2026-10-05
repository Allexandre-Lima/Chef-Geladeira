"""Rotas HTTP da API (prefixo /api)."""
from __future__ import annotations

from typing import List, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.agent.errors import LLMError
from app.guardrails.guardrails import check_user_input

router = APIRouter(prefix="/api")


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str
    history: List[Message] = []


class FeedbackRequest(BaseModel):
    question: str = Field(max_length=2000)
    answer: str = Field(default="", max_length=8000)
    rating: Literal[-1, 1]
    comment: str = Field(default="", max_length=1000)


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/chat")
def chat(body: ChatRequest, request: Request):
    ok, reason = check_user_input(body.message)
    if not ok:
        raise HTTPException(status_code=400, detail=reason)
    try:
        return request.app.state.agent.answer(body.message, [m.model_dump() for m in body.history])
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/feedback")
def add_feedback(body: FeedbackRequest, request: Request):
    ok, reason = check_user_input(body.comment) if body.comment else (True, "")
    if not ok:
        raise HTTPException(status_code=400, detail=reason)
    state = request.app.state
    feedback_id = state.repo.add_feedback(body.question, body.answer, body.rating, body.comment)
    auto_started = False
    if state.settings.auto_improve and state.engine.pending_count() >= state.settings.auto_improve_threshold:
        auto_started = state.engine.run_in_background()
    return {"id": feedback_id, "auto_started": auto_started}


@router.get("/feedback")
def list_feedback(request: Request):
    return request.app.state.repo.list_feedbacks()


@router.post("/prompts/improve")
def improve_prompt(request: Request):
    engine = request.app.state.engine
    started = engine.run_in_background()
    return {"started": started, "running": engine.running}


@router.get("/prompts/status")
def improve_status(request: Request):
    state = request.app.state
    return {
        "running": state.engine.running,
        "pending": state.engine.pending_count(),
        "threshold": state.settings.auto_improve_threshold,
        "auto": state.settings.auto_improve,
        "last_result": state.engine.last_result,
    }


@router.get("/prompts")
def list_prompts(request: Request):
    return request.app.state.repo.list_versions()


@router.post("/prompts/{version}/activate")
def activate_prompt(version: int, request: Request):
    if not request.app.state.repo.activate(version):
        raise HTTPException(status_code=404, detail="Versão não encontrada.")
    return {"active": version}
