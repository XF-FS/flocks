from __future__ import annotations

import asyncio
import json
import math
import uuid
from collections import OrderedDict
from typing import Any, Awaitable, Callable, Optional

from flocks.channel.base import (
    ChannelCapabilities,
    ChannelMeta,
    ChannelPlugin,
    ChatType,
    DeliveryResult,
    InboundMessage,
    OutboundContext,
)
from flocks.channel.builtin.wecom_new.bridge_client import OpenClawBridgeClient
from flocks.channel.builtin.wecom_new.inbound import parse_frame
from flocks.channel.builtin.wecom_new.outbound import send_media as send_media_v2
from flocks.channel.builtin.wecom_new.outbound import send_text as send_text_v2
from flocks.channel.builtin.wecom_new.status_feedback import WeComStatusFeedback
from flocks.utils.log import Log

log = Log.create(service="channel.wecom_new")

_FRAME_CACHE_MAX = 500
_DEFAULT_RECONNECT_TIMEOUT_SECONDS = 60.0


def _parse_reconnect_timeout_seconds(raw: Any) -> tuple[float, Optional[str]]:
    if raw is None:
        return _DEFAULT_RECONNECT_TIMEOUT_SECONDS, None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.0, "reconnectTimeoutSeconds must be a positive number"
    if not math.isfinite(value) or value <= 0:
        return 0.0, "reconnectTimeoutSeconds must be a positive number"
    return value, None


