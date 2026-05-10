"""Tests for Minerva MCP Server — tool registration and server startup."""

import pytest


class TestMCPServer:
    """Tests for MCP server tool registration."""

    def test_mcp_server_imports(self):
        """Test MCP server module imports without errors."""
        from minerva.mcp_server.server import mcp
        assert mcp is not None
        assert mcp.name == "Minerva Deep Research"

    @pytest.mark.asyncio
    async def test_mcp_server_has_all_tools(self):
        """Test all 5 Super Tools are registered."""
        from minerva.mcp_server.server import mcp
        tools = await mcp.list_tools()
        tool_names = {t.name for t in tools}
        expected = {"research_now", "research_schedule", "research_watch",
                     "knowledge_search", "knowledge_ingest"}
        assert tool_names == expected

    @pytest.mark.asyncio
    async def test_research_now_tool_exists(self):
        """Test research_now tool is callable."""
        from minerva.mcp_server.server import mcp
        tools = await mcp.list_tools()
        research_tool = next(t for t in tools if t.name == "research_now")
        assert research_tool is not None
        params = research_tool.parameters
        assert "query" in params.get("properties", params)

    def test_cli_mcp_command_registered(self):
        """Test CLI has mcp command."""
        from minerva.cli import build_parser
        parser = build_parser()
        # MCP should be a valid subcommand
        actions = [a for a in parser._actions if hasattr(a, 'choices')]
        subcommands = set()
        for a in actions:
            if hasattr(a, 'choices') and a.choices:
                subcommands.update(a.choices.keys())
        assert "mcp" in subcommands
