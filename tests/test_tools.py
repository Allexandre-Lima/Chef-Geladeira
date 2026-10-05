import httpx

from app.tools import tools


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_search_recipes_parses_response(monkeypatch):
    payload = {"meals": [{"idMeal": "1", "strMeal": "Egg Fried Rice", "strMealThumb": "https://img/x.jpg"}]}
    monkeypatch.setattr(tools.httpx, "get", lambda *a, **k: FakeResponse(payload))
    assert tools.search_recipes_by_ingredient("egg") == {
        "recipes": [{"id": "1", "name": "Egg Fried Rice", "thumbnail": "https://img/x.jpg"}]
    }


def test_search_translates_portuguese_ingredients(monkeypatch):
    asked = []

    def fake_get(url, params=None, **kwargs):
        asked.append(params["i"])
        return FakeResponse({"meals": [{"idMeal": "1", "strMeal": "A", "strMealThumb": None}]})

    monkeypatch.setattr(tools.httpx, "get", fake_get)
    tools.search_recipes_by_ingredient("frango")
    assert asked == ["chicken"]


def test_search_ranks_recipes_that_match_more_ingredients(monkeypatch):
    meals = {
        "chicken": [{"idMeal": "A", "strMeal": "A"}, {"idMeal": "B", "strMeal": "B"}],
        "rice": [{"idMeal": "B", "strMeal": "B"}, {"idMeal": "C", "strMeal": "C"}],
    }
    monkeypatch.setattr(
        tools.httpx, "get", lambda url, params=None, **k: FakeResponse({"meals": meals.get(params["i"])})
    )
    ids = [r["id"] for r in tools.search_recipes_by_ingredient("frango, arroz")["recipes"]]
    assert ids[0] == "B" and set(ids) == {"A", "B", "C"}


def test_search_tries_plural_variant_and_returns_hint_when_empty(monkeypatch):
    asked = []

    def fake_get(url, params=None, **kwargs):
        asked.append(params["i"])
        return FakeResponse({"meals": None})

    monkeypatch.setattr(tools.httpx, "get", fake_get)
    result = tools.search_recipes_by_ingredient("cenoura")
    assert asked == ["carrots", "carrot"]
    assert result["recipes"] == [] and "hint" in result


def test_recipe_details_collects_ingredients(monkeypatch):
    meal = {"strMeal": "X", "strCategory": "Y", "strInstructions": "Cook.",
            "strIngredient1": "Egg", "strMeasure1": "2", "strIngredient2": "", "strMeasure2": ""}
    monkeypatch.setattr(tools.httpx, "get", lambda *a, **k: FakeResponse({"meals": [meal]}))
    assert tools.get_recipe_details("1")["ingredients"] == ["2 Egg"]


def test_recipe_not_found(monkeypatch):
    monkeypatch.setattr(tools.httpx, "get", lambda *a, **k: FakeResponse({"meals": None}))
    assert tools.get_recipe_details("0") == {"error": "Receita não encontrada."}


def test_nutrition_prefers_generic_foods_and_parses_nutrients(monkeypatch):
    branded = {"description": "BRAND MILK", "dataType": "Branded", "foodNutrients": []}
    generic = {
        "description": "Milk, condensed, sweetened",
        "dataType": "SR Legacy",
        "foodNutrients": [
            {"nutrientNumber": "208", "value": 321},
            {"nutrientNumber": "203", "value": 7.9},
            {"nutrientNumber": "204", "value": 8.7},
            {"nutrientNumber": "205", "value": 54.4},
        ],
    }
    monkeypatch.setattr(tools.httpx, "get", lambda *a, **k: FakeResponse({"foods": [branded, generic]}))
    first = tools.get_food_nutrition("sweetened condensed milk")["foods"][0]
    assert first["name"] == "Milk, condensed, sweetened"
    assert (first["kcal"], first["protein_g"], first["fat_g"], first["carbs_g"]) == (321, 7.9, 8.7, 54.4)


def test_nutrition_not_found(monkeypatch):
    monkeypatch.setattr(tools.httpx, "get", lambda *a, **k: FakeResponse({"foods": []}))
    result = tools.get_food_nutrition("xyz")
    assert result["error"] == "Alimento não encontrado." and "hint" in result


def test_network_error_returns_error_dict(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(tools.httpx, "get", boom)
    assert "error" in tools.get_food_nutrition("rice")
    assert "error" in tools.search_recipes_by_ingredient("egg")


def test_http_status_error_is_reported_without_leaking_the_url(monkeypatch):
    class Failing:
        def raise_for_status(self):
            request = httpx.Request("GET", "https://api.example/x?api_key=SECRET")
            raise httpx.HTTPStatusError("falhou", request=request, response=httpx.Response(429, request=request))

    monkeypatch.setattr(tools.httpx, "get", lambda *a, **k: Failing())
    result = tools.get_food_nutrition("milk")
    assert "429" in result["error"] and "SECRET" not in result["error"]


def test_nutrition_skips_foods_without_calories(monkeypatch):
    no_data = {"description": "Condensed milk", "dataType": "Foundation", "foodNutrients": []}
    branded = {"description": "BRAND", "dataType": "Branded", "foodNutrients": [{"nutrientNumber": "208", "value": 333}]}
    monkeypatch.setattr(tools.httpx, "get", lambda *a, **k: FakeResponse({"foods": [no_data, branded]}))
    foods = tools.get_food_nutrition("condensed milk")["foods"]
    assert [f["kcal"] for f in foods] == [333]


def test_nutrition_error_when_no_food_has_calories(monkeypatch):
    no_data = {"description": "X", "dataType": "Foundation", "foodNutrients": []}
    monkeypatch.setattr(tools.httpx, "get", lambda *a, **k: FakeResponse({"foods": [no_data]}))
    assert "error" in tools.get_food_nutrition("x")


def test_search_accepts_a_list_of_ingredients(monkeypatch):
    asked = []

    def fake_get(url, params=None, **kwargs):
        asked.append(params["i"])
        return FakeResponse({"meals": [{"idMeal": "1", "strMeal": "A"}]})

    monkeypatch.setattr(tools.httpx, "get", fake_get)
    tools.search_recipes_by_ingredient(["frango", "arroz"])
    assert asked == ["chicken", "rice"]


def test_nutrition_translates_portuguese_food_names(monkeypatch):
    asked = []

    def fake_get(url, params=None, **kwargs):
        asked.append(params["query"])
        return FakeResponse({"foods": []})

    monkeypatch.setattr(tools.httpx, "get", fake_get)
    tools.get_food_nutrition("Leite condensado")
    tools.get_food_nutrition("quinoa")
    assert asked == ["sweetened condensed milk", "quinoa"]


def test_tool_annotations_are_real_types_for_the_gemini_sdk():
    """O SDK usa isinstance() com as anotações; textos (from __future__ import annotations) quebram."""
    import inspect

    for fn in tools.TOOLS:
        for name, param in inspect.signature(fn).parameters.items():
            assert not isinstance(param.annotation, str), f"{fn.__name__}({name}) tem anotação em texto"
