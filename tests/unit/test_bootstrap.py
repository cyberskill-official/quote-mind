"""FR-012: the cold-start model check, its fallbacks, and what /health admits to."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from quotemind.api import app as app_module
from quotemind.api.app import app
from quotemind.config.bootstrap import AVAILABLE, FALLBACK, UNKNOWN, check_models, health_models
from quotemind.config.models import MODEL_CONSTANTS


class _Settings:
    dashscope_api_key = "sk-test"
    dashscope_base_url = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"


class _Endpoint:
    def __init__(self, client: _Client, kind: str) -> None:
        self.client = client
        self.kind = kind

    def create(self, *, model: str, **kwargs: Any) -> object:
        self.client.calls.append((model, self.kind, kwargs))
        if model in self.client.down:
            raise RuntimeError(f"model {model} not found")
        return object()


class _Client:
    """A DashScope stand-in: refuses the models in `down`, and records how each was called."""

    def __init__(self, down: set[str] | None = None) -> None:
        self.down = down or set()
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.embeddings = _Endpoint(self, "embeddings")
        self.chat = self

    @property
    def completions(self) -> _Endpoint:
        return _Endpoint(self, "chat")

    @property
    def probed(self) -> list[str]:
        return [model for model, _, _ in self.calls]


def test_all_models_available_means_no_substitution() -> None:
    client = _Client()
    statuses = check_models(_Settings(), client=client)  # type: ignore[arg-type]

    assert {status.role for status in statuses} == set(MODEL_CONSTANTS)
    assert all(status.state == AVAILABLE for status in statuses)
    assert all(not status.substituted for status in statuses)
    assert health_models(statuses)["substitutions"] == {}


def test_each_distinct_model_is_probed_only_once() -> None:
    # Several roles share an id. Probing per role would burn calls on every cold start for nothing.
    client = _Client()
    check_models(_Settings(), client=client)  # type: ignore[arg-type]
    assert len(client.probed) == len(set(MODEL_CONSTANTS.values()))


def test_a_retired_primary_activates_its_documented_fallback() -> None:
    # FR-012 AC: qwen-vl-ocr unavailable -> the parser runs on qwen3-vl-plus, and /health says so.
    client = _Client(down={"qwen-vl-ocr"})
    statuses = check_models(_Settings(), client=client)  # type: ignore[arg-type]

    vision = next(status for status in statuses if status.role == "parser_vision")
    assert vision.state == FALLBACK
    assert vision.primary == "qwen-vl-ocr"
    assert vision.effective == "qwen3-vl-plus"

    body = health_models(statuses)
    assert body["models"]["parser_vision"] == "qwen3-vl-plus"
    assert body["substitutions"]["parser_vision"]["primary"] == "qwen-vl-ocr"
    # Everything else is untouched - one dead model must not reroute the whole system.
    assert body["models"]["planner"] == "qwen3-max"


def test_each_model_is_probed_in_the_modality_it_actually_answers() -> None:
    # The bug the live run caught: probing every id with a text-chat call made the embedding model
    # and the vision model both look dead, and the vision parser "fell back" on a healthy service.
    # A health check that manufactures its own outages is worse than none.
    client = _Client()
    check_models(_Settings(), client=client)  # type: ignore[arg-type]
    by_model = {model: (kind, kwargs) for model, kind, kwargs in client.calls}

    assert by_model["text-embedding-v4"][0] == "embeddings"
    assert by_model["qwen3-max"][0] == "chat"

    kind, kwargs = by_model["qwen-vl-ocr"]
    assert kind == "chat"
    parts = kwargs["messages"][0]["content"]  # a vision model needs an image part, or it 400s
    assert any(part["type"] == "image_url" for part in parts)


def test_a_model_with_no_fallback_proceeds_on_the_primary_and_is_flagged() -> None:
    # text-embedding-v4 has no documented substitute. Refusing to boot would be worse than trying:
    # the probe may simply have hit a transient. But the uncertainty must be visible.
    client = _Client(down={"text-embedding-v4"})
    statuses = check_models(_Settings(), client=client)  # type: ignore[arg-type]

    embed = next(status for status in statuses if status.role == "embed")
    assert embed.state == UNKNOWN
    assert embed.effective == "text-embedding-v4"  # unchanged
    assert not embed.substituted

    body = health_models(statuses)
    assert "embed" in body["unverified"]
    assert body["substitutions"] == {}


def test_health_says_unverified_when_the_probe_could_not_run() -> None:
    # The honest state when the probe did not succeed. Reporting the frozen constants with no caveat
    # would imply a check happened that did not - and for a while, in production, it had not.
    app_module._MODEL_STATUS = []
    body = TestClient(app).get("/health").json()

    assert body["status"] == "ok"
    assert body["models"] == MODEL_CONSTANTS
    assert body["unverified"] == sorted(MODEL_CONSTANTS)


def test_health_reports_the_substitution_after_a_fallback_boot() -> None:
    client = _Client(down={"qwen-vl-ocr"})
    app_module._MODEL_STATUS = check_models(_Settings(), client=client)  # type: ignore[arg-type]
    try:
        body = TestClient(app).get("/health").json()
        assert body["models"]["parser_vision"] == "qwen3-vl-plus"
        assert body["substitutions"]["parser_vision"]["using"] == "qwen3-vl-plus"
    finally:
        app_module._MODEL_STATUS = []


def test_initialize_never_raises_even_if_the_probe_blows_up(monkeypatch: Any) -> None:
    # A boot check that can take the API down is a liability, not a safeguard.
    def explode(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("DashScope unreachable")

    monkeypatch.setattr(app_module, "check_models", explode)
    app_module._PROBE_ATTEMPTED = False
    app_module.initialize()  # must not raise
    assert app_module._MODEL_STATUS == []

    body = TestClient(app).get("/health").json()
    assert body["status"] == "ok"  # still serving


def test_health_runs_the_probe_itself_when_the_initializer_never_did(monkeypatch: Any) -> None:
    # The bug this guards: Function Compute silently deployed the function with no initializer, so
    # the probe never ran and /health reported every model unverified. FR-012 must not depend on a
    # platform hook firing - the probe runs the first time anything needs its answer.
    calls: list[int] = []

    def probe(*_args: Any, **_kwargs: Any) -> Any:
        calls.append(1)
        return check_models(_Settings(), client=_Client())  # type: ignore[arg-type]

    monkeypatch.setattr(app_module, "check_models", probe)
    app_module._PROBE_ATTEMPTED = False  # as if the process had just started

    body = TestClient(app).get("/health").json()
    assert body["unverified"] == []  # it probed, and everything answered
    assert body["models"]["planner"] == "qwen3-max"

    TestClient(app).get("/health")
    assert calls == [1], "the probe must run once per process, not once per request"


def test_a_failed_probe_is_not_retried_on_every_request(monkeypatch: Any) -> None:
    # A DashScope outage must not turn every /health into a slow call.
    calls: list[int] = []

    def explode(*_args: Any, **_kwargs: Any) -> None:
        calls.append(1)
        raise RuntimeError("DashScope unreachable")

    monkeypatch.setattr(app_module, "check_models", explode)
    app_module._PROBE_ATTEMPTED = False

    for _ in range(3):
        assert TestClient(app).get("/health").json()["status"] == "ok"
    assert calls == [1]


# --- the distinction the live run forced: absence vs a bad argument ---


class _Rejecting(_Client):
    """Answers, but rejects the probe's input - a live model with a picky API."""

    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

    @property
    def completions(self) -> Any:
        return _Raiser(self, self.message)


