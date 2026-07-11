"""The DashScope base URL invariant, which took the live site down for quoting.

DashScope serves the same models under two bases and they are NOT interchangeable:

    /compatible-mode/v1   the OpenAI-compatible API - chat, embeddings, vision
    /api/v1               the native API - what AgentScope's DashScopeChatModel wants

Five call sites hand `settings.dashscope_base_url` straight to an `OpenAI(...)` client, so it must
be the *compatible* base. One (`agents.model.native_base_url`) derives the native base back out of
it. That made "this setting is always the compatible base" load-bearing - and it was defended by
nothing but a docstring.

Then CD ran for the first time, with this line in the workflow:

    DASHSCOPE_BASE_URL: ${{ vars.DASHSCOPE_BASE_URL ||
                          'https://dashscope-intl.aliyuncs.com/api/v1' }}

A fallback typed by hand and never once executed, because until the secrets existed the deploy job
no-opped. It was wrong. Chat kept working - native is what chat wanted anyway - so `/health` was
green, the model probe passed, the dashboard rendered, and every single embedding call went to
`/api/v1/embeddings`, which does not exist. Every RFQ died at `failed_parse` with a 404 nobody saw.

The system was up. The models answered. It could not produce a quote.

The fix is not "fix the workflow" - that is fixing the instance. `Settings` now normalizes either
form to the compatible base, so both derivations come from one value that cannot be wrong. These
tests are the fence.
"""

from __future__ import annotations

import pytest

from quotemind.agents import native_base_url
from quotemind.config.settings import Settings

COMPATIBLE = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
NATIVE = "https://dashscope-intl.aliyuncs.com/api/v1"

REQUIRED = {
    "dashscope_api_key": "k",
    "alibaba_cloud_access_key_id": "k",
    "alibaba_cloud_access_key_secret": "k",
    "tablestore_endpoint": "https://t",
    "tablestore_instance": "t",
    "mail_from": "a@b.c",
    "demo_api_token": "t",
}


def _settings(base: str) -> Settings:
    return Settings(**REQUIRED, dashscope_base_url=base)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "configured",
    [
        COMPATIBLE,
        NATIVE,  # the one that broke production
        NATIVE + "/",  # ... and with the trailing slash a human would add
        COMPATIBLE + "/",
    ],
)
def test_the_setting_is_always_the_compatible_base(configured: str) -> None:
    """Whatever is configured, what the OpenAI clients receive is the compatible base."""
    assert _settings(configured).dashscope_base_url == COMPATIBLE


@pytest.mark.parametrize("configured", [COMPATIBLE, NATIVE])
def test_agentscope_always_gets_the_native_base(configured: str) -> None:
    """And AgentScope still gets /api/v1, derived - not duplicated in the environment."""
    assert native_base_url(_settings(configured)) == NATIVE


def test_the_two_bases_are_never_the_same_value() -> None:
    """The bug in one line: if these ever collide, either chat or embeddings is talking to a 404."""
    settings = _settings(NATIVE)
    assert settings.dashscope_base_url != native_base_url(settings)


def test_a_default_deployment_is_correct_without_the_variable_being_set() -> None:
    """No DASHSCOPE_BASE_URL at all must be right, so a deploy that omits it cannot be wrong."""
    assert Settings(**REQUIRED).dashscope_base_url == COMPATIBLE  # type: ignore[arg-type]


def test_the_embedding_path_would_have_caught_it() -> None:
    """The 404 in one assertion: the compatible base is the only one with an /embeddings route."""
    settings = _settings(NATIVE)
    assert settings.dashscope_base_url.endswith("/compatible-mode/v1")
    assert not settings.dashscope_base_url.endswith("/api/v1")
