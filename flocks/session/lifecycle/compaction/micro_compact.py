"""Micro Compact — lightweight per-tool-call context pruning.

Two paths, both clean up old tool-call outputs without LLM summarization:

1. **Count-based** (``apply_count_based``): Runs every turn during chat message
   construction.  Keeps the most recent *N* tool calls (default 5) and replaces
   older tool outputs with ``MICRO_COMPACT_PLACEHOLDER``.

2. **Time-based** (``apply_time_based``): Triggers when the last assistant
   message is older than ``idle_threshold_ms`` (default 60 min).  Same
   retention logic, but fires once per idle gap.

Both paths operate on the **individual tool call** level (not per-turn), so a
single turn with 3 tool calls counts as 3 separate entries.

Only tools whose name is NOT in ``MICRO_COMPACT_EXCLUDE`` are eligible.
Currently only ``skill`` is excluded.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import List, Optional, Any, Dict, Iterable

from flocks.utils.log import Log

log = Log.create(service="session.compaction.micro_compact")

# ---------------------------------------------------------------------------
# Constants / defaults
# ---------------------------------------------------------------------------

MICRO_COMPACT_EXCLUDE: set[str] = {"skill"}
"""Tool names that are NEVER micro-compacted."""

DEFAULT_KEEP_RECENT = 5
"""Default number of recent tool calls to preserve."""

DEFAULT_MIN_SAVED_CHARS = 4_000
"""Minimum estimated chars saved before micro-compact is worth doing."""

TIME_BASED_IDLE_THRESHOLD_MS = 60 * 60 * 1000
"""60 minutes in milliseconds — default idle threshold for time-based path."""

MICRO_COMPACT_PLACEHOLDER = "[Old tool result content cleared]"
"""Replacement text for compacted tool outputs."""


# ---------------------------------------------------------------------------
# Environment variable overrides
# ---------------------------------------------------------------------------

def _env_keep_recent() -> Optional[int]:
    val = os.environ.get("FLOCKS_MICRO_COMPACT_KEEP_RECENT")
    if val is not None:
        try:
            return int(val)
        except ValueError:
            pass
    return None


def _env_enabled() -> bool:
    val = os.environ.get("FLOCKS_MICRO_COMPACT_ENABLED")
    if val is not None:
        return val.lower() not in ("0", "false", "no")
    return True  # enabled by default


def _env_idle_threshold_ms() -> int:
    val = os.environ.get("FLOCKS_MICRO_COMPACT_IDLE_THRESHOLD_MS")
    if val is not None:
        try:
            return int(val)
        except ValueError:
            pass
    return TIME_BASED_IDLE_THRESHOLD_MS


# ---------------------------------------------------------------------------
# Config resolver
# ---------------------------------------------------------------------------

async def _resolve_config() -> Dict[str, Any]:
    """Load micro-compact settings from Flocks config + env overrides."""
    keep_recent = DEFAULT_KEEP_RECENT
    enabled = True
    idle_threshold_ms = TIME_BASED_IDLE_THRESHOLD_MS
    min_saved_chars = DEFAULT_MIN_SAVED_CHARS

    try:
        from flocks.config import Config
        cfg = await Config.get()
        compaction = getattr(cfg, "compaction", None)
        if compaction:
            if getattr(compaction, "micro_compact_keep_recent", None) is not None:
                keep_recent = compaction.micro_compact_keep_recent
            if getattr(compaction, "micro_compact_enabled", None) is not None:
                enabled = compaction.micro_compact_enabled
            if getattr(compaction, "micro_compact_idle_threshold_ms", None) is not None:
                idle_threshold_ms = compaction.micro_compact_idle_threshold_ms
            if getattr(compaction, "micro_compact_min_saved_chars", None) is not None:
                min_saved_chars = compaction.micro_compact_min_saved_chars
    except Exception:
        pass

    # Env overrides take precedence
    env_keep = _env_keep_recent()
    if env_keep is not None:
        keep_recent = env_keep
    if not _env_enabled():
        enabled = False
    idle_threshold_ms = _env_idle_threshold_ms()

    return {
        "keep_recent": max(1, keep_recent),
        "enabled": enabled,
        "idle_threshold_ms": idle_threshold_ms,
        "min_saved_chars": max(0, min_saved_chars),
    }


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ToolCallRef:
    """Reference to a single tool call part eligible for micro-compaction."""
    message_id: str
    part: Any  # ToolPart instance
    part_index: int  # index within the message's parts list


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------

def _is_compactable(tool_name: str) -> bool:
    return tool_name not in MICRO_COMPACT_EXCLUDE


def _collect_from_parts(message_id: str, parts: Iterable[Any]) -> List[ToolCallRef]:
    refs: List[ToolCallRef] = []
    for idx, part in enumerate(parts):
        if getattr(part, "type", None) != "tool":
            continue
        state = getattr(part, "state", None)
        if state is None:
            continue
        if getattr(state, "status", None) != "completed":
            continue
        time_info = getattr(state, "time", None) or {}
        if isinstance(time_info, dict) and time_info.get("compacted"):
            continue
        tool_name = getattr(part, "tool", "")
        if not _is_compactable(tool_name):
            continue
        refs.append(ToolCallRef(message_id=message_id, part=part, part_index=idx))
    return refs


async def collect_compactable_tool_calls(
    session_id: str,
    messages: list,
) -> List[ToolCallRef]:
    """Collect eligible tool calls across messages in chronological order.

    Works in both hot paths:
    - runner path: prefers preloaded ``_parts_cache`` on the message object
    - session loop path: falls back to ``Message.parts()``
    """
    refs: List[ToolCallRef] = []

    from flocks.session.message import Message

    for msg in messages:
        try:
            role = msg.role.value if hasattr(msg.role, "value") else msg.role
        except Exception:
            continue
        if role != "assistant":
            continue

        msg_id = getattr(msg, "id", None)
        if not msg_id:
            continue

        parts = getattr(msg, "_parts_cache", None)
        if parts is None:
            parts = await Message.parts(msg_id, session_id)

        refs.extend(_collect_from_parts(msg_id, parts))

    return refs


# ---------------------------------------------------------------------------
# Core compaction helpers
# ---------------------------------------------------------------------------

async def _compact_refs(
    session_id: str,
    refs: List[ToolCallRef],
    keep_recent: int,
    reason: str,
) -> int:
    """Replace tool outputs beyond the *keep_recent* most recent with placeholder.

    Returns the number of tool outputs compacted.
    """
    if len(refs) <= keep_recent:
        return 0

    to_compact = refs[:-keep_recent]
    compacted_count = 0
    now_ms = int(time.time() * 1000)
    affected_msg_ids: set[str] = set()

    for ref in to_compact:
        state = getattr(ref.part, "state", None)
        if state is None:
            continue
        # Mark as compacted
        time_info = getattr(state, "time", None)
        if time_info is None:
            time_info = {}
            state.time = time_info
        time_info["compacted"] = now_ms

        # Store placeholder in metadata so runner can pick it up
        metadata = getattr(state, "metadata", None)
        if metadata is None:
            metadata = {}
            state.metadata = metadata
        metadata["micro_compacted"] = True
        metadata["micro_compact_reason"] = reason
        metadata["micro_compact_placeholder"] = MICRO_COMPACT_PLACEHOLDER
        metadata["context_compact_placeholder"] = MICRO_COMPACT_PLACEHOLDER

        # Clear the output to save memory (runner reads metadata placeholder)
        if hasattr(state, "output"):
            state.output = MICRO_COMPACT_PLACEHOLDER

        compacted_count += 1
        affected_msg_ids.add(ref.message_id)

    # Persist changes
    if affected_msg_ids:
        try:
            from flocks.session.message import Message
            for mid in affected_msg_ids:
                await Message._persist_parts(session_id, message_id=mid)
        except Exception as persist_err:
            log.warn("micro_compact.persist_error", {"error": str(persist_err)})

    return compacted_count


def _estimate_saved_chars(refs: List[ToolCallRef], keep_recent: int) -> int:
    if len(refs) <= keep_recent:
        return 0

    estimated = 0
    for ref in refs[:-keep_recent]:
        state = getattr(ref.part, "state", None)
        if state is None:
            continue
        output = getattr(state, "output", "")
        if not isinstance(output, str):
            output = str(output)
        estimated += max(0, len(output) - len(MICRO_COMPACT_PLACEHOLDER))
    return estimated


# ---------------------------------------------------------------------------
# Public API: Count-based
# ---------------------------------------------------------------------------

async def apply_count_based(
    session_id: str,
    messages: list,
    keep_recent: Optional[int] = None,
) -> int:
    """Count-based micro compact — keep the *keep_recent* most recent tool calls.

    Designed to run every turn inside ``_to_chat_messages``.  Lightweight: no
    LLM call, just iterates tool parts and marks old ones as compacted.

    Args:
        session_id: Current session ID.
        messages: List of MessageInfo (or compatible) objects.
        keep_recent: Override for the number of recent tool calls to keep.
            If ``None``, resolved from config / env.

    Returns:
        Number of tool outputs compacted.
    """
    cfg = await _resolve_config()
    if not cfg["enabled"]:
        return 0

    effective_keep = keep_recent if keep_recent is not None else cfg["keep_recent"]
    refs = await collect_compactable_tool_calls(session_id, messages)
    if not refs:
        return 0

    estimated_saved = _estimate_saved_chars(refs, effective_keep)
    if estimated_saved < cfg["min_saved_chars"]:
        log.debug("micro_compact.count_based.skip_low_gain", {
            "session_id": session_id,
            "estimated_saved_chars": estimated_saved,
            "min_saved_chars": cfg["min_saved_chars"],
        })
        return 0

    compacted = await _compact_refs(session_id, refs, effective_keep, "count_based")
    if compacted > 0:
        log.info("micro_compact.count_based", {
            "session_id": session_id,
            "total_compactable": len(refs),
            "kept": min(effective_keep, len(refs)),
            "compacted": compacted,
            "keep_recent": effective_keep,
            "estimated_saved_chars": estimated_saved,
        })
    return compacted


# ---------------------------------------------------------------------------
# Public API: Time-based
# ---------------------------------------------------------------------------

async def apply_time_based(
    session_id: str,
    messages: list,
    keep_recent: Optional[int] = None,
    idle_threshold_ms: Optional[int] = None,
) -> int:
    """Time-based micro compact — trigger after idle gap.

    Checks whether the last assistant message was created more than
    ``idle_threshold_ms`` ago.  If so, compacts old tool outputs.

    Args:
        session_id: Current session ID.
        messages: List of MessageInfo objects.
        keep_recent: Override for retention count.
        idle_threshold_ms: Override for idle threshold.

    Returns:
        Number of tool outputs compacted (0 if idle threshold not reached).
    """
    cfg = await _resolve_config()
    if not cfg["enabled"]:
        return 0

    effective_threshold = idle_threshold_ms or cfg["idle_threshold_ms"]
    now_ms = int(time.time() * 1000)

    # Find the last assistant message timestamp
    last_assistant_ts = 0
    for msg in reversed(messages):
        try:
            role = msg.role.value if hasattr(msg.role, "value") else msg.role
        except Exception:
            continue
        if role == "assistant":
            time_created = getattr(msg, "time", None)
            if isinstance(time_created, dict):
                last_assistant_ts = time_created.get("created", 0)
            elif hasattr(time_created, "created"):
                last_assistant_ts = time_created.created
            elif isinstance(time_created, (int, float)):
                last_assistant_ts = int(time_created)
            break

    if last_assistant_ts == 0:
        return 0

    idle_ms = now_ms - last_assistant_ts
    if idle_ms < effective_threshold:
        log.debug("micro_compact.time_based.skip", {
            "session_id": session_id,
            "idle_ms": idle_ms,
            "threshold_ms": effective_threshold,
        })
        return 0

    effective_keep = keep_recent if keep_recent is not None else cfg["keep_recent"]
    refs = await collect_compactable_tool_calls(session_id, messages)
    if not refs:
        return 0

    estimated_saved = _estimate_saved_chars(refs, effective_keep)
    if estimated_saved < cfg["min_saved_chars"]:
        log.debug("micro_compact.time_based.skip_low_gain", {
            "session_id": session_id,
            "estimated_saved_chars": estimated_saved,
            "min_saved_chars": cfg["min_saved_chars"],
            "idle_ms": idle_ms,
        })
        return 0

    compacted = await _compact_refs(session_id, refs, effective_keep, "time_based")
    if compacted > 0:
        log.info("micro_compact.time_based", {
            "session_id": session_id,
            "idle_ms": idle_ms,
            "total_compactable": len(refs),
            "kept": min(effective_keep, len(refs)),
            "compacted": compacted,
            "keep_recent": effective_keep,
            "estimated_saved_chars": estimated_saved,
        })
    return compacted
