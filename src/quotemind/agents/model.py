"""AgentScope model and agent factory.

Model names come from the frozen registry (config.models); nothing here hardcodes a model string.
AgentScope's DashScopeChatModel talks to the *native* DashScope base (/api/v1), while the embedding
path uses the OpenAI-compatible base (/compatible-mode/v1) - verified live against the international
(Singapore) endpoint, so the two bases are derived from one setting rather than duplicated in .env.
"""

from __future__ import annotations

from typing import Any, Protocol

from agentscope.agent import ReActAgent
from agentscope.formatter import DashScopeChatFormatter
from agentscope.memory import InMemoryMemory
from agentscope.model import DashScopeChatModel
from agentscope.tool import Toolkit

from ..config.settings import Settings

_COMPATIBLE_SUFFIX = "/compatible-mode/v1"
_NATIVE_SUFFIX = "/api/v1"


class UsageSink(Protocol):
    """Anything that can be told how many tokens a call consumed (obs.trace.StepRecorder)."""

    def usage(self, tokens_in: int = 0, tokens_out: int = 0) -> None: ...


def _tokens(usage: Any, *names: str) -> int:
    for name in names:
        value = getattr(usage, name, None)
        if value:
            return int(value)
    return 0


class _UsageCapturingModel(DashScopeChatModel):
    """Reports the model's own token counts to a sink (TASK-110/112) - never an estimate."""

    def __init__(self, *, sink: UsageSink, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._sink = sink

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        response = await super().__call__(*args, **kwargs)
        usage = getattr(response, "usage", None)
        if usage is not None:
            self._sink.usage(
                _tokens(usage, "input_tokens", "prompt_tokens"),
                _tokens(usage, "output_tokens", "completion_tokens"),
            )
        return response


def native_base_url(settings: Settings) -> str:
    """The native DashScope base AgentScope needs, derived from the OpenAI-compatible base."""
    base = settings.dashscope_base_url.rstrip("/")
    if base.endswith(_COMPATIBLE_SUFFIX):
        return base[: -len(_COMPATIBLE_SUFFIX)] + _NATIVE_SUFFIX
    return base


def build_chat_model(
    model_name: str, settings: Settings, *, usage: UsageSink | None = None
) -> DashScopeChatModel:
    """A non-streaming DashScope chat model bound to the configured (international) endpoint."""
    kwargs = {
        "model_name": model_name,
        "api_key": settings.dashscope_api_key,
        "stream": False,
        "base_http_api_url": native_base_url(settings),
    }
    if usage is None:
        return DashScopeChatModel(**kwargs)  # type: ignore[arg-type]
    return _UsageCapturingModel(sink=usage, **kwargs)  # type: ignore[arg-type]


def build_agent(
    *,
    name: str,
    sys_prompt: str,
    model_name: str,
    settings: Settings,
    usage: UsageSink | None = None,
) -> ReActAgent:
    """A tool-less ReAct agent used purely for structured extraction/selection."""
    return ReActAgent(
        name=name,
        sys_prompt=sys_prompt,
        model=build_chat_model(model_name, settings, usage=usage),
        formatter=DashScopeChatFormatter(),
        memory=InMemoryMemory(),
        toolkit=Toolkit(),
    )
