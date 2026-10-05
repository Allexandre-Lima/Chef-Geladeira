"""Ferramentas externas expostas ao agente (function calling).

IMPORTANTE: não use `from __future__ import annotations` neste arquivo. O SDK do Gemini valida os
argumentos com isinstance() usando as anotações reais; anotações em texto quebram a chamada.

Cada função tem type hints e docstring, pois o SDK do Gemini usa isso para
descrever a ferramenta ao modelo. Erros de rede nunca propagam: retornam um
dict com a chave "error", para o agente poder se explicar ao usuário.
"""
import logging
import os
import re
from typing import Any, Dict, List

import httpx

logger = logging.getLogger(__name__)

THEMEALDB = "https://www.themealdb.com/api/json/v1/1"
USDA = "https://api.nal.usda.gov/fdc/v1/foods/search"
PREFERRED_FOOD_TYPES = ("Foundation", "SR Legacy")  # alimentos genéricos vêm primeiro
# Identificadores dos nutrientes no USDA (número do nutriente, id).
NUTRIENT_IDS = {
    "kcal": ("208", "1008"),
    "protein_g": ("203", "1003"),
    "fat_g": ("204", "1004"),
    "carbs_g": ("205", "1005"),
}
TIMEOUT = 10.0


def _get(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """GET com tratamento de erros. Nunca registra a URL com parâmetros (pode conter chaves)."""
    try:
        resp = httpx.get(url, params=params, timeout=TIMEOUT, headers={"User-Agent": "chef-geladeira/1.0"})
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        logger.warning("external api failed", extra={"extra_data": {"url": url, "status": status}})
        return {"error": f"O serviço externo respondeu com erro {status}."}
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("external api failed", extra={"extra_data": {"url": url, "error": type(exc).__name__}})
        return {"error": "Serviço externo indisponível no momento."}


# O TheMealDB só entende nomes de ingredientes em inglês (e alguns só no plural).
PT_TO_EN = {
    "frango": ["chicken"], "peito de frango": ["chicken_breast"], "arroz": ["rice"],
    "cenoura": ["carrots", "carrot"], "ovo": ["eggs", "egg"], "ovos": ["eggs", "egg"],
    "batata": ["potatoes", "potato"], "tomate": ["tomatoes", "tomato"], "cebola": ["onions", "onion"],
    "alho": ["garlic"], "carne": ["beef"], "carne moída": ["minced_beef", "beef"], "porco": ["pork"],
    "salmão": ["salmon"], "atum": ["tuna"], "macarrão": ["pasta", "spaghetti"], "leite": ["milk"],
    "queijo": ["cheese"], "farinha": ["flour"], "banana": ["bananas", "banana"], "brócolis": ["broccoli"],
    "abóbora": ["pumpkin"], "limão": ["lemon"], "cogumelo": ["mushrooms"], "espinafre": ["spinach"],
    "manteiga": ["butter"], "pão": ["bread"], "camarão": ["prawns"], "feijão": ["kidney_beans"],
    "grão de bico": ["chickpeas"], "lentilha": ["lentils"], "milho": ["sweetcorn"], "peixe": ["salmon"],
}
MAX_TERMS = 3


def _ingredient_candidates(term: str) -> List[str]:
    """Nomes a tentar no TheMealDB para um ingrediente (tradução e singular/plural)."""
    t = term.strip().lower()
    if not t:
        return []
    if t in PT_TO_EN:
        return PT_TO_EN[t]
    t = t.replace(" ", "_")
    return [t, t[:-1]] if t.endswith("s") else [t, t + "s"]


def _meals_for_ingredient(term: str) -> Dict[str, Any]:
    for candidate in _ingredient_candidates(term):
        data = _get(f"{THEMEALDB}/filter.php", {"i": candidate})
        if "error" in data:
            return data
        meals = data.get("meals") or []
        if meals:
            return {"meals": meals}
    return {"meals": []}


def search_recipes_by_ingredient(ingredients: str) -> Dict[str, Any]:
    """Busca receitas a partir de um ou mais ingredientes principais (TheMealDB).

    Args:
        ingredients: até 3 ingredientes separados por vírgula, em português ou inglês
            (ex.: "frango, arroz, cenoura" ou "chicken, rice").

    Returns:
        Lista de receitas com id, nome e foto (as que usam mais ingredientes vêm primeiro),
        ou um dicionário com a chave "error".
    """
    if not isinstance(ingredients, str):  # o modelo às vezes envia uma lista em vez de texto
        ingredients = ", ".join(str(item) for item in ingredients)
    terms = [t for t in re.split(r"\s*(?:,|;|\be\b|\band\b)\s*", ingredients.strip(), flags=re.IGNORECASE) if t][:MAX_TERMS]
    scored: Dict[str, Dict[str, Any]] = {}
    for order, term in enumerate(terms):
        data = _meals_for_ingredient(term)
        if "error" in data:
            return data
        for meal in data["meals"]:
            entry = scored.setdefault(meal["idMeal"], {"meal": meal, "score": 0, "order": len(scored)})
            entry["score"] += 1
    ranked = sorted(scored.values(), key=lambda e: (-e["score"], e["order"]))[:5]
    if not ranked:
        return {
            "recipes": [],
            "hint": "Nenhuma receita encontrada. Tente um ingrediente principal por vez (ex.: chicken, rice).",
        }
    return {
        "recipes": [
            {"id": e["meal"]["idMeal"], "name": e["meal"]["strMeal"], "thumbnail": e["meal"].get("strMealThumb")}
            for e in ranked
        ]
    }


def get_recipe_details(recipe_id: str) -> Dict[str, Any]:
    """Obtém ingredientes e modo de preparo de uma receita pelo id (TheMealDB).

    Args:
        recipe_id: id retornado por search_recipes_by_ingredient.
    """
    data = _get(f"{THEMEALDB}/lookup.php", {"i": recipe_id})
    if "error" in data:
        return data
    meals = data.get("meals") or []
    if not meals:
        return {"error": "Receita não encontrada."}
    meal = meals[0]
    ingredients = []
    for n in range(1, 21):
        name = (meal.get(f"strIngredient{n}") or "").strip()
        if name:
            ingredients.append(f"{(meal.get(f'strMeasure{n}') or '').strip()} {name}".strip())
    return {
        "name": meal.get("strMeal"),
        "category": meal.get("strCategory"),
        "ingredients": ingredients,
        "instructions": (meal.get("strInstructions") or "")[:1500],
    }


# A USDA só entende nomes em inglês: traduz os alimentos mais comuns pedidos em português.
FOOD_PT_TO_EN = {
    "leite condensado": "sweetened condensed milk", "creme de leite": "heavy cream", "leite": "whole milk",
    "ovo": "egg whole raw", "ovos": "egg whole raw", "arroz": "white rice cooked", "arroz cozido": "white rice cooked",
    "arroz integral": "brown rice cooked", "feijão": "beans cooked", "feijão cozido": "beans cooked",
    "frango": "chicken breast cooked", "peito de frango": "chicken breast cooked", "carne": "beef cooked",
    "carne moída": "ground beef cooked", "batata": "potato boiled", "cenoura": "carrots raw", "tomate": "tomatoes raw",
    "cebola": "onions raw", "alho": "garlic raw", "banana": "bananas raw", "maçã": "apples raw", "pão": "white bread",
    "pão francês": "white bread", "queijo": "cheddar cheese", "manteiga": "butter", "açúcar": "granulated sugar",
    "farinha de trigo": "wheat flour", "macarrão": "pasta cooked", "azeite": "olive oil", "óleo": "vegetable oil",
    "brócolis": "broccoli raw", "atum": "tuna canned", "salmão": "salmon cooked", "aveia": "oats", "iogurte": "plain yogurt",
    "chocolate": "milk chocolate", "mandioca": "cassava raw", "milho": "sweet corn", "abacate": "avocados raw",
}


def get_food_nutrition(food_name: str) -> Dict[str, Any]:
    """Consulta calorias e macronutrientes por 100 g de um alimento (USDA FoodData Central).

    Args:
        food_name: nome do alimento, de preferência em inglês (ex.: "sweetened condensed milk", "cooked white rice").

    Returns:
        Até 3 alimentos com kcal, proteína, gordura e carboidratos por 100 g, ou "error".
    """
    query = FOOD_PT_TO_EN.get(food_name.strip().lower(), food_name.strip())
    data = _get(
        USDA,
        {"query": query, "pageSize": 10, "api_key": os.getenv("USDA_API_KEY") or "DEMO_KEY"},
    )
    if "error" in data:
        return data
    foods = data.get("foods") or []
    if not foods:
        return {
            "error": "Alimento não encontrado.",
            "hint": "Tente o nome do alimento em inglês (ex.: sweetened condensed milk).",
        }
    foods.sort(key=lambda f: f.get("dataType") not in PREFERRED_FOOD_TYPES)  # ordenação estável
    results = []
    for food in foods:
        item: Dict[str, Any] = {"name": food.get("description"), "type": food.get("dataType"), "per": "100 g"}
        for key, ids in NUTRIENT_IDS.items():
            item[key] = next(
                (n.get("value") for n in food.get("foodNutrients", [])
                 if str(n.get("nutrientNumber")) in ids or str(n.get("nutrientId")) in ids),
                None,
            )
        if item["kcal"] is None:  # alguns registros não trazem calorias: ignora
            continue
        results.append(item)
        if len(results) == 3:
            break
    if not results:
        return {"error": "Não há dados nutricionais disponíveis para este alimento."}
    return {"foods": results}


TOOLS = [search_recipes_by_ingredient, get_recipe_details, get_food_nutrition]
