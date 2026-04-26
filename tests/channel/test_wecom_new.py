from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from flocks.channel.base import ChatType, InboundMessage, OutboundContext
from flocks.channel.builtin.wecom_new.inbound import normalize_inbound_payload, parse_frame
from flocks.channel.builtin.wecom_new.channel import WeComNewChannel
from flocks.channel.builtin.wecom_new.status_feedback import (
    ACK_TEXT,
    FAILED_TEXT_PREFIX,
    SLOW_TASK_TEXT,
    WeComStatusFeedback,
)
from flocks.channel.builtin.wecom_new.inbound_media import download_inbound_media


@pytest.mark.asyncio
async def test_download_inbound_media_uses_structured_attachment_fields(tmp_path: Path):
    class DummyApiClient:
        def __init__(self, *_args, **_kwargs):
            self._client = None

        async def download_file_raw(self, media_url: str):
            assert media_url == "https://example.com/a.pdf"
            return {"buffer": b"encrypted", "filename": None}

    class DummySdk:
        WeComApiClient = DummyApiClient

        @staticmethod
        def decrypt_file(buffer: bytes, aes_key: str) -> bytes:
            assert buffer == b"encrypted"
            assert aes_key == "secret-key"
            return b"decrypted"

    msg = InboundMessage(
        channel_id="wecom_new",
        account_id="acc1",
        message_id="msg1",
        sender_id="u1",
        chat_id="u1",
        chat_type=ChatType.DIRECT,
        media_url="https://example.com/a.pdf",
        raw={
            "_wecom_new_payload": {
                "attachments": [
                    {
                        "kind": "file",
                        "url": "https://example.com/a.pdf",
                        "aes_key": "secret-key",
                        "filename": "report.pdf",
                    }
                ]
            }
        },
    )

    import flocks.channel.builtin.wecom_new.inbound_media as inbound_media_mod

    with patch.object(inbound_media_mod.importlib, "import_module", return_value=DummySdk), patch.object(
        inbound_media_mod,
        "_media_storage_dir",
        return_value=tmp_path,
    ):
        media = await download_inbound_media(msg, {})

    assert media is not None
    assert media.filename == "msg1.pdf"
    assert media.mime == "application/pdf"
    assert media.source["channel"] == "wecom_new"
    assert Path(media.url.replace("file://", "")).read_bytes() == b"decrypted"


@pytest.mark.asyncio
async def test_dispatcher_uses_wecom_new_inbound_media_handler(monkeypatch):
    from flocks.channel.inbound.dispatcher import _download_channel_media

    msg = InboundMessage(
        channel_id="wecom_new",
        account_id="acc1",
        message_id="msg2",
        sender_id="u1",
        chat_id="u1",
        chat_type=ChatType.DIRECT,
        media_url="https://example.com/a.pdf",
    )

    expected = object()
    monkeypatch.setattr(
        "flocks.channel.builtin.wecom_new.inbound_media.download_inbound_media",
        AsyncMock(return_value=expected),
    )

    result = await _download_channel_media(msg, {})
    assert result is expected


def test_normalize_inbound_payload_text_message():
    payload = normalize_inbound_payload({
        "msgtype": "text",
        "text": {"content": "hello wecom_new"},
    })

    assert payload.msg_type == "text"
    assert payload.text == "hello wecom_new"
    assert payload.attachments == []


def test_normalize_inbound_payload_file_message():
    payload = normalize_inbound_payload({
        "msgtype": "file",
        "file": {
            "url": "https://example.com/report.pdf",
            "aeskey": "k1",
            "filename": "report.pdf",
        },
    })

    assert payload.msg_type == "file"
    assert payload.text == "[文件消息: report.pdf]"
    assert len(payload.attachments) == 1
    assert payload.attachments[0].url == "https://example.com/report.pdf"
    assert payload.attachments[0].aes_key == "k1"
    assert payload.attachments[0].filename == "report.pdf"


def test_normalize_inbound_payload_mixed_message_collects_text_and_attachments():
    payload = normalize_inbound_payload({
        "msgtype": "mixed",
        "mixed": {
            "msg_item": [
                {"msgtype": "text", "text": {"content": "请分析附件"}},
                {
                    "msgtype": "file",
                    "file": {
                        "url": "https://example.com/a.pdf",
                        "aeskey": "k1",
                        "filename": "a.pdf",
                    },
                },
                {
                    "msgtype": "image",
                    "image": {
                        "url": "https://example.com/img.png",
                        "aeskey": "k2",
                        "filename": "img.png",
                    },
                },
            ]
        },
    })

    assert payload.msg_type == "mixed"
    assert payload.text == "请分析附件 [文件: a.pdf] [图片]"
    assert len(payload.attachments) == 2
    assert payload.attachments[0].kind == "file"
    assert payload.attachments[1].kind == "image"


