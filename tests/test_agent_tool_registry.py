from agent_tool_registry import load_registry


def test_agent_tool_registry_loads_and_exports_categories() -> None:
    _catalog, tools = load_registry()
    names = {tool["name"] for tool in tools}
    categories = {tool["category"] for tool in tools}

    assert "query-platform-context" in names
    assert "converge-rag-context" in names
    assert {"observe", "report", "execute"}.issubset(categories)