class WeComNewChannel(ChannelPlugin):
    def __init__(self) -> None:
        super().__init__()
        self._ws_client: Any = None
        self._frame_cache: OrderedDict[str, Any] = OrderedDict()
        self._stream_cache: OrderedDict[str, str] = OrderedDict()
        self._inflight_message_ids: OrderedDict[str, None] = OrderedDict()
        self._intentional_disconnect = False
        self._reconnect_timeout_seconds = _DEFAULT_RECONNECT_TIMEOUT_SECONDS
        self._reconnect_timeout_event = asyncio.Event()
        self._reconnect_watchdog_task: asyncio.Task[None] | None = None
        self._bridge: OpenClawBridgeClient | None = None

    def meta(self) -> ChannelMeta:
        return ChannelMeta(
            id="wecom_new",
            label="WeCom_new",
            aliases=["wecom-v2", "wecom_new_v2"],
            order=21,
        )

    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            chat_types=[ChatType.DIRECT, ChatType.GROUP],
            media=True,
            threads=False,
            reactions=False,
            edit=False,
            rich_text=True,
        )

    def validate_config(self, config: dict) -> Optional[str]:
        for key in ("botId", "secret"):
            if not config.get(key):
                return f"Missing required config: {key}"
        reconnect_timeout_seconds, error = _parse_reconnect_timeout_seconds(
            config.get("reconnectTimeoutSeconds")
        )
        if error:
            return error
        if "reconnectTimeoutSeconds" in config:
            config["reconnectTimeoutSeconds"] = reconnect_timeout_seconds
        if config.get("groupTrigger") == "all":
            config["groupTrigger"] = "mention"
        return None

    async def start(self, config, on_message, abort_event=None):
        self._config = config
        self._on_message = on_message
        self._intentional_disconnect = False
        self._reconnect_timeout_seconds, error = _parse_reconnect_timeout_seconds(
            config.get("reconnectTimeoutSeconds")
        )
        if error:
            raise ValueError(error)
        self._reconnect_timeout_event = asyncio.Event()
        self._cancel_reconnect_watchdog()

        bridge = OpenClawBridgeClient(config)
        if bridge.enabled:
            self._bridge = bridge
            await self._start_openclaw_bridge(bridge, on_message, abort_event)
            return

        try:
            from wecom_aibot_sdk import WSClient
        except ImportError:
            raise RuntimeError(
                "wecom-aibot-sdk not installed. Run `pip install wecom-aibot-sdk` to enable WeCom_new channel."
            )

        ws_url = config.get("websocketUrl", "")
        self._ws_client = WSClient(
            bot_id=config["botId"],
            secret=config["secret"],
            **({"ws_url": ws_url} if ws_url else {}),
            max_reconnect_attempts=-1,
            heartbeat_interval=30_000,
            scene=1,
            plug_version="1.0.0",
        )

        self._ws_client.on("authenticated", self._handle_authenticated)
        self._ws_client.on("disconnected", self._handle_disconnected)
        self._ws_client.on("reconnecting", self._handle_reconnecting)
        self._ws_client.on("error", self._handle_error)

        handler = self._make_message_handler(on_message)
        self._ws_client.on("message", handler)
        for event in ("message.text", "message.image", "message.mixed", "message.voice", "message.file"):
            self._ws_client.on(event, handler)

        log.info("wecom_new.ws.connecting", {"bot_id": config["botId"]})
        await self._ws_client.connect()
        try:
            await self._wait_until_stopped(abort_event)
        finally:
            await self._disconnect_ws_client()

    async def stop(self) -> None:
        if self._bridge:
            await self._disconnect_bridge()
        await self._disconnect_ws_client()

    async def send_text(self, ctx: OutboundContext) -> DeliveryResult:
        try:
            if self._bridge:
                frame = self._frame_cache.get(ctx.reply_to_id) if ctx.reply_to_id else None
                result = await self._bridge.send_text(
                    ctx,
                    frame=frame,
                    stream_id=self._stream_cache.pop(ctx.reply_to_id, None) if ctx.reply_to_id else None,
                )
                self.record_message()
                return result
            result = await send_text_v2(
                self._ws_client,
                self._frame_cache,
                ctx,
                stream_id=self._stream_cache.pop(ctx.reply_to_id, None) if ctx.reply_to_id else None,
            )
            self.record_message()
            return result
        except Exception as e:
            retryable = "timeout" in str(e).lower()
            return DeliveryResult(
                channel_id="wecom_new",
                message_id="",
                success=False,
                error=str(e),
                retryable=retryable,
            )

    async def send_media(self, ctx: OutboundContext) -> DeliveryResult:
        try:
            if self._bridge:
                frame = self._frame_cache.get(ctx.reply_to_id) if ctx.reply_to_id else None
                result = await self._bridge.send_media(
                    ctx,
                    frame=frame,
                    stream_id=self._stream_cache.pop(ctx.reply_to_id, None) if ctx.reply_to_id else None,
                )
                self.record_message()
                return result
            result = await send_media_v2(
                self._ws_client,
                self._frame_cache,
                ctx,
                stream_id=self._stream_cache.pop(ctx.reply_to_id, None) if ctx.reply_to_id else None,
            )
            self.record_message()
            return result
        except Exception as e:
            retryable = "timeout" in str(e).lower() or "rate limit" in str(e).lower()
            return DeliveryResult(
                channel_id="wecom_new",
                message_id="",
                success=False,
                error=str(e),
                retryable=retryable,
            )

    def format_message(self, text: str, format_hint: str = "markdown") -> str:
        return text

    @property
    def text_chunk_limit(self) -> int:
        return self._config.get("textChunkLimit", 4000)

    @property
    def rate_limit(self) -> tuple[float, int]:
        rate = self._config.get("rateLimit", 20.0)
        burst = self._config.get("rateBurst", 5)
        return (float(rate), int(burst))

    def normalize_target(self, raw: str) -> Optional[str]:
        for prefix in ("user:", "group:"):
            if raw.startswith(prefix):
                return raw[len(prefix):]
        return raw

    def target_hint(self) -> str:
        return "user:<userid> 或 group:<chatid>"

    async def handle_webhook(self, body: bytes, headers: dict) -> Optional[dict]:
        if not self._on_message:
            return {"ok": False, "error": "wecom_new channel is not running", "status_code": 409}
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            return {"ok": False, "error": str(e), "status_code": 400}
        frame = payload.get("frame") if isinstance(payload, dict) else payload
        if not isinstance(frame, dict):
            return {"ok": False, "error": "invalid frame", "status_code": 400}
        await self._handle_inbound_frame(frame, self._on_message)
        return {"ok": True}

    def _cache_frame(self, msg_id: str, frame: Any) -> None:
        self._frame_cache[msg_id] = frame
        while len(self._frame_cache) > _FRAME_CACHE_MAX:
            self._frame_cache.popitem(last=False)

    def _cache_stream_id(self, msg_id: str, stream_id: str) -> None:
        self._stream_cache[msg_id] = stream_id
        while len(self._stream_cache) > _FRAME_CACHE_MAX:
            self._stream_cache.popitem(last=False)

    def _mark_inflight(self, msg_id: str) -> bool:
        if not msg_id:
            return False
        if msg_id in self._inflight_message_ids:
            return True
        self._inflight_message_ids[msg_id] = None
        while len(self._inflight_message_ids) > _FRAME_CACHE_MAX:
            self._inflight_message_ids.popitem(last=False)
        return False

    def _clear_inflight(self, msg_id: str) -> None:
        if msg_id:
            self._inflight_message_ids.pop(msg_id, None)

    async def _wait_until_stopped(self, abort_event: asyncio.Event | None) -> None:
        abort_waiter = asyncio.create_task(
            abort_event.wait() if abort_event else asyncio.Event().wait()
        )
        reconnect_waiter = asyncio.create_task(self._reconnect_timeout_event.wait())
        done, pending = await asyncio.wait(
            {abort_waiter, reconnect_waiter},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        if reconnect_waiter in done and self._reconnect_timeout_event.is_set():
            raise RuntimeError(
                "WeCom reconnect timed out after "
                f"{self._reconnect_timeout_seconds:.1f}s"
            )

    async def _start_openclaw_bridge(
        self,
        bridge: OpenClawBridgeClient,
        on_message: Callable[[InboundMessage], Awaitable[None]],
        abort_event: asyncio.Event | None,
    ) -> None:
        log.info("wecom_new.openclaw_bridge.starting")
        await bridge.start()
        self.mark_connected()
        log.info("wecom_new.openclaw_bridge.started")
        try:
            while not (abort_event and abort_event.is_set()):
                health = await bridge.health()
                if health.get("connected"):
                    self.mark_connected()
                    self._reconnect_timeout_event.clear()
                    self._cancel_reconnect_watchdog()
                elif health.get("lastError"):
                    self.mark_disconnected()
                    error = str(health.get("lastError"))
                    if _bridge_error_should_stay_stopped(error):
                        log.warning("wecom_new.openclaw_bridge.stopped", {"error": error})
                    else:
                        raise RuntimeError(error)
                else:
                    self.mark_disconnected()
                await asyncio.sleep(5.0)
        finally:
            await self._disconnect_bridge()

    async def _handle_inbound_frame(
        self,
        frame: dict[str, Any],
        on_message: Callable[[InboundMessage], Awaitable[None]],
    ) -> None:
        try:
            msg = parse_frame(frame, self._config)
            if not msg:
                return
            if self._mark_inflight(msg.message_id):
                log.debug("wecom_new.handler.duplicate_frame", {"message_id": msg.message_id})
                return
            self._cache_frame(msg.message_id, frame)
            stream_id = f"stream-{uuid.uuid4().hex}"
            self._cache_stream_id(msg.message_id, stream_id)
            feedback = WeComStatusFeedback(
                send_text=lambda text: self._send_status_text(frame, stream_id, text, False),
                slow_task_delay_seconds=float(self._config.get("slowTaskDelaySeconds", 30.0)),
            )
            await feedback.send_ack()
            try:
                await on_message(msg)
            except Exception as e:
                self._stream_cache.pop(msg.message_id, None)
                await self._send_status_text(frame, stream_id, f"处理失败：{e}", True)
                raise
            finally:
                await feedback.complete()
                self._clear_inflight(msg.message_id)
        except Exception as e:
            log.error("wecom_new.handler.error", {"error": str(e)})

    async def _send_status_text(self, frame: dict[str, Any], stream_id: str, text: str, finish: bool) -> None:
        try:
            if self._bridge:
                await self._bridge.reply_stream(frame, stream_id, text, finish)
                return
            await self._ws_client.reply_stream(frame, stream_id, text, finish)
        except Exception as e:
            log.warning("wecom_new.status_feedback.failed", {"error": str(e)})

    def _handle_authenticated(self) -> None:
        self.mark_connected()
        self._reconnect_timeout_event.clear()
        self._cancel_reconnect_watchdog()
        log.info("wecom_new.ws.authenticated")

    def _handle_disconnected(self, reason: str) -> None:
        self.mark_disconnected()
        log.warning("wecom_new.ws.disconnected", {"reason": reason})
        self._start_reconnect_watchdog(reason=f"disconnected:{reason}")

    def _handle_reconnecting(self, attempt: int) -> None:
        self.mark_disconnected()
        log.info("wecom_new.ws.reconnecting", {"attempt": attempt})
        self._start_reconnect_watchdog(reason=f"reconnecting:{attempt}")

    def _handle_error(self, error: Exception) -> None:
        log.error("wecom_new.ws.error", {"error": str(error)})

    def _start_reconnect_watchdog(self, reason: str) -> None:
        if self._intentional_disconnect or self._ws_client is None:
            return
        if self._reconnect_timeout_event.is_set():
            return
        if self._reconnect_watchdog_task and not self._reconnect_watchdog_task.done():
            return
        self._reconnect_watchdog_task = asyncio.create_task(self._reconnect_watchdog(reason))

    async def _reconnect_watchdog(self, reason: str) -> None:
        try:
            await asyncio.sleep(self._reconnect_timeout_seconds)
        except asyncio.CancelledError:
            return
        self._reconnect_timeout_event.set()
        log.error(
            "wecom_new.ws.reconnect_watchdog_expired",
            {"reason": reason, "timeout_seconds": self._reconnect_timeout_seconds},
        )

    def _cancel_reconnect_watchdog(self) -> None:
        if self._reconnect_watchdog_task and not self._reconnect_watchdog_task.done():
            self._reconnect_watchdog_task.cancel()
        self._reconnect_watchdog_task = None

    async def _disconnect_ws_client(self) -> None:
        ws_client = self._ws_client
        if ws_client is None:
            self._cancel_reconnect_watchdog()
            return
        self._intentional_disconnect = True
        try:
            self._cancel_reconnect_watchdog()
            try:
                await asyncio.wait_for(ws_client.disconnect(), timeout=3.0)
            except (asyncio.TimeoutError, Exception):
                pass
        finally:
            if self._ws_client is ws_client:
                self._ws_client = None
            self._stream_cache.clear()
            self._frame_cache.clear()
            self._inflight_message_ids.clear()
            self._cancel_reconnect_watchdog()
            self._intentional_disconnect = False

    async def _disconnect_bridge(self) -> None:
        bridge = self._bridge
        if not bridge:
            return
        try:
            await bridge.stop()
        finally:
            if self._bridge is bridge:
                self._bridge = None
            self._stream_cache.clear()
            self._frame_cache.clear()
            self._inflight_message_ids.clear()
            self.mark_disconnected()

    def _make_message_handler(
        self,
        on_message: Callable[[InboundMessage], Awaitable[None]],
    ):
        async def _send_status_text(frame: dict[str, Any], stream_id: str, text: str, finish: bool) -> None:
            await self._send_status_text(frame, stream_id, text, finish)

        async def _handle(frame: dict) -> None:
            try:
                from wecom_aibot_sdk import generate_req_id

                msg = parse_frame(frame, self._config)
                if not msg:
                    return
                if self._mark_inflight(msg.message_id):
                    log.debug("wecom_new.handler.duplicate_frame", {"message_id": msg.message_id})
                    return
                self._cache_frame(msg.message_id, frame)
                stream_id = generate_req_id("stream")
                self._cache_stream_id(msg.message_id, stream_id)
                feedback = WeComStatusFeedback(
                    send_text=lambda text: _send_status_text(frame, stream_id, text, False),
                    slow_task_delay_seconds=float(self._config.get("slowTaskDelaySeconds", 30.0)),
                )
                await feedback.send_ack()
                try:
                    await on_message(msg)
                except Exception as e:
                    self._stream_cache.pop(msg.message_id, None)
                    await _send_status_text(frame, stream_id, f"处理失败：{e}", True)
                    raise
                finally:
                    await feedback.complete()
                    self._clear_inflight(msg.message_id)
            except Exception as e:
                log.error("wecom_new.handler.error", {"error": str(e)})

        def handler(frame: dict) -> None:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(_handle(frame))
                else:
                    loop.run_until_complete(_handle(frame))
            except Exception as e:
                log.error("wecom_new.handler.schedule_error", {"error": str(e)})

        return handler


def _bridge_error_should_stay_stopped(error: str) -> bool:
    return (
        "Kicked by server" in error
        or "new connection was established elsewhere" in error
        or "Auth failure attempts exhausted" in error
    )
