from __future__ import annotations

import asyncio
import contextlib
import os
import socket
from pathlib import Path
from typing import Any

import aiohttp

from flocks.channel.base import DeliveryResult, OutboundContext


class OpenClawBridgeClient:
    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._session: aiohttp.ClientSession | None = None
        self._process: asyncio.subprocess.Process | None = None
        self._base_url = ""
        self._account_id = str(config.get("_account_id") or config.get("accountId") or "default")
        self._owns_process = False

    @property
    def enabled(self) -> bool:
        bridge = self._bridge_config()
        if self._config.get("openclawBridge") is False or bridge.get("enabled") is False:
            return False
        return True

    async def start(self) -> None:
        bridge = self._bridge_config()
        self._session = aiohttp.ClientSession()
        self._base_url = str(bridge.get("url") or "").rstrip("/")
        if not self._base_url:
            port = int(bridge.get("port") or _pick_free_port())
            await self._start_local_process(port)
            self._base_url = f"http://127.0.0.1:{port}"

        await self._wait_until_ready()
        await self._post_json("/start", {
            "accountId": self._account_id,
            "config": self._config,
            "flocksBaseUrl": str(bridge.get("flocksBaseUrl") or os.environ.get("FLOCKS_BASE_URL") or "http://127.0.0.1:8000"),
        })

    async def stop(self) -> None:
        with contextlib.suppress(Exception):
            if self._session and self._base_url:
                await self._post_json("/stop", {"accountId": self._account_id})
        if self._session:
            await self._session.close()
            self._session = None
        if self._process and self._owns_process:
            self._process.terminate()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._process.wait(), timeout=3.0)
            if self._process.returncode is None:
                self._process.kill()
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(self._process.wait(), timeout=3.0)
        self._process = None

    async def next_events(self, timeout_ms: int = 30_000) -> list[dict[str, Any]]:
        payload = await self._get_json(f"/events?accountId={self._account_id}&timeoutMs={timeout_ms}")
        events = payload.get("events", [])
        return events if isinstance(events, list) else []

    async def health(self) -> dict[str, Any]:
        return await self._get_json(f"/health?accountId={self._account_id}")

    async def reply_stream(
        self,
        frame: dict[str, Any],
        stream_id: str,
        text: str,
        finish: bool,
    ) -> None:
        await self._post_json("/reply_stream", {
            "accountId": self._account_id,
            "frame": frame,
            "streamId": stream_id,
            "text": text,
            "finish": finish,
        })

    async def send_text(
        self,
        ctx: OutboundContext,
        *,
        frame: dict[str, Any] | None = None,
        stream_id: str | None = None,
    ) -> DeliveryResult:
        payload = await self._post_json("/send_text", {
            "accountId": ctx.account_id or self._account_id,
            "to": ctx.to,
            "text": ctx.text,
            "replyFrame": frame,
            "streamId": stream_id,
        })
        return _delivery_result(payload, "wecom_new", ctx.to)

    async def send_media(
        self,
        ctx: OutboundContext,
        *,
        frame: dict[str, Any] | None = None,
        stream_id: str | None = None,
    ) -> DeliveryResult:
        payload = await self._post_json("/send_media", {
            "accountId": ctx.account_id or self._account_id,
            "to": ctx.to,
            "text": ctx.text,
            "mediaUrl": ctx.media_url,
            "replyFrame": frame,
            "streamId": stream_id,
        })
        return _delivery_result(payload, "wecom_new", ctx.to)

    async def _start_local_process(self, port: int) -> None:
        bridge = self._bridge_config()
        runner = Path(str(bridge.get("script") or _default_bridge_script())).expanduser()
        if not runner.is_file():
            raise RuntimeError(
                "wecom-openclaw bridge is not built. Run `npm install && npm run build` "
                "in flocks/plugin/wecom-openclaw-plugin, or set openclawBridgeConfig.url."
            )
        self._process = await asyncio.create_subprocess_exec(
            "node",
            str(runner),
            "--port",
            str(port),
            cwd=str(runner.parents[3]),
            stdout=None,
            stderr=None,
            start_new_session=True,
        )
        self._owns_process = True

    async def _wait_until_ready(self) -> None:
        deadline = asyncio.get_running_loop().time() + 10.0
        last_error = "bridge not ready"
        while asyncio.get_running_loop().time() < deadline:
            if self._process and self._process.returncode is not None:
                raise RuntimeError(f"wecom-openclaw bridge exited with code {self._process.returncode}")
            try:
                payload = await self._get_json("/health")
                if payload.get("ok"):
                    return
            except Exception as exc:
                last_error = str(exc)
            await asyncio.sleep(0.2)
        raise RuntimeError(f"wecom-openclaw bridge unavailable: {last_error}")

    async def _get_json(self, path: str) -> dict[str, Any]:
        if not self._session:
            raise RuntimeError("wecom-openclaw bridge session not started")
        async with self._session.get(f"{self._base_url}{path}") as resp:
            payload = await resp.json(content_type=None)
            if resp.status >= 400:
                raise RuntimeError(str(payload.get("error") or payload))
            return payload

    async def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._session:
            raise RuntimeError("wecom-openclaw bridge session not started")
        async with self._session.post(f"{self._base_url}{path}", json=payload) as resp:
            data = await resp.json(content_type=None)
            if resp.status >= 400:
                raise RuntimeError(str(data.get("error") or data))
            return data

    def _bridge_config(self) -> dict[str, Any]:
        raw = self._config.get("openclawBridgeConfig") or self._config.get("bridge") or {}
        return raw if isinstance(raw, dict) else {}


def _delivery_result(payload: dict[str, Any], channel_id: str, fallback_chat_id: str) -> DeliveryResult:
    return DeliveryResult(
        channel_id=channel_id,
        message_id=str(payload.get("messageId") or payload.get("message_id") or ""),
        chat_id=str(payload.get("chatId") or payload.get("chat_id") or fallback_chat_id or ""),
        success=bool(payload.get("ok", True)),
        error=payload.get("error"),
        retryable=bool(payload.get("retryable", False)),
    )


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _default_bridge_script() -> Path:
    repo_root = Path(__file__).resolve().parents[4]
    return repo_root / "flocks" / "plugin" / "wecom-openclaw-plugin" / "dist" / "src" / "bridge" / "server.js"
