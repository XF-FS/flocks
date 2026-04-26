from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class WeComInboundAttachment:
    kind: str
    url: str | None
    aes_key: str | None
    filename: str | None
    mime: str | None = None


@dataclass
class WeComInboundPayload:
    msg_type: str
    text: str
    attachments: list[WeComInboundAttachment] = field(default_factory=list)
    quoted_text: str | None = None
    quoted_attachments: list[WeComInboundAttachment] | None = None
    raw: dict[str, Any] | None = None