def test_parse_frame_builds_inbound_message_with_structured_payload():
    msg = parse_frame(
        {
            "body": {
                "msgid": "wx-frame-1",
                "msgtype": "mixed",
                "chattype": "group",
                "chatid": "group-1",
                "from": {"userid": "user-1"},
                "mixed": {
                    "msg_item": [
                        {"msgtype": "text", "text": {"content": "@bot 请分析"}},
                        {
                            "msgtype": "file",
                            "file": {
                                "url": "https://example.com/a.pdf",
                                "aeskey": "k1",
                                "filename": "a.pdf",
                            },
                        },
                    ]
                },
            }
        },
        {"_account_id": "acc1"},
    )

    assert msg is not None
    assert msg.channel_id == "wecom_new"
    assert msg.account_id == "acc1"
    assert msg.message_id == "wx-frame-1"
    assert msg.chat_type == ChatType.GROUP
    assert msg.chat_id == "group-1"
    assert msg.sender_id == "user-1"
    assert msg.mentioned is True
    assert msg.media_url == "https://example.com/a.pdf"
    assert msg.text == "请分析 [文件: a.pdf]"
    assert msg.raw["_wecom_new_payload"]["attachments"][0]["filename"] == "a.pdf"


@pytest.mark.asyncio
async def test_status_feedback_sends_ack_and_slow_task_once():
    sent: list[str] = []

    async def _send_text(text: str) -> None:
        sent.append(text)

    feedback = WeComStatusFeedback(send_text=_send_text, slow_task_delay_seconds=0.01)
    await feedback.send_ack()
    await feedback._slow_task

    assert sent == [ACK_TEXT, SLOW_TASK_TEXT]


@pytest.mark.asyncio
async def test_status_feedback_complete_cancels_slow_task():
    sent: list[str] = []

    async def _send_text(text: str) -> None:
        sent.append(text)

    feedback = WeComStatusFeedback(send_text=_send_text, slow_task_delay_seconds=0.2)
    await feedback.send_ack()
    await feedback.complete()

    assert sent == [ACK_TEXT]
    assert feedback._slow_task is None


@pytest.mark.asyncio
async def test_status_feedback_send_failed_cancels_and_reports_reason():
    sent: list[str] = []

    async def _send_text(text: str) -> None:
        sent.append(text)

    feedback = WeComStatusFeedback(send_text=_send_text, slow_task_delay_seconds=0.2)
    await feedback.send_ack()
    await feedback.send_failed("timeout")

    assert sent == [ACK_TEXT, f"{FAILED_TEXT_PREFIX}timeout"]


@pytest.mark.asyncio
async def test_wecom_new_send_text_reuses_cached_stream_id(monkeypatch):
    channel = WeComNewChannel()
    channel._config = {}

    class DummyWsClient:
        def __init__(self):
            self.calls = []

        async def reply_stream(self, frame, stream_id, text, finish):
            self.calls.append((frame, stream_id, text, finish))

    ws = DummyWsClient()
    channel._ws_client = ws
    channel._frame_cache["msg1"] = {"body": {"msgid": "msg1"}}
    channel._stream_cache["msg1"] = "stream-123"

    result = await channel.send_text(
        OutboundContext(channel_id="wecom_new", to="u1", text="final", reply_to_id="msg1")
    )

    assert result.success is True
    assert ws.calls == [({"body": {"msgid": "msg1"}}, "stream-123", "final", True)]
    assert "msg1" not in channel._stream_cache


@pytest.mark.asyncio
async def test_wecom_new_message_handler_sends_placeholder_with_finish_false(monkeypatch):
    channel = WeComNewChannel()
    channel._config = {"slowTaskDelaySeconds": 30}

    class DummyWsClient:
        def __init__(self):
            self.calls = []

        async def reply_stream(self, frame, stream_id, text, finish):
            self.calls.append((stream_id, text, finish))

    ws = DummyWsClient()
    channel._ws_client = ws

    monkeypatch.setattr(
        "wecom_aibot_sdk.generate_req_id",
        lambda _prefix: "stream-ack-1",
    )

    async def on_message(_msg):
        return None

    handler = channel._make_message_handler(on_message)
    handler({
        "body": {
            "msgid": "m1",
            "msgtype": "text",
            "from": {"userid": "u1"},
            "text": {"content": "hello"},
        }
    })

    await asyncio.sleep(0.05)

    assert ws.calls[0] == ("stream-ack-1", ACK_TEXT, False)
    assert channel._stream_cache["m1"] == "stream-ack-1"
