"""TASK-080: exhaustive legal and illegal Status transitions."""

from __future__ import annotations

import pytest

from quotemind.models import (
    LEGAL_TRANSITIONS,
    TERMINAL_STATES,
    IllegalTransitionError,
    Status,
    assert_transition,
    can_transition,
)


def test_every_pair_is_legal_or_raises() -> None:
    for current in Status:
        allowed = LEGAL_TRANSITIONS.get(current, set())
        for target in Status:
            if target in allowed:
                assert can_transition(current, target)
                assert assert_transition(current, target) is target
            else:
                assert not can_transition(current, target)
                with pytest.raises(IllegalTransitionError):
                    assert_transition(current, target)


def test_terminal_states_have_no_outgoing() -> None:
    for status in TERMINAL_STATES:
        assert not LEGAL_TRANSITIONS.get(status)
    for terminal in (
        Status.SENT,
        Status.REJECTED,
        Status.CRITIC_FAILED,
        Status.NEEDS_MANUAL,
        Status.NEEDS_CLARIFICATION,
        Status.FAILED_INTAKE,
        Status.FAILED_PARSE,
        Status.FAILED_PRICE,
        Status.FAILED_DRAFT,
        Status.FAILED_DISPATCH,
    ):
        assert terminal in TERMINAL_STATES


def test_happy_path_is_legal() -> None:
    path = [
        Status.RECEIVED,
        Status.PARSING,
        Status.MATCHING,
        Status.PRICING,
        Status.DRAFTING,
        Status.VALIDATING,
        Status.PENDING_APPROVAL,
        Status.APPROVED,
        Status.DISPATCHING,
        Status.SENT,
    ]
    for current, target in zip(path, path[1:], strict=False):
        assert assert_transition(current, target) is target


def test_revise_loop_returns_to_drafting() -> None:
    assert can_transition(Status.PENDING_APPROVAL, Status.REVISING)
    assert can_transition(Status.REVISING, Status.DRAFTING)
    assert not can_transition(Status.REVISING, Status.PENDING_APPROVAL)
