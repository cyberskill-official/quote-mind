"""Shared fixtures. Provides dummy env so Settings loads offline (no paid-API calls)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

_REQUIRED_ENV = {
    "DASHSCOPE_API_KEY": "sk-test-dummy",
    "ALIBABA_CLOUD_ACCESS_KEY_ID": "test-id",
    "ALIBABA_CLOUD_ACCESS_KEY_SECRET": "test-secret",
    "TABLESTORE_ENDPOINT": "https://quotemind.ap-southeast-1.ots.aliyuncs.com",
    "TABLESTORE_INSTANCE": "quotemind",
    "MAIL_FROM": "quotes@demo.cyberskill.world",
    "DEMO_API_TOKEN": "test-token-abcdef0123456789",
}


@pytest.fixture(autouse=True)
def _dummy_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for key, value in _REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)
    from quotemind.config.settings import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
