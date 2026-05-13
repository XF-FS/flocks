"""
Xiaomi MiMo provider implementation.

MiMo is an AI assistant developed by Xiaomi with reasoning capabilities.
Docs: https://platform.xiaomimimo.com/docs/zh-CN/api/chat/openai-api

Key differences from standard OpenAI API:
- Authentication via ``api-key`` header (not ``Authorization: Bearer``)
- Uses ``max_completion_tokens`` instead of ``max_tokens``
- Streaming responses include ``reasoning_content`` in delta (thinking model)
- Usage includes ``reasoning_tokens`` in ``completion_tokens_details``
"""

from typing import Any, AsyncIterator, Dict, List, Optional

from flocks.provider.provider import (
    ChatMessage,
    ChatResponse,
    StreamChunk,
)
from flocks.provider.sdk.openai_base import (
    OpenAIBaseProvider,
    _normalize_stream_usage,
    _supports_include_usage_fallback,
    extract_reasoning_content,
)
from flocks.utils.log import Log

log = Log.create(service="provider.xiaomi_mimo")


class XiaomiMimoProvider(OpenAIBaseProvider):
    """Xiaomi MiMo provider (OpenAI-compatible) with reasoning support.

    Inherits chat/chat_stream from OpenAIBaseProvider with overrides for:
    - Custom ``api-key`` header authentication
    - ``max_completion_tokens`` parameter instead of ``max_tokens``
    - Reasoning content extraction from ``reasoning_content`` delta field
    """

    DEFAULT_BASE_URL = "https://api.xiaomimimo.com/v1"
    ENV_API_KEY = ["MIMO_API_KEY"]
    ENV_BASE_URL = "MIMO_BASE_URL"
    CATALOG_ID = ""

    def __init__(self):
        super().__init__(provider_id="xiaomi-mimo", name="Xiaomi MiMo")

    @staticmethod
    def _format_messages(messages: List[ChatMessage]) -> list:
        formatted = []
        for m in messages:
            d: Dict[str, Any] = {"role": m.role, "content": m.content}
            if m.reasoning:
                d["reasoning_content"] = m.reasoning
            if m.tool_calls:
                d["tool_calls"] = m.tool_calls
            if m.tool_call_id:
                d["tool_call_id"] = m.tool_call_id
            if m.name:
                d["name"] = m.name
            formatted.append(d)
        return formatted

    def _get_client(self):
        if self._client is not None:
            return self._client

        from openai import AsyncOpenAI
        import httpx

        api_key = self._config.api_key if self._config else self._api_key
        if not api_key:
            raise ValueError(
                "Xiaomi MiMo API key not configured. Set MIMO_API_KEY."
            )

        base_url = (
            self._config.base_url
            if self._config and self._config.base_url
            else self._base_url
        )

        custom_settings = getattr(self._config, "custom_settings", None) or {}
        verify_ssl = True
        if "verify_ssl" in custom_settings:
            verify_ssl = bool(custom_settings["verify_ssl"])

        http_client = httpx.AsyncClient(verify=verify_ssl, timeout=120.0)

        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers={
                "api-key": api_key,
            },
            http_client=http_client,
        )

        self.log.info("xiaomi_mimo.client.created", {
            "base_url": base_url,
            "verify_ssl": verify_ssl,
        })

        return self._client

    @staticmethod
    def _build_params(
        model_id: str,
        messages: list,
        **kwargs,
    ) -> Dict[str, Any]:
        thinking = kwargs.get("thinking")

        params: Dict[str, Any] = {
            "model": model_id,
            "messages": messages,
        }

        extra_body = dict(kwargs.get("extra_body") or {})
        if thinking:
            extra_body["thinking"] = thinking
        else:
            temperature = kwargs.get("temperature")
            if temperature is not None:
                params["temperature"] = temperature
        if extra_body:
            params["extra_body"] = extra_body

        max_tokens = kwargs.get("max_tokens")
        if max_tokens:
            params["max_completion_tokens"] = max_tokens
        if kwargs.get("tools"):
            params["tools"] = kwargs["tools"]

        return params

    async def chat(
        self, model_id: str, messages: List[ChatMessage], **kwargs
    ) -> ChatResponse:
        client = self._get_client()
        openai_messages = self._format_messages(messages)
        params = self._build_params(model_id, openai_messages, **kwargs)

        response = await client.chat.completions.create(**params)
        if not response.choices:
            raise ValueError(
                f"Xiaomi MiMo API returned empty choices. model={model_id}"
            )
        choice = response.choices[0]
        msg = getattr(choice, "message", None)
        if msg is None:
            raise ValueError(
                f"Xiaomi MiMo API returned choice with null message. model={model_id}"
            )

        reasoning_tokens = 0
        if response.usage and hasattr(response.usage, "completion_tokens_details"):
            details = response.usage.completion_tokens_details
            if details and hasattr(details, "reasoning_tokens"):
                reasoning_tokens = details.reasoning_tokens or 0

        return ChatResponse(
            id=response.id,
            model=response.model,
            content=msg.content or "",
            finish_reason=choice.finish_reason or "stop",
            usage={
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
                **({"reasoning_tokens": reasoning_tokens} if reasoning_tokens else {}),
            },
        )

    async def chat_stream(
        self, model_id: str, messages: List[ChatMessage], **kwargs
    ) -> AsyncIterator[StreamChunk]:
        client = self._get_client()
        openai_messages = self._format_messages(messages)

        params = self._build_params(model_id, openai_messages, **kwargs)
        params["stream"] = True
        params["stream_options"] = {"include_usage": True}

        log.info("xiaomi_mimo.stream.request", {
            "model": model_id,
            "has_tools": bool(kwargs.get("tools")),
            "max_tokens": kwargs.get("max_tokens"),
        })

        try:
            stream = await client.chat.completions.create(**params)
        except Exception as exc:
            if not _supports_include_usage_fallback(exc):
                raise
            log.warn("xiaomi_mimo.stream.include_usage_unsupported", {
                "model": model_id,
                "error": str(exc),
            })
            params = dict(params)
            params.pop("stream_options", None)
            stream = await client.chat.completions.create(**params)

        stream_usage: Optional[Dict[str, int]] = None
        usage_emitted = False
        emitted_substantive_chunk = False
        _first_delta_logged = False

        async for chunk in stream:
            normalized_usage = _normalize_stream_usage(getattr(chunk, "usage", None))
            if normalized_usage:
                stream_usage = normalized_usage
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta
            yielded_finish = False

            if delta is not None:
                if not _first_delta_logged:
                    _first_delta_logged = True
                    try:
                        delta_attrs = {
                            k: type(v).__name__
                            for k, v in vars(delta).items()
                            if v is not None and k != "__pydantic_fields_set__"
                        }
                    except TypeError:
                        delta_attrs = []
                    extra = getattr(delta, "model_extra", None)
                    log.info("xiaomi_mimo.stream.first_delta", {
                        "delta_attrs": delta_attrs,
                        "model_extra_keys": list(extra.keys()) if extra else [],
                        "has_content": bool(getattr(delta, "content", None)),
                        "has_reasoning": bool(getattr(delta, "reasoning_content", None)),
                    })

                reasoning = extract_reasoning_content(delta)
                if reasoning:
                    emitted_substantive_chunk = True
                    yield StreamChunk(
                        event_type="reasoning",
                        reasoning=reasoning,
                        finish_reason=None,
                    )

                delta_text = getattr(delta, "content", None)
                if delta_text:
                    emitted_substantive_chunk = True
                    yield StreamChunk(delta=delta_text, finish_reason=None)

                delta_tcs = getattr(delta, "tool_calls", None)
                if delta_tcs:
                    emitted_substantive_chunk = True
                    tool_calls = []
                    for tc in delta_tcs:
                        tc_dict = {
                            "index": tc.index if hasattr(tc, "index") else 0,
                            "id": tc.id if tc.id else None,
                            "type": "function",
                            "function": {
                                "name": tc.function.name if (tc.function and tc.function.name) else None,
                                "arguments": tc.function.arguments if (tc.function and tc.function.arguments) else None,
                            },
                        }
                        tool_calls.append(tc_dict)

                    if tool_calls:
                        terminal_chunk = StreamChunk(
                            delta="",
                            finish_reason=choice.finish_reason,
                            tool_calls=tool_calls,
                            usage=stream_usage,
                        )
                        yield terminal_chunk
                        usage_emitted = usage_emitted or terminal_chunk.usage is not None
                        yielded_finish = True

            if choice.finish_reason and not yielded_finish:
                terminal_chunk = StreamChunk(
                    delta="",
                    finish_reason=choice.finish_reason,
                    usage=stream_usage,
                )
                yield terminal_chunk
                usage_emitted = usage_emitted or terminal_chunk.usage is not None

        if emitted_substantive_chunk and stream_usage and not usage_emitted:
            yield StreamChunk(delta="", finish_reason=None, usage=stream_usage)

        if not emitted_substantive_chunk:
            log.warn("xiaomi_mimo.stream.empty_response", {
                "model": model_id,
                "has_tools": bool(kwargs.get("tools")),
            })
            fallback_error: Optional[Exception] = None
            try:
                fallback = await self.chat(model_id, messages, **kwargs)
                fallback_content = fallback.content or ""
                if fallback_content:
                    yield StreamChunk(
                        delta=fallback_content,
                        finish_reason=fallback.finish_reason or "stop",
                        usage=fallback.usage or None,
                    )
                    return
            except Exception as exc:
                fallback_error = exc

            if fallback_error:
                raise fallback_error
            raise ValueError(
                f"Xiaomi MiMo API returned an empty streaming response and empty fallback response. "
                f"model={model_id}"
            )
