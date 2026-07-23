from __future__ import annotations

import json

from app.agent.cli import main


def test_cli_tools_lists_json(capsys) -> None:
    code = main(["tools"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert "tools" in payload
    assert any(item["name"] == "preview_bot_config" for item in payload["tools"])


def test_cli_preview_uses_tool_layer(monkeypatch, capsys) -> None:
    from app.agent import cli as cli_module

    def fake_call_tool(name, arguments=None, client=None):
        assert name == "preview_bot_config"
        assert arguments["strategy_id"] == "trend_following_core"
        assert arguments["use_testnet"] is True
        return {"ok": True, "tool": name, "result": {"preview_only": True}}

    monkeypatch.setattr(cli_module, "call_tool", fake_call_tool)
    code = main(
        [
            "preview",
            "--strategy",
            "trend_following_core",
            "--exchange",
            "okx",
            "--testnet",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
