from types import SimpleNamespace as NS

from app.agent.agent import _collect_tool_results


def _part(call=None, response=None):
    return NS(
        function_call=NS(name=call) if call else None,
        function_response=NS(name=response[0], response=response[1]) if response else None,
    )


def test_collects_tools_recipes_and_nutrition():
    history = [
        NS(parts=[_part(call="search_recipes_by_ingredient")]),
        NS(parts=[_part(response=("search_recipes_by_ingredient", {"recipes": [{"id": "1", "name": "A", "thumbnail": None}]}))]),
        NS(parts=[_part(call="get_food_nutrition")]),
        NS(parts=[_part(response=("get_food_nutrition", {"foods": [{"name": "Milk", "kcal": 321}]}))]),
    ]
    result = _collect_tool_results(history)
    assert result["tools_used"] == ["search_recipes_by_ingredient", "get_food_nutrition"]
    assert [r["id"] for r in result["recipes"]] == ["1"]
    assert result["nutrition"]["kcal"] == 321


def test_handles_wrapped_results_and_empty_history():
    wrapped = [NS(parts=[_part(response=("get_food_nutrition", {"result": {"foods": [{"kcal": 1}]}}))])]
    assert _collect_tool_results(wrapped)["nutrition"] == {"kcal": 1}
    assert _collect_tool_results(None) == {"tools_used": [], "recipes": [], "nutrition": None, "trace": []}


def test_trace_records_calls_arguments_and_result_summary():
    call = NS(name="get_food_nutrition", args={"food_name": "milk"})
    history = [
        NS(parts=[NS(function_call=call, function_response=None)]),
        NS(parts=[_part(response=("get_food_nutrition", {"error": "O serviço externo respondeu com erro 429."}))]),
    ]
    trace = _collect_tool_results(history)["trace"]
    assert trace[0] == {"call": "get_food_nutrition", "args": {"food_name": "milk"}}
    assert trace[1]["summary"] == {"error": "O serviço externo respondeu com erro 429."}