class _Raiser:
    def __init__(self, client: _Rejecting, message: str) -> None:
        self.client = client
        self.message = message

    def create(self, *, model: str, **_kwargs: Any) -> object:
        self.client.calls.append((model, "chat", {}))
        raise RuntimeError(self.message)


def test_a_model_that_rejects_the_probe_is_alive_not_missing() -> None:
    # The failure the live run actually produced: qwen-vl-ocr answered with
    # "400 InvalidParameter: image must be larger than 10px". That is a deployed, reachable model
    # refusing a malformed request - and treating it as an outage would reroute the vision parser
    # onto a different model for no reason at all.
    client = _Rejecting("400 InvalidParameter: the image length and width do not meet the model")
    statuses = check_models(_Settings(), client=client)  # type: ignore[arg-type]

    vision = next(status for status in statuses if status.role == "parser_vision")
    assert vision.state == AVAILABLE
    assert vision.effective == "qwen-vl-ocr"  # no substitution
    assert not vision.substituted
    assert health_models(statuses)["substitutions"] == {}


def test_a_model_that_is_genuinely_gone_does_fall_back() -> None:
    # The case FR-012 is actually for: Model Studio retires the id.
    client = _Rejecting("404 model_not_found: qwen-vl-ocr does not exist")
    statuses = check_models(_Settings(), client=client)  # type: ignore[arg-type]

    vision = next(status for status in statuses if status.role == "parser_vision")
    assert vision.state == FALLBACK
    assert vision.effective == "qwen3-vl-plus"
