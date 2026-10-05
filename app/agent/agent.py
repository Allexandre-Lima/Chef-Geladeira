"""Agente: prompt versionado + contexto da vector store + ferramentas externas."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from google.genai import types

from app.agent import llm
from app.guardrails.guardrails import sanitize_output
from app.prompts.manager import PromptRepository
from app.tools.tools import TOOLS
from app.vectorstore.store import KnowledgeBase

logger = logging.getLogger(__name__)

# Regras fixas: NUNCA são editadas pelo motor de feedback, só a seção de estilo.
CORE_RULES = """[REGRAS FIXAS]
- Fale apenas sobre culinária, alimentos e nutrição básica; recuse educadamente outros assuntos.
- Use as ferramentas para buscar receitas em vez de inventar. Passe à ferramenta de receitas os ingredientes principais (até 3, separados por vírgula); se ela não retornar receitas, tente um ingrediente de cada vez antes de desistir.
- Para calorias e nutrientes de um alimento, use a ferramenta de nutrição (nome em inglês) e informe que os valores são por 100 g.
- Se uma ferramenta falhar ou não retornar valores, diga que não conseguiu consultar. Nunca cite números nutricionais (nem aproximados ou de memória) sem que a ferramenta os tenha retornado.
- Nunca afirme que uma receita é segura para alergias ou intolerâncias; oriente a conferir rótulos.
- Use o contexto de conhecimento abaixo quando for relevante."""

MAX_RECIPES = 6


def _summarize(data: Any) -> Any:
    """Resumo curto do resultado de uma ferramenta, para o log."""
    if not isinstance(data, dict):
        return str(data)[:80]
    if "error" in data:
        return {"error": str(data["error"])[:120]}
    return {k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in data.items()}


def _collect_tool_results(history: List[Any]) -> Dict[str, Any]:
    """Extrai ferramentas usadas, dados estruturados (receitas e nutrição) e um rastro para o log."""
    tools_used: List[str] = []
    recipes: Dict[str, Dict] = {}
    nutrition: Optional[Dict] = None
    trace: List[Dict] = []
    for content in history or []:
        for part in content.parts or []:
            call = part.function_call
            if call:
                if call.name not in tools_used:
                    tools_used.append(call.name)
                trace.append({"call": call.name, "args": dict(getattr(call, "args", None) or {})})
            fr = getattr(part, "function_response", None)
            if not fr or not isinstance(fr.response, dict):
                continue
            data = fr.response
            if set(data.keys()) == {"result"} and isinstance(data["result"], dict):
                data = data["result"]
            trace.append({"result": fr.name, "summary": _summarize(data)})
            if fr.name == "search_recipes_by_ingredient":
                for recipe in data.get("recipes", []):
                    recipes.setdefault(recipe["id"], recipe)
            elif fr.name == "get_food_nutrition" and nutrition is None and data.get("foods"):
                nutrition = data["foods"][0]
    return {"tools_used": tools_used, "recipes": list(recipes.values())[:MAX_RECIPES], "nutrition": nutrition, "trace": trace}


class ChefAgent:
    def __init__(self, repo: PromptRepository, kb: KnowledgeBase) -> None:
        self.repo = repo
        self.kb = kb

    @staticmethod
    def build_system_prompt(style_prompt: str, context: List[str]) -> str:
        ctx = "\n".join(f"- {c}" for c in context) or "(nenhum contexto encontrado)"
        return f"{style_prompt}\n\n{CORE_RULES}\n\n[CONTEXTO]\n{ctx}"

    def answer(self, message: str, history: Optional[List[Dict]] = None, style_prompt: Optional[str] = None) -> Dict:
        style = style_prompt or self.repo.get_active()["content"]
        try:
            context = self.kb.search(message)
        except Exception as exc:  # RAG é opcional: o chat segue sem contexto
            logger.warning("vector search failed", extra={"extra_data": {"error": str(exc)}})
            context = []

        contents = [
            types.Content(role="user" if m["role"] == "user" else "model", parts=[types.Part(text=m["content"])])
            for m in (history or [])
        ]
        contents.append(types.Content(role="user", parts=[types.Part(text=message)]))

        resp = llm.generate(self.build_system_prompt(style, context), contents, tools=TOOLS)
        results = _collect_tool_results(getattr(resp, "automatic_function_calling_history", None))
        trace = results.pop("trace")
        text = sanitize_output(resp.text or "Não consegui gerar uma resposta agora.")
        logger.info(
            "chat answered",
            extra={"extra_data": {"tools": results["tools_used"], "context_chunks": len(context), "trace": trace}},
        )
        return {"answer": text, "context": context, **results}
