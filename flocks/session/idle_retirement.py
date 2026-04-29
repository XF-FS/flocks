"""空闲会话弃用。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from flocks.config.config import Config
from flocks.session.message import Message, MessageRole
from flocks.session.session import Session, SessionInfo
from flocks.utils.log import Log

log = Log.create(service="session.idle_retirement")

IDLE_RETIRE_TIMEOUT_MS = 8 * 60 * 60 * 1000
# IDLE_RETIRE_TIMEOUT_MS = 2 * 60 * 1000
SummaryScheduler = Callable[[SessionInfo], Awaitable[None]]


@dataclass(frozen=True)
class IdleRetirementResult:
    active_session: SessionInfo
    retired_session: SessionInfo
    last_user_message_at: int
    idle_ms: int


async def retire_if_idle(
    session: SessionInfo,
    *,
    now_ms: Optional[int] = None,
    summary_scheduler: Optional[SummaryScheduler] = None,
    source_metadata: Optional[dict[str, Any]] = None,
) -> Optional[IdleRetirementResult]:
    """必要时弃用空闲会话，并返回新会话。"""
    if not await _is_enabled():
        return None
    if session.status != "active":
        return None

    now = now_ms if now_ms is not None else int(time.time() * 1000)
    last_user_message_at = await _last_user_message_at(session.id)
    if last_user_message_at is None:
        return None

    idle_ms = now - last_user_message_at
    if idle_ms < IDLE_RETIRE_TIMEOUT_MS:
        return None

    new_session = await _create_replacement_session(session, source_metadata)
    retired_session = await _archive_retired_session(
        session,
        now_ms=now,
        last_user_message_at=last_user_message_at,
        new_session_id=new_session.id,
        source_metadata=source_metadata,
    )

    result = IdleRetirementResult(
        active_session=new_session,
        retired_session=retired_session,
        last_user_message_at=last_user_message_at,
        idle_ms=idle_ms,
    )

    if summary_scheduler is not None:
        await summary_scheduler(retired_session)

    log.info("idle_retirement.retired", {
        "session_id": session.id,
        "new_session_id": new_session.id,
        "idle_ms": idle_ms,
    })
    return result


async def _is_enabled() -> bool:
    try:
        config = await Config.get()
    except Exception as exc:
        log.warn("idle_retirement.config_error", {"error": str(exc)})
        return False

    debug = getattr(config, "debug", None)
    lifecycle = getattr(debug, "session_lifecycle", None) if debug is not None else None
    if isinstance(lifecycle, dict):
        return bool(lifecycle.get("autoRetireIdle", False))
    return bool(getattr(lifecycle, "auto_retire_idle", False))


async def _last_user_message_at(session_id: str) -> Optional[int]:
    messages = await Message.list(session_id)
    for message in reversed(messages):
        role = message.role.value if hasattr(message.role, "value") else message.role
        if role != MessageRole.USER.value:
            continue
        return _created_at(getattr(message, "time", None))
    return None


def _created_at(raw_time: Any) -> Optional[int]:
    if isinstance(raw_time, dict):
        value = raw_time.get("created")
    else:
        value = getattr(raw_time, "created", None)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


async def _create_replacement_session(
    session: SessionInfo,
    source_metadata: Optional[dict[str, Any]],
) -> SessionInfo:
    metadata = {
        "retiredFromSessionID": session.id,
        "retirementReason": "idle_timeout",
    }
    if source_metadata:
        metadata["retiredSource"] = source_metadata
    kwargs: dict[str, Any] = {
        "agent": session.agent,
        "model": session.model,
        "provider": session.provider,
        "model_pinned": session.model_pinned,
        "memory_enabled": session.memory_enabled,
        "category": session.category,
        "owner_user_id": session.owner_user_id,
        "owner_username": session.owner_username,
        "metadata": metadata,
    }
    return await Session.create(
        project_id=session.project_id,
        directory=session.directory,
        permission=session.permission,
        **kwargs,
    )


async def _archive_retired_session(
    session: SessionInfo,
    *,
    now_ms: int,
    last_user_message_at: int,
    new_session_id: str,
    source_metadata: Optional[dict[str, Any]],
) -> SessionInfo:
    time_data = session.time.model_dump()
    time_data["archived"] = now_ms

    metadata = dict(session.metadata or {})
    metadata.update({
        "idleRetired": True,
        "idleRetiredAt": now_ms,
        "idleRetiredLastUserMessageAt": last_user_message_at,
        "idleRetiredNewSessionID": new_session_id,
    })
    if source_metadata:
        metadata["idleRetiredSource"] = source_metadata

    updated = await Session.update(
        project_id=session.project_id,
        session_id=session.id,
        status="archived",
        time=time_data,
        metadata=metadata,
    )
    if updated is None:
        raise RuntimeError(f"Failed to archive idle session {session.id}")
    return updated
