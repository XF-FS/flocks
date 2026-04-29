"""
WeCom_new inbound media download helpers.

Uses the same SDK download/decrypt path as the legacy WeCom channel, but reads
attachment metadata from the v2 structured payload and stores files under the
dedicated wecom_new workspace root.
"""

from __future__ import annotations

import datetime
import mimetypes
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse

from flocks.channel.base import InboundMessage
from flocks.channel.builtin.wecom.inbound_media import (
    DownloadedInboundMedia,
    _DEFAULT_MAX_INBOUND_MEDIA_BYTES,
    _close_api_client,
    _download_file_limited,
    _filename_from_content_disposition,
    _guess_mime_from_ext,
    _max_size_error,
    _sanitize_filename,
    WeComInboundMediaTooLarge,
)
from flocks.utils.log import Log
from flocks.workspace.manager import WorkspaceManager

import importlib

log = Log.create(service="channel.wecom_new.media")


def _media_storage_dir(account_id: str) -> Path:
    workspace = WorkspaceManager.get_instance()
    workspace.ensure_dirs()
    return (
        workspace.get_workspace_dir()
        / "uploads"
        / "wecom_new"
        / account_id
        / datetime.date.today().isoformat()
    )


def _structured_attachment(msg: InboundMessage) -> dict | None:
    raw = msg.raw if isinstance(msg.raw, dict) else {}
    payload = raw.get("_wecom_new_payload") if isinstance(raw, dict) else None
    if not isinstance(payload, dict):
        return None
    target_url = getattr(msg, "media_url", None)
    for item in payload.get("attachments", []) or []:
        if not isinstance(item, dict):
            continue
        if target_url and item.get("url") != target_url:
            continue
        return item
    return None


def _guess_filename(msg: InboundMessage, media_url: str, cd_filename: Optional[str] = None) -> str:
    attachment = _structured_attachment(msg) or {}
    filename = str(attachment.get("filename", "") or "").strip()
    if filename:
        return _sanitize_filename(filename)
    if cd_filename:
        return _sanitize_filename(cd_filename)
    tail = media_url.rsplit("/", 1)[-1].strip()
    if tail and "." in tail:
        return _sanitize_filename(tail)
    msg_id = msg.message_id or "unknown"
    return _sanitize_filename(f"file_{msg_id[:12]}")


def _landing_filename(msg: InboundMessage, guessed_filename: str) -> str:
    suffix = Path(guessed_filename).suffix
    if not suffix:
        guessed_mime = _guess_mime_from_ext(guessed_filename)
        suffix = mimetypes.guess_extension(guessed_mime) if guessed_mime else ""
    msg_id = msg.message_id or "unknown"
    original_name = Path(guessed_filename).name
    if original_name:
        return _sanitize_filename(f"[{msg_id}]_{original_name}")
    return _sanitize_filename(f"[{msg_id}]{suffix or ''}")


def _extract_aes_key(msg: InboundMessage) -> Optional[str]:
    attachment = _structured_attachment(msg) or {}
    key = str(attachment.get("aes_key", "") or "").strip()
    return key or None


def _local_media_path(media_url: str) -> Path | None:
    parsed = urlparse(media_url)
    if parsed.scheme == "file":
        return Path(unquote(parsed.path))
    if not parsed.scheme:
        path = Path(media_url)
        if path.is_absolute():
            return path
    return None


async def download_inbound_media(
    msg: InboundMessage,
    config: dict,
    *,
    max_bytes: int = _DEFAULT_MAX_INBOUND_MEDIA_BYTES,
) -> Optional[DownloadedInboundMedia]:
    del config
    media_url = msg.media_url
    if not media_url:
        return None

    aes_key = _extract_aes_key(msg)
    api_client = None
    local_path = _local_media_path(media_url)
    try:
        if local_path:
            buffer = local_path.read_bytes()
            cd_filename = local_path.name
            if len(buffer) > max_bytes:
                raise _max_size_error(max_bytes)
        else:
            sdk = importlib.import_module("wecom_aibot_sdk")
            api_client = sdk.WeComApiClient(log, timeout=30000)
            buffer, cd_filename = await _download_file_limited(api_client, media_url, max_bytes)

        if aes_key and not local_path:
            try:
                buffer = sdk.decrypt_file(buffer, aes_key)
            except Exception as e:
                log.warning("wecom_new.media.decrypt_failed", {
                    "url": media_url[:200],
                    "message_id": msg.message_id,
                    "error": str(e),
                })
                return None
            if len(buffer) > max_bytes:
                raise _max_size_error(max_bytes)

    except ImportError:
        log.warning("wecom_new.media.sdk_not_available")
        return None

    except WeComInboundMediaTooLarge as e:
        log.warning("wecom_new.media.file_too_large", {
            "url": media_url[:200],
            "message_id": msg.message_id,
            "error": str(e),
        })
        return None

    except Exception as e:
        log.warning("wecom_new.media.download_failed", {
            "url": media_url[:200],
            "message_id": msg.message_id,
            "error": str(e),
        })
        return None

    finally:
        if api_client is not None:
            await _close_api_client(api_client)

    original_filename = _guess_filename(msg, media_url, cd_filename)
    filename = _landing_filename(msg, original_filename)

    mime = _guess_mime_from_ext(original_filename) or _guess_mime_from_ext(filename) or "application/octet-stream"
    storage_dir = _media_storage_dir(msg.account_id or "default")
    storage_dir.mkdir(parents=True, exist_ok=True)
    file_path = storage_dir / filename
    file_path.write_bytes(buffer)

    return DownloadedInboundMedia(
        filename=filename,
        mime=mime,
        url=file_path.resolve().as_uri(),
        source={
            "channel": "wecom_new",
            "account_id": msg.account_id,
            "message_id": msg.message_id,
            "media_url": msg.media_url,
        },
    )
