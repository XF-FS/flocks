from __future__ import annotations

from typing import Any

from flocks.channel.base import DeliveryResult, OutboundContext


async def send_text(
    ws_client: Any,
    frame_cache: dict[str, Any],
    ctx: OutboundContext,
    *,
    stream_id: str | None = None,
) -> DeliveryResult:
    if not ws_client:
        return DeliveryResult(
            channel_id="wecom_new",
            message_id="",
            success=False,
            error="WebSocket not connected",
        )

    from wecom_aibot_sdk import generate_req_id

    frame = frame_cache.get(ctx.reply_to_id) if ctx.reply_to_id else None
    if frame:
        effective_stream_id = stream_id or generate_req_id("stream")
        await ws_client.reply_stream(frame, effective_stream_id, ctx.text, True)
    else:
        await ws_client.send_message(ctx.to, {
            "msgtype": "markdown",
            "markdown": {"content": ctx.text},
        })
    return DeliveryResult(channel_id="wecom_new", message_id="", chat_id=ctx.to)


async def send_media(
    ws_client: Any,
    frame_cache: dict[str, Any],
    ctx: OutboundContext,
    *,
    stream_id: str | None = None,
) -> DeliveryResult:
    if not ws_client:
        return DeliveryResult(
            channel_id="wecom_new",
            message_id="",
            success=False,
            error="WebSocket not connected",
        )
    if not ctx.media_url:
        return await send_text(ws_client, frame_cache, ctx, stream_id=stream_id)

    from flocks.channel.builtin.wecom.media import prepare_wecom_media

    media = await prepare_wecom_media(ctx.media_url)
    upload = await ws_client.upload_media(
        media.data,
        type=media.media_type,
        filename=media.filename,
    )
    media_id = upload.get("media_id", "")
    if not media_id:
        raise RuntimeError(f"WeCom media upload failed: {upload}")

    frame = frame_cache.get(ctx.reply_to_id) if ctx.reply_to_id else None
    if frame:
        sent = await ws_client.reply_media(
            frame,
            media.media_type,
            media_id,
            video_title=media.filename if media.media_type == "video" else None,
        )
    else:
        sent = await ws_client.send_media_message(
            ctx.to,
            media.media_type,
            media_id,
            video_title=media.filename if media.media_type == "video" else None,
        )

    if ctx.text:
        await send_text(
            ws_client,
            frame_cache,
            OutboundContext(**{**vars(ctx), "media_url": None}),
            stream_id=stream_id,
        )

    return DeliveryResult(
        channel_id="wecom_new",
        message_id=_extract_sent_message_id(sent),
        chat_id=ctx.to,
    )


def _extract_sent_message_id(frame: Any) -> str:
    if not isinstance(frame, dict):
        return ""
    body = frame.get("body") or {}
    if not isinstance(body, dict):
        return ""
    return str(body.get("msgid") or body.get("message_id") or "")
