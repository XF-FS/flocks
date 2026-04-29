Use MiniMax XML for tool calls; native API tool-calling is unavailable for this model.

<minimax:tool_call>
<invoke name="tool_name">
<parameter name="param_name">json_or_string_value</parameter>
</invoke>
</minimax:tool_call>

Rules:
- Emit exactly one tool call block when using a tool.
- Use valid tool names only.
- Parameter values must be valid JSON scalars, objects, or arrays.
- After tool results return, continue the task.
- Do not use native API tool-calling for this model.
