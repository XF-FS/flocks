from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from flocks.session.idle_retirement import IDLE_RETIRE_TIMEOUT_MS, retire_if_idle
from flocks.session.message import MessageRole
from flocks.session.session import SessionInfo, SessionTime


def _session(**overrides) -> SessionInfo:
    defaults = {
        "id": "ses_old",
        "projectID": "proj_test",
        "directory": "/tmp/project",
        "agent": "rex",
        "model": "claude-test",
        "provider": "anthropic",
        "model_pinned": True,
        "memory_enabled": True,
        "category": "user",
        "ownerUserID": "user_1",
        "ownerUsername": "alice",
        "time": SessionTime(created=1_000, updated=2_000),
    }
    defaults.update(overrides)
    return SessionInfo(**defaults)


def _enabled_config(enabled: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        session_lifecycle=SimpleNamespace(auto_retire_idle=enabled),
    )


@pytest.mark.asyncio
async def test_retire_if_idle_ignores_disabled_config():
    session = _session()

    with patch(
        "flocks.session.idle_retirement.Config.get",
        new=AsyncMock(return_value=_enabled_config(False)),
    ), patch(
        "flocks.session.idle_retirement.Message.list",
        new=AsyncMock(),
    ) as list_mock:
        result = await retire_if_idle(session, now_ms=IDLE_RETIRE_TIMEOUT_MS + 1)

    assert result is None
    list_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_retire_if_idle_ignores_sessions_without_user_messages():
    session = _session()

    with patch(
        "flocks.session.idle_retirement.Config.get",
        new=AsyncMock(return_value=_enabled_config()),
    ), patch(
        "flocks.session.idle_retirement.Message.list",
        new=AsyncMock(return_value=[]),
    ):
        result = await retire_if_idle(session, now_ms=IDLE_RETIRE_TIMEOUT_MS + 1)

    assert result is None


@pytest.mark.asyncio
async def test_retire_if_idle_ignores_recent_user_message():
    session = _session()
    user_message = SimpleNamespace(
        role=MessageRole.USER,
        time={"created": 10_000},
    )

    with patch(
        "flocks.session.idle_retirement.Config.get",
        new=AsyncMock(return_value=_enabled_config()),
    ), patch(
        "flocks.session.idle_retirement.Message.list",
        new=AsyncMock(return_value=[user_message]),
    ):
        result = await retire_if_idle(
            session,
            now_ms=10_000 + IDLE_RETIRE_TIMEOUT_MS - 1,
        )

    assert result is None


@pytest.mark.asyncio
async def test_retire_if_idle_archives_old_session_and_creates_replacement():
    session = _session(metadata={"existing": True})
    new_session = _session(
        id="ses_new",
        metadata={"retiredFromSessionID": "ses_old", "retirementReason": "idle_timeout"},
    )
    retired_session = _session(
        status="archived",
        metadata={
            "existing": True,
            "idleRetired": True,
            "idleRetiredNewSessionID": "ses_new",
        },
    )
    user_message = SimpleNamespace(
        role=MessageRole.USER,
        time={"created": 10_000},
    )
    summary_scheduler = AsyncMock()

    with patch(
        "flocks.session.idle_retirement.Config.get",
        new=AsyncMock(return_value=_enabled_config()),
    ), patch(
        "flocks.session.idle_retirement.Message.list",
        new=AsyncMock(return_value=[user_message]),
    ), patch(
        "flocks.session.idle_retirement.Session.create",
        new=AsyncMock(return_value=new_session),
    ) as create_mock, patch(
        "flocks.session.idle_retirement.Session.update",
        new=AsyncMock(return_value=retired_session),
    ) as update_mock:
        result = await retire_if_idle(
            session,
            now_ms=10_000 + IDLE_RETIRE_TIMEOUT_MS,
            summary_scheduler=summary_scheduler,
            source_metadata={
                "sourceType": "wecom_new",
                "senderID": "alice",
            },
        )

    assert result is not None
    assert result.active_session.id == "ses_new"
    assert result.retired_session.status == "archived"
    assert result.idle_ms == IDLE_RETIRE_TIMEOUT_MS
    summary_scheduler.assert_awaited_once_with(retired_session)

    create_mock.assert_awaited_once()
    assert create_mock.await_args.kwargs["agent"] == "rex"
    assert create_mock.await_args.kwargs["model"] == "claude-test"
    assert create_mock.await_args.kwargs["provider"] == "anthropic"
    assert create_mock.await_args.kwargs["model_pinned"] is True
    assert create_mock.await_args.kwargs["memory_enabled"] is True

    update_mock.assert_awaited_once()
    assert update_mock.await_args.kwargs["status"] == "archived"
    assert update_mock.await_args.kwargs["metadata"]["idleRetired"] is True
    assert update_mock.await_args.kwargs["metadata"]["idleRetiredNewSessionID"] == "ses_new"
    assert update_mock.await_args.kwargs["metadata"]["idleRetiredSource"]["sourceType"] == "wecom_new"
    assert create_mock.await_args.kwargs["metadata"]["retiredSource"]["senderID"] == "alice"
