"""AgentScope model and agent factory.

Model names come from the frozen registry (config.models); nothing here hardcodes a model string.
AgentScope's DashScopeChatModel talks to the *native* DashScope base (/api/v1), while the embedding
path uses the OpenAI-compatible base (/compatible-mode/v1) - verified live against the international
(Singapore) endpoint, so the two bases are derived from one setting rather than duplicated in .env.
"""

from __future__ import annotations

from agentscope.agent import ReActAgent
from agentscope.formatter import DashScopeChatFormatter
from agentscope.memory import InMemoryMemory
from agentscope.model import DashScopeChatModel
from agentscope.tool import Toolkit

from ..config.settings import Settings

_COMPATIBLE_SUFFIX = "/compatible-mode/v1"
_NATIVE_SUFFIX = "/api/v1"


def native_base_url(settings: Settings) -> str:
    """The native DashScope base AgentScope needs, derived from the OpenAI-compatible base."""
    base = settings.dashscope_base_url.rstrip("/")
    if base.endswith(_COMPATIBLE_SUFFIX):
        return base[: -len(_COMPATIBLE_SUFFIX)] + _NATIVE_SUFFIX
    return base


def build_chat_model(model_name: str, settings: Settings) -> DashScopeChatModel:
    """A non-streaming DashScope chat model bound to the configured (international) endpoint."""
    return DashScopeChatModel(
        model_name=model_name,
        api_key=settings.dashscope_api_key,
        stream=False,
        base_http_api_url=native_base_url(settings),
    )


def build_agent(
    *, name: str, sys_prompt: str, model_name: str, settings: Settings
) -> ReActAgent:
    """A tool-less ReAct agent used purely for structured extraction/selection."""
    return ReActAgent(
        name=name,
        sys_prompt=sys_prompt,
        model=build_chat_model(model_name, settings),
        formatter=DashScopeChatFormatter(),
        memory=InMemoryMemory(),
        toolkit=Toolkit(),
    )
