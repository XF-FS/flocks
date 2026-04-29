"""
Channel HTTP routes: webhook callbacks, health/status, and outbound send APIs.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import AliasChoices, BaseModel, Field

from flocks.channel.gateway.manager import default_manager
from flocks.channel.registry import default_registry
from flocks.utils.log import Log

router = APIRouter()
log = Log.create(service="channel.routes")

_WECOM_NEW_REVIEW_SCHEMA = {
    "f04Gwj": "用户提问",
    "fhIosl": "机器人回复",
    "f4iZhP": "提问附件路径",
    "f8go0U": "回复附件路径",
    "f60SN8": "提问时间",
    "fb7dU8": "提问人",
}


def _normalize_channel_type(channel_type: str | None) -> str | None:
    if not channel_type:
        return None
    lower = channel_type.strip().lower()
    aliases = {
        "wecomnew": "wecom_new",
        "wecom_new": "wecom_new",
        "wecom-v2": "wecom_new",
        "wecomnewv2": "wecom_new",
        "wecom": "wecom",
        "wechat_work": "wecom",
        "wxwork": "wecom",
    }
    return aliases.get(lower, lower)


class SendMessageRequest(BaseModel):
    channel_id: str
    to: str
    text: str = Field("", validation_alias=AliasChoices("text", "message"))
    account_id: Optional[str] = None
    media_url: Optional[str] = Field(None, validation_alias=AliasChoices("media_url", "media"))
    reply_to_id: Optional[str] = None
    session_id: Optional[str] = None


class SessionSendRequest(BaseModel):
    session_id: str
    text: str = Field("", validation_alias=AliasChoices("text", "message"))
    channel_type: Optional[str] = None
    media_url: Optional[str] = Field(None, validation_alias=AliasChoices("media_url", "media"))


class OpenClawDispatchRequest(BaseModel):
    ctx: dict[str, Any]
    cfg: dict[str, Any] = Field(default_factory=dict)


class _OpenClawCollectCallbacks:
    def __init__(self) -> None:
        self.replies: list[dict[str, Any]] = []

    async def on_step_end(self, step: int) -> None:
        return None

    async def on_error(self, error_msg: str) -> None:
        await self.deliver_text(f"⚠ 处理消息时出错：{error_msg}")

    async def deliver_text(self, text: str) -> None:
        if text:
            self.replies.append({"text": text})

    async def deliver_media(self, media_url: str, text: str = "") -> None:
        if media_url:
            self.replies.append({"text": text, "mediaUrl": media_url})

    def to_loop_callbacks(self, runner_callbacks=None):
        from flocks.session.session_loop import LoopCallbacks
        return LoopCallbacks(
            on_step_end=self.on_step_end,
            on_error=self.on_error,
            runner_callbacks=runner_callbacks,
        )


def _strip_wecom_target(raw: Any) -> str:
    value = str(raw or "").strip()
    for prefix in ("wecom:group:", "wecom:user:", "wecom:"):
        if value.startswith(prefix):
            return value[len(prefix):]
    return value


def _openclaw_ctx_to_inbound(ctx: dict[str, Any]):
    from flocks.channel.base import ChatType, InboundMessage

    chat_type_raw = str(ctx.get("ChatType") or "direct").lower()
    chat_type = ChatType.GROUP if chat_type_raw == "group" else ChatType.DIRECT
    chat_id = _strip_wecom_target(ctx.get("OriginatingTo") or ctx.get("To"))
    sender_id = str(ctx.get("SenderId") or _strip_wecom_target(ctx.get("From")) or "")
    if not chat_id:
        chat_id = sender_id

    media_paths = ctx.get("MediaPaths")
    if not isinstance(media_paths, list):
        media_paths = [ctx.get("MediaPath")] if ctx.get("MediaPath") else []
    media_filenames = ctx.get("MediaFilenames")
    if not isinstance(media_filenames, list):
        media_filenames = [ctx.get("MediaFilename")] if ctx.get("MediaFilename") else []
    attachments = []
    for index, path in enumerate(media_paths):
        if not path:
            continue
        url = str(path)
        if "://" not in url:
            url = f"file://{url}"
        filename = ""
        if index < len(media_filenames):
            filename = str(media_filenames[index] or "").strip()
        attachments.append({
            "kind": "file",
            "url": url,
            "filename": filename or url.rsplit("/", 1)[-1],
            "mime": ctx.get("MediaType"),
        })

    raw = dict(ctx)
    if attachments:
        raw["_wecom_new_payload"] = {
            "msg_type": "mixed",
            "text": str(ctx.get("Body") or ""),
            "attachments": attachments,
        }

    return InboundMessage(
        channel_id="wecom_new",
        account_id=str(ctx.get("AccountId") or "default"),
        message_id=str(ctx.get("MessageSid") or ""),
        sender_id=sender_id,
        sender_name=str(ctx.get("SenderName") or "") or None,
        chat_id=chat_id,
        chat_type=chat_type,
        text=str(ctx.get("Body") or ""),
        media_url=attachments[0]["url"] if attachments else None,
        mentioned=chat_type is ChatType.GROUP,
        raw=raw,
    )


def _coerce_epoch_ms(raw: Any) -> str:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return str(int(time.time() * 1000))
    if value <= 0:
        return str(int(time.time() * 1000))
    if value < 10_000_000_000:
        value *= 1000
    return str(int(value))


def _review_text_from_replies(replies: list[dict[str, Any]]) -> str:
    return "\n\n".join(
        str(reply.get("text") or "").strip()
        for reply in replies
        if str(reply.get("text") or "").strip()
    )


def _review_paths_from_values(*values: Any) -> str:
    paths: list[str] = []
    seen: set[str] = set()
    for value in values:
        candidates = value if isinstance(value, list) else [value]
        for item in candidates:
            path = str(item or "").strip()
            if path and path not in seen:
                seen.add(path)
                paths.append(path)
    return "\n".join(paths)


def _resolve_wecom_new_review_webhook_url(channel_config: Any) -> str:
    for key in ("reviewWebhookUrl", "reviewWebhookURL"):
        value = channel_config.get_extra(key) if channel_config is not None else None
        if value:
            return str(value).strip()
    return os.getenv("FLOCKS_WECOM_NEW_REVIEW_WEBHOOK_URL", "").strip()


async def _post_wecom_new_review_record(
    webhook_url: str,
    values: dict[str, str],
) -> None:
    import aiohttp

    payload = {
        "schema": _WECOM_NEW_REVIEW_SCHEMA,
        "add_records": [{"values": values}],
    }
    timeout = aiohttp.ClientTimeout(total=5)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(webhook_url, json=payload) as resp:
            body = await resp.text()
            if resp.status >= 400:
                raise RuntimeError(f"HTTP {resp.status}: {body[:300]}")
            try:
                data = await resp.json(content_type=None)
            except Exception:
                data = {}
            if isinstance(data, dict) and data.get("errcode") not in (None, 0):
                raise RuntimeError(str(data))


def _schedule_wecom_new_review_record(
    *,
    channel_config: Any,
    ctx: dict[str, Any],
    msg: Any,
    replies: list[dict[str, Any]],
    inbound_attachment_paths: list[str] | None = None,
) -> None:
    webhook_url = _resolve_wecom_new_review_webhook_url(channel_config)
    if not webhook_url:
        return

    values = {
        "f04Gwj": msg.mention_text or msg.text,
        "fhIosl": _review_text_from_replies(replies),
        "f4iZhP": _review_paths_from_values(
            inbound_attachment_paths,
            ctx.get("MediaPaths") if not inbound_attachment_paths else None,
            ctx.get("MediaPath") if not inbound_attachment_paths else None,
            ctx.get("MediaUrls") if not inbound_attachment_paths else None,
            ctx.get("MediaUrl") if not inbound_attachment_paths else None,
        ),
        "f8go0U": _review_paths_from_values(
            *[reply.get("mediaUrl") or reply.get("media_url") for reply in replies],
        ),
        "f60SN8": _coerce_epoch_ms(ctx.get("Timestamp") or ctx.get("CreateTime")),
        "fb7dU8": msg.sender_name or msg.sender_id,
    }

    async def _run() -> None:
        try:
            await _post_wecom_new_review_record(webhook_url, values)
        except Exception as e:
            log.warning("channel.wecom_new.review_record_failed", {
                "error": f"{type(e).__name__}: {e}",
                "message_id": msg.message_id,
            })

    asyncio.create_task(_run())


@router.post("/wecom_new/openclaw/dispatch")
async def wecom_new_openclaw_dispatch(req: OpenClawDispatchRequest):
    from flocks.agent.registry import Agent
    from flocks.channel.inbound.dispatcher import (
        InboundDispatcher,
        _resolve_session_model,
    )
    from flocks.channel.inbound.session_binding import SessionBindingService
    from flocks.session.idle_retirement import retire_if_idle
    from flocks.session.session import Session

    msg = _openclaw_ctx_to_inbound(req.ctx)
    dispatcher = InboundDispatcher()
    channel_config = await dispatcher._get_channel_config("wecom_new")
    default_agent = channel_config.default_agent or await Agent.default_agent()
    binding_service = SessionBindingService()
    binding = await binding_service.resolve_or_create(
        msg,
        default_agent=default_agent,
        directory=channel_config.workspace_dir,
    )

    bound_session = await Session.get_by_id(binding.session_id)
    if bound_session is not None:
        async def _schedule_idle_retirement_summary(retired_session) -> None:
            from flocks.server.routes.session import _run_session_compaction, _schedule_background_coro

            _schedule_background_coro(
                _run_session_compaction(
                    retired_session.id,
                    auto=True,
                    focus_instruction=(
                        "Summarize this idle channel session for closure. Preserve only durable decisions, "
                        "technical facts, user preferences, and follow-up items worth future recall."
                    ),
                ),
                session_id=retired_session.id,
                action="channel.wecom_new.idle_retirement.summary",
            )

        retirement = await retire_if_idle(
            bound_session,
            summary_scheduler=_schedule_idle_retirement_summary,
            source_metadata={
                "sourceType": "wecom_new",
                "entrypoint": "openclaw_dispatch",
                "accountID": msg.account_id,
                "chatID": msg.chat_id,
                "chatType": msg.chat_type.value,
                "senderID": msg.sender_id,
                "messageID": msg.message_id,
            },
        )
        if retirement is not None:
            binding = await binding_service.rebind(
                msg,
                retirement.active_session.id,
                agent_id=binding.agent_id or default_agent,
            )
            log.info("channel.openclaw_dispatch.idle_retired", {
                "session": retirement.retired_session.id,
                "new_session": retirement.active_session.id,
                "idle_ms": retirement.idle_ms,
            })

    lock = dispatcher._get_session_lock(binding.session_id)
    callbacks = _OpenClawCollectCallbacks()
    inbound_attachment_paths: list[str] = []

    async with lock:
        resolved_model = await _resolve_session_model(binding.session_id)
        inbound_attachment_paths = await dispatcher._append_user_message(
            binding.session_id,
            msg.mention_text or msg.text,
            msg,
            channel_config,
            model=resolved_model,
            agent=binding.agent_id,
        )
        try:
            from flocks.session.session_loop import SessionLoop
            result = await SessionLoop.run(
                session_id=binding.session_id,
                agent_name=binding.agent_id,
                callbacks=callbacks.to_loop_callbacks(),
            )
            if result.last_message:
                callbacks.replies.extend(
                    await _extract_openclaw_message_replies(
                        binding.session_id,
                        result.last_message,
                    ),
                )
        except Exception as e:
            log.error("channel.openclaw_dispatch.agent_error", {
                "session": binding.session_id,
                "error": str(e),
            })
            await callbacks.on_error(f"{type(e).__name__}: {e}")

    _schedule_wecom_new_review_record(
        channel_config=channel_config,
        ctx=req.ctx,
        msg=msg,
        replies=callbacks.replies,
        inbound_attachment_paths=inbound_attachment_paths,
    )

    return {
        "ok": True,
        "sessionId": binding.session_id,
        "replies": callbacks.replies,
    }


async def _extract_openclaw_message_replies(
    session_id: str,
    message: Any,
) -> list[dict[str, Any]]:
    try:
        from flocks.session.message import Message
        msg_id = getattr(message, "id", None)
        if not msg_id:
            return []
        parts = await Message.parts(msg_id, session_id=session_id)
        text_parts = [
            p.text for p in parts
            if hasattr(p, "text") and p.text and getattr(p, "type", None) == "text"
        ]
        replies: list[dict[str, Any]] = []
        text = "\n".join(text_parts)
        if text:
            replies.append({"text": text})
        for part in parts:
            if getattr(part, "type", None) != "file":
                continue
            media_url = str(getattr(part, "url", "") or "").strip()
            if media_url:
                replies.append({"mediaUrl": media_url})
        return replies
    except Exception as e:
        log.warning("channel.openclaw_dispatch.extract_replies_failed", {
            "session": session_id,
            "error": f"{type(e).__name__}: {e}",
        })
        return []


@router.post("/send")
async def channel_send(req: SendMessageRequest):
    """向指定渠道的指定目标（chat_id / user_id）主动发送消息。"""
    from flocks.channel.base import OutboundContext
    from flocks.channel.outbound.deliver import OutboundDelivery

    out_ctx = OutboundContext(
        channel_id=req.channel_id,
        account_id=req.account_id,
        to=req.to,
        text=req.text,
        media_url=req.media_url,
        reply_to_id=req.reply_to_id,
    )
    results = await OutboundDelivery.deliver(out_ctx, session_id=req.session_id)
    failed = [r for r in results if not r.success]
    if failed:
        raise HTTPException(status_code=502, detail=failed[0].error)
    return {
        "ok": True,
        "message_ids": [r.message_id for r in results if r.message_id],
    }


@router.post("/session-send")
async def channel_session_send(req: SessionSendRequest):
    """通过 session_id 查找绑定的渠道，向该渠道发送消息。"""
    from flocks.channel.base import OutboundContext
    from flocks.channel.inbound.session_binding import SessionBindingService
    from flocks.channel.outbound.deliver import OutboundDelivery

    svc = SessionBindingService()
    matched = await svc.get_bindings_by_session(req.session_id)
    normalized_channel_type = _normalize_channel_type(req.channel_type)

    if not matched:
        raise HTTPException(
            status_code=404,
            detail=f"未找到 session '{req.session_id}' 的渠道绑定",
        )

    if normalized_channel_type:
        matched = [b for b in matched if b.channel_id == normalized_channel_type]
        if not matched:
            raise HTTPException(
                status_code=404,
                detail=f"session '{req.session_id}' 未绑定渠道 '{req.channel_type}'",
            )

    all_results = []
    errors = []
    for binding in matched:
        out_ctx = OutboundContext(
            channel_id=binding.channel_id,
            account_id=binding.account_id,
            to=binding.chat_id,
            text=req.text,
            media_url=req.media_url,
        )
        results = await OutboundDelivery.deliver(out_ctx, session_id=req.session_id)
        all_results.extend(results)
        for r in results:
            if not r.success:
                errors.append(f"[{binding.channel_id}] {r.error}")

    if errors:
        raise HTTPException(status_code=502, detail="; ".join(errors))

    return {
        "ok": True,
        "message_ids": [r.message_id for r in all_results if r.message_id],
        "channels": list({b.channel_id for b in matched}),
    }


@router.post("/{channel_id}/webhook")
async def channel_webhook(channel_id: str, request: Request):
    """
    Receive a platform webhook callback.

    Platforms (Feishu, WeCom, …) POST events to this endpoint in
    webhook mode.  The plugin is responsible for URL verification,
    signature validation, and event parsing.
    """
    plugin = default_registry.get(channel_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Channel '{channel_id}' not found")

    body = await request.body()
    headers = dict(request.headers)

    result = await plugin.handle_webhook(body, headers)
    if isinstance(result, dict) and isinstance(result.get("status_code"), int):
        status_code = int(result["status_code"])
        payload = {k: v for k, v in result.items() if k != "status_code"}
        return JSONResponse(status_code=status_code, content=payload)
    return result if result else {"ok": True}


@router.get("/status")
async def channel_status():
    """Return health status of all running channels."""
    statuses = default_manager.get_status()
    return {
        channel_id: status.to_dict()
        for channel_id, status in statuses.items()
    }


@router.get("/{channel_id}/status")
async def single_channel_status(channel_id: str):
    """Return health status of a single channel."""
    statuses = default_manager.get_status()
    status = statuses.get(channel_id)
    if not status:
        raise HTTPException(status_code=404, detail=f"Channel '{channel_id}' not running")
    return {"channel_id": channel_id, **status.to_dict()}


@router.get("/list")
async def list_channels():
    """List all registered channel plugins."""
    default_registry.init()
    channels = default_registry.list_channels()
    return [
        {
            "id": ch.meta().id,
            "label": ch.meta().label,
            "aliases": ch.meta().aliases,
            "capabilities": {
                "chat_types": [ct.value for ct in ch.capabilities().chat_types],
                "media": ch.capabilities().media,
                "threads": ch.capabilities().threads,
                "reactions": ch.capabilities().reactions,
                "edit": ch.capabilities().edit,
                "rich_text": ch.capabilities().rich_text,
            },
            "running": default_manager.is_channel_running(ch.meta().id),
        }
        for ch in channels
    ]


@router.post("/{channel_id}/record-inbound")
async def record_inbound(channel_id: str):
    """Notify the gateway that a message was received on this channel.

    Used by out-of-process bridges (e.g. DingTalk's runner.ts) that bypass the
    InboundDispatcher so that last_message_at is updated on the plugin status.
    """
    default_manager.record_message(channel_id)
    return {"ok": True}


class BindSessionRequest(BaseModel):
    """Body for ``POST /api/channel/{channel_id}/bind``."""
    session_id: str
    chat_id: str
    chat_type: str = "direct"  # "direct" | "group"
    account_id: Optional[str] = "default"
    thread_id: Optional[str] = None
    agent_id: Optional[str] = None


@router.post("/{channel_id}/bind")
async def bind_session(channel_id: str, req: BindSessionRequest):
    """Register a (channel, conversation) → session mapping in ``channel_bindings``.

    For Feishu/WeCom/Telegram this row is written automatically inside
    ``InboundDispatcher`` → ``SessionBindingService.resolve_or_create``.  Out-
    of-process bridges (e.g. DingTalk's ``runner.ts``) create their Flocks
    session on their own and must call this endpoint after each session
    creation so that ``channel_message`` / ``POST /session-send`` can route
    outbound replies back.

    Idempotent — re-binding the same conversation key replaces the prior row.
    """
    from flocks.channel.base import ChatType
    from flocks.channel.inbound.session_binding import SessionBindingService

    # Conversation-level bindings only — CHANNEL-broadcast style targets
    # (e.g. Telegram channels) are not addressable by a single chat reply
    # and would never be a legitimate ``channel_message`` destination.
    if req.chat_type not in ("direct", "group"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid chat_type '{req.chat_type}', expected 'direct' or 'group'",
        )
    chat_type = ChatType(req.chat_type)

    # Defense-in-depth: some out-of-process bridges build composite
    # session-isolation keys like ``<conversationId>:<senderId>`` for
    # per-sender group sessions (e.g. DingTalk's ``groupSessionScope=
    # group_sender``).  Such keys are NOT valid outbound targets — they
    # would be fed as ``openConversationId`` to the platform API and fail
    # to deliver.  Reject them here so the bug can never regress silently
    # into the bindings table.
    if chat_type is ChatType.GROUP and ":" in req.chat_id:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid group chat_id '{req.chat_id}': contains ':', which "
                "looks like a session-isolation composite (e.g. "
                "'<conversationId>:<senderId>').  Pass the bare platform "
                "conversation id (e.g. DingTalk openConversationId)."
            ),
        )

    svc = SessionBindingService()
    try:
        binding = await svc.bind_session(
            session_id=req.session_id,
            channel_id=channel_id,
            account_id=req.account_id or "default",
            chat_id=req.chat_id,
            chat_type=chat_type,
            thread_id=req.thread_id,
            agent_id=req.agent_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return {
        "ok": True,
        "channel_id": binding.channel_id,
        "session_id": binding.session_id,
        "chat_id": binding.chat_id,
        "chat_type": binding.chat_type.value,
    }


@router.post("/{channel_id}/restart")
async def restart_channel(channel_id: str):
    """Restart a single channel connection with the latest config.

    Fires the restart in the background and returns immediately so that
    long WebSocket disconnect sequences do not block the HTTP response.
    Stops the current long-connection (if any) and re-connects using the
    freshly saved configuration.
    """
    import asyncio

    plugin = default_registry.get(channel_id)
    if not plugin:
        raise HTTPException(
            status_code=404, detail=f"Channel '{channel_id}' not found"
        )

    asyncio.create_task(default_manager.restart_channel(channel_id))
    return {"ok": True, "channel_id": channel_id}


@router.post("/restart-all")
async def restart_all_channels():
    """Restart all enabled channel connections (background, returns immediately)."""
    import asyncio

    async def _do():
        await default_manager.stop_all()
        await default_manager.start_all()

    asyncio.create_task(_do())
    return {"ok": True}


# ---------------------------------------------------------------------------
# Telegram pairing
# ---------------------------------------------------------------------------

class TelegramPairRequest(BaseModel):
    code: str


def _append_telegram_allow_from(user_id: str) -> None:
    """Atomically add *user_id* to channels.telegram.allowFrom in flocks.json.

    Creates the key (as an empty list) if it is absent, then appends the ID
    (deduplicated).  Uses ConfigWriter so the write is atomic and the cache is
    cleared automatically.
    """
    from flocks.config.config_writer import ConfigWriter  # local import — avoids circular deps

    data = ConfigWriter._read_raw()
    channels = data.setdefault("channels", {})
    telegram = channels.setdefault("telegram", {})

    allow_from: list = telegram.get("allowFrom", [])
    str_id = str(user_id)
    if str_id not in [str(x) for x in allow_from]:
        allow_from = list(allow_from) + [str_id]
    telegram["allowFrom"] = allow_from

    ConfigWriter._write_raw(data)
    log.info("telegram.pairing.config_saved", {"user_id": str_id})


@router.post("/telegram/pair")
async def telegram_pair(req: TelegramPairRequest):
    """
    Verify a Telegram pairing code.

    On success, the user_id is immediately persisted to channels.telegram.allowFrom
    in flocks.json, so no manual save is required in the UI.
    """
    plugin = default_registry.get("telegram")
    if not plugin:
        raise HTTPException(status_code=404, detail="Telegram channel plugin not loaded")

    # Duck-type access to pairing store (avoids importing the plugin module here)
    get_store = getattr(plugin, "get_pairing_store", None)
    if get_store is None:
        raise HTTPException(status_code=501, detail="Telegram plugin does not support pairing")

    store = get_store()
    entry = store.consume(req.code.strip().upper())
    if entry is None:
        raise HTTPException(status_code=400, detail="配对码无效或已过期")

    user_id = entry["user_id"]

    # Persist user_id to flocks.json immediately
    config_saved = False
    try:
        import asyncio
        await asyncio.get_event_loop().run_in_executor(None, _append_telegram_allow_from, user_id)
        config_saved = True
    except Exception as exc:
        log.warning("telegram.pairing.config_save_failed", {"error": str(exc)})

    # Send a confirmation message back to the Telegram user (best-effort, before restart)
    confirm = getattr(plugin, "confirm_pairing", None)
    if confirm is not None:
        import asyncio
        asyncio.create_task(confirm(entry))

    # Restart the channel so the new allowFrom takes effect immediately.
    # Schedule after a short delay so the confirmation message is sent first.
    if config_saved:
        import asyncio

        async def _delayed_restart() -> None:
            await asyncio.sleep(2)
            await default_manager.restart_channel("telegram")

        asyncio.create_task(_delayed_restart())
        log.info("telegram.pairing.channel_restart_scheduled", {"user_id": user_id})

    return {
        "ok": True,
        "user_id": user_id,
        "username": entry.get("username"),
    }
