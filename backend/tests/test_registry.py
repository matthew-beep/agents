from agents import registry


# test that orchestrator_tools returns one schema per registered agent
def test_orchestrator_tools_one_schema_per_agent():
    tools = registry.orchestrator_tools()
    assert len(tools) == len(registry.AGENTS)

# test that each schema is a well-formed function tool with a required query param
def test_orchestrator_tools_schema_shape():
    tools = registry.orchestrator_tools()
    names = {a.name for a in registry.AGENTS.values()}
    for tool in tools:
        assert tool["type"] == "function"
        fn = tool["function"]
        assert fn["name"] in names
        assert fn["description"]
        assert fn["parameters"]["required"] == ["query"]
        assert "query" in fn["parameters"]["properties"]

# test that agent_directory lists every agent's name and description
def test_agent_directory_lists_every_agent():
    directory = registry.agent_directory()
    for agent in registry.AGENTS.values():
        assert agent.name in directory
        assert agent.description in directory

# test that every tool schema name has a matching tool_map entry and vice versa,
# for every registered agent
def test_agent_tools_and_tool_map_are_consistent():
    for agent in registry.AGENTS.values():
        schema_names = {t["function"]["name"] for t in agent.tools}
        map_names = set(agent.tool_map.keys())
        assert schema_names == map_names
