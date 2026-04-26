from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable


ACK_TEXT = "已收到，正在处理中，请稍候..."
SLOW_TASK_TEXT = "任务正在处理中，预计等待时间3分钟，请稍候..."
FAILED_TEXT_PREFIX = "处理失败："


@dataclass
class WeComStatusFeedback:
    send_text: Callable[[str], Awaitable[None]]
    slow_task_delay_seconds: float = 30.0
    _slow_task: asyncio.Task[None] | None = None
    _slow_sent: bool = False

    async def send_ack(self) -> None:
        await self.send_text(ACK_TEXT)
        self._schedule_slow_task()

    async def send_failed(self, reason: str) -> None:
        await self.cancel()
        await self.send_text(f"{FAILED_TEXT_PREFIX}{reason}")

    async def complete(self) -> None:
        await self.cancel()

    async def cancel(self) -> None:
        if self._slow_task and not self._slow_task.done():
            self._slow_task.cancel()
            await asyncio.gather(self._slow_task, return_exceptions=True)
        self._slow_task = None

    def _schedule_slow_task(self) -> None:
        if self._slow_task and not self._slow_task.done():
            return
        self._slow_task = asyncio.create_task(self._send_slow_task_once())

    async def _send_slow_task_once(self) -> None:
        try:
            await asyncio.sleep(self.slow_task_delay_seconds)
            if not self._slow_sent:
                self._slow_sent = True
                await self.send_text(SLOW_TASK_TEXT)
        except asyncio.CancelledError:
            return
