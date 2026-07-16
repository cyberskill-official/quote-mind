"""TASK-002: config loads from env and fails fast, naming a missing required variable."""

from __future__ import annotations

from pathlib import Path

import pytest

from quotemind.config.settings import get_settings, require_settings


def test_settings_load_with_env() -> None:
    settings = get_settings()
    assert settings.dashscope_api_key == "sk-test-dummy"
    assert settings.oss_bucket_inbox == "quotemind-inbox"  # frozen default (section 12.6)
    assert settings.mail_transport == "stub"  # TASK-093 demo default


def test_missing_required_var_exits_naming_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)  # isolate from any real .env at the repo root
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    with pytest.raises(SystemExit) as exc_info:
        require_settings()
    assert "DASHSCOPE_API_KEY" in str(exc_info.value)
