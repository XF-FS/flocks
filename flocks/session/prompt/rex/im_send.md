### IM Send Protocol (MANDATORY when user asks to send a message to WeCom/Feishu/DingTalk)

Trigger: sending a message to WeCom, Feishu, or DingTalk.

Rules:
- If `## Current IM Channel Context` exists and the user did not specify another target, use that session.
- If no IM context exists, call `session_list(category="user", status="active")`, filter `[Wecom]`, `[Feishu]`, `[Dingtalk]`, then ask the user to choose.
- Always include an "我不知道" option. If selected, stop and ask the user to obtain the session id from the IM chat.
- Map title prefix to channel type: `[Wecom]` -> `wecom`, `[Feishu]` -> `feishu`, `[Dingtalk]` -> `dingtalk`.
- Send with `channel_message(session_id="<id>", message="<content>", channel_type="<type>")`.
- Report success or the tool error.

For scheduled or queued tasks that send IM messages:
- Resolve `session_id` and `channel_type` before `task_create`.
- Put both values in `description` and `user_prompt`.
- Do not create the task if the target IM session is unresolved.

If no IM sessions are found, reply: 未找到活跃的 IM session。请先在企业微信/飞书/钉钉中向 Flocks 机器人发送任意消息以建立 session。
