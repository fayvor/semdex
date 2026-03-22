import asyncio
import tempfile
from pathlib import Path

from semdex.server import create_server


def test_server_has_search_tool():
    server = create_server(project_root=Path("/tmp/fake"))
    tool_names = [t.name for t in asyncio.run(server.list_tools())]
    assert "search" in tool_names


def test_server_has_related_tool():
    server = create_server(project_root=Path("/tmp/fake"))
    tool_names = [t.name for t in asyncio.run(server.list_tools())]
    assert "related" in tool_names


def test_server_has_summary_tool():
    server = create_server(project_root=Path("/tmp/fake"))
    tool_names = [t.name for t in asyncio.run(server.list_tools())]
    assert "summary" in tool_names
