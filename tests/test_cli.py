"""Tests for mcp-gw CLI argument parsing."""

import argparse
import json
from unittest.mock import patch

import pytest

from mcp_gateway.cli import main, get_gateway_url


class TestGatewayUrl:
    def test_default(self):
        args = argparse.Namespace(gateway=None)
        with patch.dict("os.environ", {}, clear=True):
            assert get_gateway_url(args) == "http://localhost:8085"

    def test_env_var(self):
        args = argparse.Namespace(gateway=None)
        with patch.dict("os.environ", {"MCP_GATEWAY_URL": "http://myhost:9000"}):
            assert get_gateway_url(args) == "http://myhost:9000"

    def test_flag_overrides_env(self):
        args = argparse.Namespace(gateway="http://flag:1234")
        with patch.dict("os.environ", {"MCP_GATEWAY_URL": "http://env:5678"}):
            assert get_gateway_url(args) == "http://flag:1234"

    def test_trailing_slash_stripped(self):
        args = argparse.Namespace(gateway="http://host:8085/")
        assert get_gateway_url(args) == "http://host:8085"


class TestMainArgParsing:
    def test_no_args_exits(self):
        with pytest.raises(SystemExit):
            with patch("sys.argv", ["mcp-gw"]):
                main()

    def test_list_command(self, capsys):
        with patch("sys.argv", ["mcp-gw", "list"]), \
             patch("mcp_gateway.cli.request") as mock_req:
            mock_req.return_value = [
                {"id": "time", "status": "connected", "tools": ["get_current_time"]}
            ]
            main()
            out = capsys.readouterr().out
            assert "time" in out
            assert "connected" in out
            assert "1 tools" in out

    def test_call_inline_json(self, capsys):
        with patch("sys.argv", ["mcp-gw", "call", "time", "get_current_time", '{"timezone":"UTC"}']), \
             patch("mcp_gateway.cli.request") as mock_req:
            mock_req.return_value = {
                "success": True,
                "result": [{"type": "text", "text": "2026-03-09"}],
            }
            main()
            out = capsys.readouterr().out
            assert "2026-03-09" in out

    def test_call_empty_args(self, capsys):
        with patch("sys.argv", ["mcp-gw", "call", "github", "get_me"]), \
             patch("mcp_gateway.cli.request") as mock_req:
            mock_req.return_value = {
                "success": True,
                "result": [{"type": "text", "text": "user123"}],
            }
            main()
            out = capsys.readouterr().out
            assert "user123" in out

    def test_grep_command(self, capsys):
        with patch("sys.argv", ["mcp-gw", "grep", "search"]), \
             patch("mcp_gateway.cli.request") as mock_req:
            mock_req.return_value = [
                {"server_id": "github", "name": "search_code", "description": "Search code"}
            ]
            main()
            out = capsys.readouterr().out
            assert "github/search_code" in out

    def test_json_flag(self, capsys):
        with patch("sys.argv", ["mcp-gw", "--json", "list"]), \
             patch("mcp_gateway.cli.request") as mock_req:
            mock_req.return_value = [{"id": "time", "status": "connected", "tools": []}]
            main()
            out = capsys.readouterr().out
            parsed = json.loads(out)
            assert parsed[0]["id"] == "time"
