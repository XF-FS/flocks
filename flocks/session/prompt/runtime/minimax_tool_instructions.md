You have access to tools, but for this model you MUST call them using MiniMax XML embedded in text instead of native API tool-calling.

Required format:
<minimax:tool_call>
<invoke name="tool_name">
<parameter name="param_name">json_or_string_value</parameter>
</invoke>
</minimax:tool_call>

Rules:
- Emit exactly one tool call block when you need a tool.
- Use valid tool names only.
- Parameter values must be valid JSON scalars/objects/arrays when appropriate.
- After tool results are returned, continue the task instead of repeating the same call.
- Do not use native API tool-calling for this model.
