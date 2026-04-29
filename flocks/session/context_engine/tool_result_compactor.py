"""工具结果压缩器。"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from flocks.session.message import Message
from flocks.tool.truncation import (
    calculate_max_tool_result_chars,
    truncate_tool_result_text,
)
from flocks.utils.log import Log

log = Log.create(service="session.context_engine.tool_result_compactor")


@dataclass(frozen=True)
class ToolResultCompactionResult:
    truncated_count: int = 0
    total_chars_before: int = 0
    total_chars_after: int = 0
    affected_message_ids: set[str] = field(default_factory=set)


@dataclass
class _ToolResultItem:
    message_id: str
    part: Any
    output: str
    original_len: int
    turn_index: int
    sequence: int


class ToolResultCompactor:
    """压缩会话里的工具输出，避免工具结果挤占主要对话上下文。"""

    _READ_FILE_TOOL_NAMES = {"read", "readfile", "read_file"}
    _COMPACT_PLACEHOLDER = (
        "[compacted: older tool output removed to free context; "
        "tool={tool}; original_chars={original_chars}]"
    )
    _PREVIEW_CHARS = 160
    _MIN_TOTAL_TOOL_RESULT_CHARS = 8_000
    _MIN_TURN_TOOL_RESULT_CHARS = 4_000
    _MAX_TOTAL_TOOL_RESULT_CHARS = 80_000
    _TOTAL_TOOL_RESULT_CONTEXT_SHARE = 0.70
    _TURN_TOOL_RESULT_BUDGET_SHARE = 0.35

    async def compact_session(
        self,
        session_id: str,
        context_window_tokens: int,
    ) -> ToolResultCompactionResult:
        max_chars = calculate_max_tool_result_chars(context_window_tokens)
        items = await self._collect_tool_results(session_id)
        if not items:
            return ToolResultCompactionResult()

        changed_part_ids: set[str] = set()
        affected_message_ids: set[str] = set()
        total_chars_before = sum(item.original_len for item in items)

        for item in items:
            if self._is_read_file_tool(item):
                if self._replace_read_file_output(item, changed_part_ids, affected_message_ids):
                    continue
            if len(item.output) <= max_chars:
                continue
            item.part.state.output = truncate_tool_result_text(item.output, max_chars)
            item.output = item.part.state.output
            changed_part_ids.add(self._part_key(item))
            affected_message_ids.add(item.message_id)

        total_budget = self._total_budget(context_window_tokens)
        turn_budget = self._turn_budget(total_budget)
        self._compact_latest_turn_to_budget(
            items,
            turn_budget,
            changed_part_ids,
            affected_message_ids,
        )
        total_chars_after = self._total_output_chars(items)

        if total_chars_after > total_budget:
            freed = self._compact_to_budget(
                items,
                total_chars_after - total_budget,
                changed_part_ids,
                affected_message_ids,
            )
            if freed:
                log.info("tool_result_compactor.total_budget_enforced", {
                    "session_id": session_id,
                    "total_tool_chars": total_chars_after,
                    "budget": total_budget,
                    "turn_budget": turn_budget,
                    "freed": freed,
                })

        if affected_message_ids:
            try:
                for message_id in affected_message_ids:
                    await Message._persist_parts(session_id, message_id=message_id)
            except Exception as persist_err:
                log.warn("tool_result_compactor.persist_error", {"error": str(persist_err)})

        final_chars = self._total_output_chars(items)
        changed_count = len(changed_part_ids)
        if changed_count:
            log.info("tool_result_compactor.compacted", {
                "session_id": session_id,
                "count": changed_count,
                "max_chars": max_chars,
                "total_budget": total_budget,
                "turn_budget": turn_budget,
                "context_window": context_window_tokens,
                "total_chars_before": total_chars_before,
                "total_chars_after": final_chars,
            })

        return ToolResultCompactionResult(
            truncated_count=changed_count,
            total_chars_before=total_chars_before,
            total_chars_after=final_chars,
            affected_message_ids=affected_message_ids,
        )

    async def _collect_tool_results(self, session_id: str) -> list[_ToolResultItem]:
        messages = await Message.list(session_id)
        items: list[_ToolResultItem] = []
        turn_index = 0

        for msg in messages:
            role = msg.role.value if hasattr(msg.role, "value") else msg.role
            if role == "user":
                turn_index += 1
            if role != "assistant":
                continue

            parts = await Message.parts(msg.id, session_id)
            for part in parts:
                if getattr(part, "type", None) != "tool":
                    continue
                state = getattr(part, "state", None)
                if not state or getattr(state, "status", None) != "completed":
                    continue
                time_info = getattr(state, "time", None)
                if isinstance(time_info, dict) and time_info.get("compacted"):
                    continue

                output = self._coerce_output(getattr(state, "output", ""))
                if output != getattr(state, "output", ""):
                    state.output = output
                items.append(
                    _ToolResultItem(
                        message_id=msg.id,
                        part=part,
                        output=output,
                        original_len=len(output),
                        turn_index=turn_index,
                        sequence=len(items),
                    )
                )

        return items

    def _compact_latest_turn_to_budget(
        self,
        items: list[_ToolResultItem],
        turn_budget: int,
        changed_part_ids: set[str],
        affected_message_ids: set[str],
    ) -> None:
        latest_turn = max(item.turn_index for item in items)
        latest_turn_items = [item for item in items if item.turn_index == latest_turn]
        latest_turn_chars = self._total_output_chars(latest_turn_items)

        for item in latest_turn_items[:-1]:
            if latest_turn_chars <= turn_budget:
                break
            freed = self._replace_with_placeholder(
                item,
                "tool_result_budget",
                changed_part_ids,
                affected_message_ids,
            )
            latest_turn_chars -= freed

    def _compact_to_budget(
        self,
        items: list[_ToolResultItem],
        chars_to_free: int,
        changed_part_ids: set[str],
        affected_message_ids: set[str],
    ) -> int:
        freed = 0
        candidates = items[:-1]

        for item in candidates:
            if freed >= chars_to_free:
                break
            freed += self._replace_with_placeholder(
                item,
                "context_budget",
                changed_part_ids,
                affected_message_ids,
            )

        return freed

    def _replace_with_placeholder(
        self,
        item: _ToolResultItem,
        reason: str,
        changed_part_ids: set[str],
        affected_message_ids: set[str],
    ) -> int:
        placeholder = self._placeholder(item)
        output_len = len(item.output)
        if output_len <= len(placeholder):
            return 0

        item.part.state.output = placeholder
        self._mark_compacted(item, placeholder, reason)
        item.output = placeholder
        changed_part_ids.add(self._part_key(item))
        affected_message_ids.add(item.message_id)
        return output_len - len(placeholder)

    def _total_budget(self, context_window_tokens: int) -> int:
        budget = int(context_window_tokens * 4 * self._TOTAL_TOOL_RESULT_CONTEXT_SHARE)
        return min(
            self._MAX_TOTAL_TOOL_RESULT_CHARS,
            max(self._MIN_TOTAL_TOOL_RESULT_CHARS, budget),
        )

    def _turn_budget(self, total_budget: int) -> int:
        return max(
            self._MIN_TURN_TOOL_RESULT_CHARS,
            int(total_budget * self._TURN_TOOL_RESULT_BUDGET_SHARE),
        )

    @staticmethod
    def _total_output_chars(items: list[_ToolResultItem]) -> int:
        return sum(len(item.output) for item in items)

    @staticmethod
    def _coerce_output(output: Any) -> str:
        if isinstance(output, str):
            return output
        try:
            return json.dumps(output, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(output)

    @classmethod
    def _part_key(cls, item: _ToolResultItem) -> str:
        return str(getattr(item.part, "id", f"{item.message_id}:{item.sequence}"))

    def _mark_compacted(self, item: _ToolResultItem, placeholder: str, reason: str) -> None:
        state = item.part.state
        metadata = dict(getattr(state, "metadata", None) or {})
        metadata.update({
            "context_compacted": True,
            "context_compact_reason": reason,
            "context_compact_preview": self._preview(item.output),
            "context_compact_placeholder": placeholder,
        })
        state.metadata = metadata

        time_info = dict(getattr(state, "time", None) or {})
        time_info["compacted"] = int(time.time() * 1000)
        state.time = time_info

    def _is_read_file_tool(self, item: _ToolResultItem) -> bool:
        tool_name = getattr(item.part, "tool", "") or ""
        normalized = tool_name.replace("-", "_").replace(" ", "_").lower()
        return normalized in self._READ_FILE_TOOL_NAMES

    def _replace_read_file_output(
        self,
        item: _ToolResultItem,
        changed_part_ids: set[str],
        affected_message_ids: set[str],
    ) -> bool:
        placeholder = self._read_file_placeholder(item)
        if item.output == placeholder:
            return False

        item.part.state.output = placeholder
        self._mark_compacted(item, placeholder, "read_file_content_omitted")
        item.output = placeholder
        changed_part_ids.add(self._part_key(item))
        affected_message_ids.add(item.message_id)
        return True

    def _read_file_placeholder(self, item: _ToolResultItem) -> str:
        tool_name = getattr(item.part, "tool", "") or "read"
        state = getattr(item.part, "state", None)
        tool_input = getattr(state, "input", None) if state is not None else None
        call_info = self._format_read_file_call(tool_input)
        return (
            "[compacted: file content omitted during context compaction; "
            f"tool={tool_name}; {call_info}; original_chars={item.original_len}]"
        )

    @classmethod
    def _format_read_file_call(cls, tool_input: Any) -> str:
        if isinstance(tool_input, dict):
            file_path = (
                tool_input.get("filePath")
                or tool_input.get("file_path")
                or tool_input.get("path")
                or tool_input.get("filename")
                or "unknown"
            )
            extras = []
            for key in ("offset", "limit", "start", "end"):
                if key in tool_input and tool_input[key] is not None:
                    extras.append(f"{key}={tool_input[key]}")
            suffix = f"; {', '.join(extras)}" if extras else ""
            return f"filePath={file_path}{suffix}"
        if tool_input:
            return f"input={cls._coerce_output(tool_input)}"
        return "filePath=unknown"

    def _preview(self, output: str) -> str:
        normalized = " ".join(output.split())
        preview = normalized[: self._PREVIEW_CHARS]
        return f"{preview}..." if len(normalized) > self._PREVIEW_CHARS else preview

    def _placeholder(self, item: _ToolResultItem) -> str:
        tool_name = getattr(item.part, "tool", "") or "unknown"
        return self._COMPACT_PLACEHOLDER.format(
            tool=tool_name,
            original_chars=item.original_len,
        )
