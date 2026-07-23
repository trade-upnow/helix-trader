from __future__ import annotations

from app.agent.metadata import (
    enrich_strategy_payload,
    explain_config,
    list_strategy_specs,
    merge_preview_config,
)


def test_strategy_specs_cover_known_ids() -> None:
    ids = {item["id"] for item in list_strategy_specs()}
    assert "trend_following_core" in ids
    assert "trend_breakout_accel" in ids


def test_enrich_strategy_includes_parameter_docs() -> None:
    payload = enrich_strategy_payload("trend_following_core")
    assert payload["default_params"]["timeframe"] == "15m"
    assert "leverage" in payload["parameter_docs"]
    assert "disclaimer" in payload


def test_merge_preview_defaults_to_testnet() -> None:
    config = merge_preview_config(
        strategy_id="trend_breakout_accel",
        exchange="okx",
    )
    assert config["use_testnet"] is True
    assert config["strategy_id"] == "trend_breakout_accel"
    assert config["leverage"] == 2


def test_explain_config_contains_human_text() -> None:
    lines = explain_config({"leverage": 2, "use_testnet": True})
    assert any("leverage=2" in line for line in lines)
    assert any("use_testnet=True" in line for line in lines)
