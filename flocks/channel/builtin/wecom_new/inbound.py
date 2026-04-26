from __future__ import annotations

import re
from typing import Any

from flocks.channel.base import ChatType, InboundMessage

from flocks.channel.builtin.wecom_new.models import (
    WeComInboundAttachment,
    WeComInboundPayload,
)


def parse_frame(frame: dict[str, Any], config: dict[str, Any]) -> InboundMessage | None:
    body = frame.get("body", {})
    msg_type = str(body.get("msgtype", "") or "")
    if msg_type == "stream":
        return None

    payload = normalize_inbound_payload(body)
    if not payload.text and not payload.attachments:
        return None

    chat_type_raw = body.get("chattype", "single")
    chat_type = ChatType.GROUP if chat_type_raw == "group" else ChatType.DIRECT
    from_user = body.get("from", {}).get("userid", "")
    chat_id = body.get("chatid") or from_user
    text = payload.text
    if chat_type == ChatType.GROUP:
        text = re.sub(r"@\S+", "", text).strip()

    first_media_url = next((a.url for a in payload.attachments if a.url), None)
    raw = dict(body)
    raw["_wecom_new_payload"] = {
        "msg_type": payload.msg_type,
        "text": payload.text,
        "attachments": [
            {
                "kind": item.kind,
                "url": item.url,
                "aes_key": item.aes_key,
                "filename": item.filename,
                "mime": item.mime,
            }
            for item in payload.attachments
        ],
        "quoted_text": payload.quoted_text,
        "quoted_attachments": [
            {
                "kind": item.kind,
                "url": item.url,
                "aes_key": item.aes_key,
                "filename": item.filename,
                "mime": item.mime,
            }
            for item in (payload.quoted_attachments or [])
        ],
    }

    return InboundMessage(
        channel_id="wecom_new",
        account_id=config.get("_account_id", "default"),
        message_id=body.get("msgid", ""),
        sender_id=from_user,
        chat_id=chat_id,
        chat_type=chat_type,
        text=text,
        media_url=first_media_url,
        mentioned=chat_type == ChatType.GROUP,
        raw=raw,
    )


def normalize_inbound_payload(body: dict[str, Any]) -> WeComInboundPayload:
    msg_type = str(body.get("msgtype", "") or "")

    if msg_type == "text":
        return WeComInboundPayload(
            msg_type=msg_type,
            text=str(body.get("text", {}).get("content", "") or ""),
            raw=body,
        )

    if msg_type in {"image", "file", "voice", "video"}:
        attachment = _attachment_from_block(msg_type, body.get(msg_type, {}))
        return WeComInboundPayload(
            msg_type=msg_type,
            text=_default_text_for_attachment(msg_type, attachment.filename),
            attachments=[attachment] if attachment else [],
            raw=body,
        )

    if msg_type == "mixed":
        return _normalize_mixed(body)

    return WeComInboundPayload(msg_type=msg_type, text="", raw=body)


def _normalize_mixed(body: dict[str, Any]) -> WeComInboundPayload:
    parts: list[str] = []
    attachments: list[WeComInboundAttachment] = []
    for item in body.get("mixed", {}).get("msg_item", []):
        item_type = str(item.get("msgtype", "") or "")
        if item_type == "text":
            text = str(item.get("text", {}).get("content", "") or "").strip()
            if text:
                parts.append(text)
            continue
        if item_type in {"image", "file", "voice", "video"}:
            attachment = _attachment_from_block(item_type, item.get(item_type, {}))
            if attachment:
                attachments.append(attachment)
                parts.append(_default_text_for_attachment(item_type, attachment.filename).replace("消息", ""))
    return WeComInboundPayload(
        msg_type="mixed",
        text=" ".join(part for part in parts if part).strip(),
        attachments=attachments,
        raw=body,
    )


def _attachment_from_block(kind: str, block: dict[str, Any]) -> WeComInboundAttachment | None:
    url = str(block.get("url", "") or "").strip() or None
    aes_key = str(block.get("aeskey", "") or "").strip() or None
    filename = str(block.get("filename", "") or "").strip() or None
    mime = str(block.get("mime", "") or "").strip() or None
    if not url and not filename and not aes_key:
        return None
    return WeComInboundAttachment(
        kind=kind,
        url=url,
        aes_key=aes_key,
        filename=filename,
        mime=mime,
    )


def _default_text_for_attachment(kind: str, filename: str | None) -> str:
    if kind == "image":
        return "[图片消息]"
    if kind == "voice":
        return "[语音消息]"
    if kind == "video":
        return f"[视频消息: {filename}]" if filename else "[视频消息]"
    if kind == "file":
        return f"[文件消息: {filename}]" if filename else "[文件消息]"
    return ""
