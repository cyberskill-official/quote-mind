"""Runtime configuration (QM-SPEC-001 section 4.7).

Loaded exclusively from environment variables; the API function fails fast at cold start
if a required (P0) variable is missing (FR-002).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# DashScope exposes the same models under two bases, and they are not interchangeable:
#   /compatible-mode/v1  the OpenAI-compatible API - chat, embeddings, vision (what `openai` wants)
#   /api/v1              the native API - what AgentScope's DashScopeChatModel wants
#
# Five call sites hand `dashscope_base_url` straight to an OpenAI client, and one derives the native
# base from it. That makes "this setting is the COMPATIBLE base" a load-bearing invariant - and it
# was, until now, defended by nothing but a comment. When a deploy handed it the native base
# instead,
# chat kept working (native is what chat wanted anyway) and every embedding call went to
# /api/v1/embeddings, which does not exist. The matcher got a 404 on every quote. The site was up,
# the models answered, and no quote could be produced.
#
# So the invariant is enforced here, once, at the only boundary the value can enter through.
_NATIVE_SUFFIX = "/api/v1"
_COMPATIBLE_SUFFIX = "/compatible-mode/v1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Required (P0) - no defaults, so a missing value is a hard error at startup.
    dashscope_api_key: str
    alibaba_cloud_access_key_id: str
    alibaba_cloud_access_key_secret: str
    tablestore_endpoint: str
    tablestore_instance: str
    mail_from: str
    demo_api_token: str

    # Defaulted to the canonical values in section 4.7.
    dashscope_base_url: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    oss_endpoint: str = "https://oss-ap-southeast-1.aliyuncs.com"

    @field_validator("dashscope_base_url")
    @classmethod
    def _always_the_compatible_base(cls, value: str) -> str:
        """Whichever DashScope base is configured, store the OpenAI-compatible one.

        `agents.model.native_base_url` derives `/api/v1` back out of it for AgentScope. Deriving
        both directions from one normalized value means a wrong-but-plausible env var can no longer
        silently point half the system at a 404 - it is simply corrected.
        """
        base = value.rstrip("/")
        if base.endswith(_NATIVE_SUFFIX):
            return base[: -len(_NATIVE_SUFFIX)] + _COMPATIBLE_SUFFIX
        return base

    oss_bucket_inbox: str = "quotemind-inbox"
    oss_bucket_artifacts: str = "quotemind-artifacts"

    # Stub transport is the demo default (FR-093); set MAIL_TRANSPORT=smtp for real mail.
    mail_transport: Literal["stub", "smtp"] = "stub"
    directmail_smtp_host: str = "smtpdm-ap-southeast-1.aliyun.com"
    directmail_smtp_port: int = 465
    directmail_user: str | None = None
    directmail_password: str | None = None

    fx_usd_vnd: int = 25400
    margin_floor_pct: int = 5
    quote_validity_days: int = 14

    # FR-111: prompt/response bodies are excluded from the trace unless this is switched on.
    trace_content: bool = False
    otel_semconv_stability_opt_in: str = "gen_ai_latest_experimental"
    qm_env: Literal["local", "fc"] = "local"
    region: str = "ap-southeast-1"


def _missing_env_vars(exc: ValidationError) -> list[str]:
    names: list[str] = []
    for err in exc.errors():
        if err.get("type") == "missing" and err.get("loc"):
            names.append(str(err["loc"][0]).upper())
    return names


def require_settings() -> Settings:
    """Construct Settings, or exit with a single-line actionable error (FR-002 AC)."""
    try:
        return Settings()  # type: ignore[call-arg]  # values come from the environment
    except ValidationError as exc:
        missing = _missing_env_vars(exc)
        if missing:
            raise SystemExit(
                "Missing required environment variable(s): " + ", ".join(sorted(missing))
            ) from exc
        raise SystemExit(f"Invalid configuration: {exc}") from exc


@lru_cache
def get_settings() -> Settings:
    return require_settings()
