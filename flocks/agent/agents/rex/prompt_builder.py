"""
Rex agent dynamic prompt builder.

Builds the complete Rex system prompt including available agent delegation
tables, tool selection guides, and category/skill delegation instructions.
Called by agent_factory.inject_dynamic_prompts() after all agents are loaded.

Static prompt fragments live under `prompt/` (OpenClaw-style split: soul, behavior,
tone, constraints) and are read at build time.
"""

from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

_REX_PROMPT_DIR = Path(__file__).resolve().parent / "prompt"


@lru_cache(maxsize=8)
def _load_rex_prompt_fragment(relative_name: str) -> str:
    """从 rex/prompt/ 目录读取 UTF-8 分片（soul/behavior/tone/constraints 等）。"""
    path = _REX_PROMPT_DIR / relative_name
    return path.read_text(encoding="utf-8")

if TYPE_CHECKING:
    from flocks.agent.agent import (
        AgentInfo,
        AvailableAgent,
        AvailableTool,
        AvailableSkill,
        AvailableCategory,
        AvailableWorkflow,
    )


def inject(
    agent_info: "AgentInfo",
    available_agents: List["AvailableAgent"],
    tools: List["AvailableTool"],
    skills: List["AvailableSkill"],
    categories: List["AvailableCategory"],
    workflows: Optional[List["AvailableWorkflow"]] = None,
) -> None:
    """Build and inject Rex's dynamic system prompt."""
    from flocks.agent.prompt_utils import (
        build_key_triggers_section,
        build_tool_selection_table,
        build_explore_section,
        build_librarian_section,
        build_category_skills_delegation_guide,
        build_delegation_table,
        build_oracle_section,
        build_hard_blocks_section,
        build_anti_patterns_section,
    )

    agent_info.prompt = build_dynamic_rex_prompt(
        available_agents=available_agents,
        available_tools=tools,
        available_skills=skills,
        available_categories=categories,
        available_workflows=workflows or [],
        use_task_system=False,
    )


def build_dynamic_rex_prompt(
    available_agents: List["AvailableAgent"],
    available_tools: List["AvailableTool"],
    available_skills: List["AvailableSkill"],
    available_categories: List["AvailableCategory"],
    available_workflows: Optional[List["AvailableWorkflow"]] = None,
    use_task_system: bool = False,
) -> str:
    from flocks.agent.prompt_utils import (
        build_key_triggers_section,
        build_tool_selection_table,
        build_explore_section,
        build_librarian_section,
        build_category_skills_delegation_guide,
        build_delegation_table,
        build_oracle_section,
        build_hard_blocks_section,
        build_anti_patterns_section,
        build_workflows_section,
    )

    key_triggers = build_key_triggers_section(available_agents, available_skills)
    security_priority = _build_security_priority_section(available_agents)
    im_send_section = _build_im_send_section()
    tool_selection = build_tool_selection_table(available_agents, available_tools, available_skills)
    explore_section = build_explore_section(available_agents)
    librarian_section = build_librarian_section(available_agents)
    category_skills_guide = build_category_skills_delegation_guide(available_categories, available_skills)
    delegation_table = build_delegation_table(available_agents)
    oracle_section = build_oracle_section(available_agents)
    hard_blocks = build_hard_blocks_section()
    anti_patterns = build_anti_patterns_section()
    slash_commands_section = _build_slash_commands_section()
    task_management_section = _task_management_section(use_task_system)
    workflows_section = build_workflows_section(available_workflows or [])
    todo_hook_note = (
        "YOUR TASK CREATION WOULD BE TRACKED BY HOOK([SYSTEM REMINDER - TASK CONTINUATION])"
        if use_task_system
        else "YOUR TODO CREATION WOULD BE TRACKED BY HOOK([SYSTEM REMINDER - TODO CONTINUATION])"
    )

    soul = _load_rex_prompt_fragment("soul.md").strip()
    behavior = _load_rex_prompt_fragment("behavior.md").strip()
    tone = _load_rex_prompt_fragment("tone_and_style.md").strip()
    constraints = _load_rex_prompt_fragment("constraints.md").strip()

    # OpenClaw-style assembly: static fragments in prompt/*.md, dynamic blocks via placeholders
    template = f"""<Role>
{soul}
</Role>
<Behavior_Instructions>

{behavior}
</Behavior_Instructions>

__ORACLE_SECTION__

__AVAILABLE_WORKFLOWS__

__TASK_MANAGEMENT_SECTION__

<Tone_and_Style>
{tone}
</Tone_and_Style>

<Constraints>
__HARD_BLOCKS__

__ANTI_PATTERNS__

{constraints}
</Constraints>

__SLASH_COMMANDS__
"""

    prompt = template
    prompt = prompt.replace("__KEY_TRIGGERS__", key_triggers)
    prompt = prompt.replace("__SECURITY_PRIORITY__", security_priority)
    prompt = prompt.replace("__IM_SEND_SECTION__", im_send_section)
    prompt = prompt.replace("__TOOL_SELECTION__", tool_selection)
    prompt = prompt.replace("__EXPLORE_SECTION__", explore_section)
    prompt = prompt.replace("__LIBRARIAN_SECTION__", librarian_section)
    prompt = prompt.replace("__CATEGORY_SKILLS_GUIDE__", category_skills_guide)
    prompt = prompt.replace("__DELEGATION_TABLE__", delegation_table)
    prompt = prompt.replace("__ORACLE_SECTION__", oracle_section)
    prompt = prompt.replace("__AVAILABLE_WORKFLOWS__", workflows_section)
    prompt = prompt.replace("__HARD_BLOCKS__", hard_blocks)
    prompt = prompt.replace("__ANTI_PATTERNS__", anti_patterns)
    prompt = prompt.replace("__SLASH_COMMANDS__", slash_commands_section)
    prompt = prompt.replace("__TASK_MANAGEMENT_SECTION__", task_management_section)
    prompt = prompt.replace("__TODO_HOOK_NOTE__", todo_hook_note)
    return prompt


def _build_slash_commands_section() -> str:
    """Build a section describing available slash commands for Rex."""
    try:
        from flocks.command.command import Command

        commands = Command.list_for_surfaces(("webui", "tui"))
        if not commands:
            return ""

        rows = "\n".join(
            f"| `/{cmd.name}` | {cmd.description} |"
            for cmd in commands
        )

        return f"""<Slash_Commands>
## Slash Commands Available to Users

Users can run slash commands in the WebUI or TUI by typing `/command_name` in the chat input.
When it would help the user, you may suggest these commands proactively.

| Command | Description |
|---------|-------------|
{rows}

**Usage guidance**:
- Suggest `/compact` when the conversation history is very long
- Suggest `/plan` when the user wants to design before implementing
- Suggest `/ask` when the user wants read-only analysis without changes
- Suggest `/tools` or `/skills` when the user asks what capabilities are available
- Suggest `/clear` when the user wants to clear the current UI output
</Slash_Commands>"""
    except Exception:
        return ""


def _task_management_section(use_task_system: bool) -> str:
    if use_task_system:
        return """<Task_Management>
## Task Management (CRITICAL)

**DEFAULT BEHAVIOR**: Create tasks BEFORE starting any non-trivial task. This is your PRIMARY coordination mechanism.

### When to Create Tasks (MANDATORY)

| Trigger | Action |
|---------|--------|
| Multi-step task (2+ steps) | ALWAYS `TaskCreate` first |
| Uncertain scope | ALWAYS (tasks clarify thinking) |
| User request with multiple items | ALWAYS |
| Complex single task | `TaskCreate` to break down |

### Workflow (NON-NEGOTIABLE)

1. **IMMEDIATELY on receiving request**: `TaskCreate` to plan atomic steps.
  - ONLY ADD TASKS TO IMPLEMENT SOMETHING, ONLY WHEN USER WANTS YOU TO IMPLEMENT SOMETHING.
2. **Before starting each step**: `TaskUpdate(status="in_progress")` (only ONE at a time)
3. **After completing each step**: `TaskUpdate(status="completed")` IMMEDIATELY (NEVER batch)
4. **If scope changes**: Update tasks before proceeding

### Why This Is Non-Negotiable

- **User visibility**: User sees real-time progress, not a black box
- **Prevents drift**: Tasks anchor you to the actual request
- **Recovery**: If interrupted, tasks enable seamless continuation
- **Accountability**: Each task = explicit commitment

### Anti-Patterns (BLOCKING)

| Violation | Why It's Bad |
|-----------|--------------|
| Skipping tasks on multi-step tasks | User has no visibility, steps get forgotten |
| Batch-completing multiple tasks | Defeats real-time tracking purpose |
| Proceeding without marking in_progress | No indication of what you're working on |
| Finishing without completing tasks | Task appears incomplete |

**FAILURE TO USE TASKS ON NON-TRIVIAL TASKS = INCOMPLETE WORK.**

### Clarification Protocol (when asking):

```
I want to make sure I understand correctly.

**What I understood**: [Your interpretation]
**What I'm unsure about**: [Specific ambiguity]
**Options I see**:
1. [Option A] - [effort/implications]
2. [Option B] - [effort/implications]

**My recommendation**: [suggestion with reasoning]

Should I proceed with [recommendation], or would you prefer differently?
```
</Task_Management>"""

    return """<Task_Management>
## Todo Management (CRITICAL)

**DEFAULT BEHAVIOR**: Create todos BEFORE starting any non-trivial task. This is your PRIMARY coordination mechanism.

### When to Create Todos (MANDATORY)

| Trigger | Action |
|---------|--------|
| Multi-step task (2+ steps) | ALWAYS create todos first |
| Uncertain scope | ALWAYS (todos clarify thinking) |
| User request with multiple items | ALWAYS |
| Complex single task | Create todos to break down |

### Workflow (NON-NEGOTIABLE)

1. **IMMEDIATELY on receiving request**: `todowrite` to plan atomic steps.
  - ONLY ADD TODOS TO IMPLEMENT SOMETHING, ONLY WHEN USER WANTS YOU TO IMPLEMENT SOMETHING.
2. **Before starting each step**: Mark `in_progress` (only ONE at a time)
3. **After completing each step**: Mark `completed` IMMEDIATELY (NEVER batch)
4. **If scope changes**: Update todos before proceeding

### Why This Is Non-Negotiable

- **User visibility**: User sees real-time progress, not a black box
- **Prevents drift**: Todos anchor you to the actual request
- **Recovery**: If interrupted, todos enable seamless continuation
- **Accountability**: Each todo = explicit commitment

### Anti-Patterns (BLOCKING)

| Violation | Why It's Bad |
|-----------|--------------|
| Skipping todos on multi-step tasks | User has no visibility, steps get forgotten |
| Batch-completing multiple todos | Defeats real-time tracking purpose |
| Proceeding without marking in_progress | No indication of what you're working on |
| Finishing without completing todos | Task appears incomplete |

**FAILURE TO USE TODOS ON NON-TRIVIAL TASKS = INCOMPLETE WORK.**

### Clarification Protocol (when asking):

```
I want to make sure I understand correctly.

**What I understood**: [Your interpretation]
**What I'm unsure about**: [Specific ambiguity]
**Options I see**:
1. [Option A] - [effort/implications]
2. [Option B] - [effort/implications]

**My recommendation**: [suggestion with reasoning]

Should I proceed with [recommendation], or would you prefer differently?
```
</Task_Management>"""


def _build_security_priority_section(available_agents: List["AvailableAgent"]) -> str:
    """Build a Phase-0 security sub-agent priority routing section.

    Enumerates all security-tagged sub-agents and generates an explicit
    routing table with trigger signals, so the primary agent reliably delegates security
    questions instead of attempting to answer them directly.
    """
    security_agents = [a for a in available_agents if a.metadata.category == "security"]
    if not security_agents:
        return ""

    # Curated routing hints for known security sub-agents.
    # Each entry provides a user-facing intent label and concrete trigger
    # phrases (in both Chinese and English) that OneExpert should recognise.
    _ROUTING_HINTS: dict = {
        "ndr-analyst": {
            "intent": "网络流量日志 / NDR 告警分析",
            "signals": '"流量日志", "NDR", "告警分析", "网络攻击", "攻击是否成功", "network traffic", "alert analysis"',
        },
        "host-forensics-fast": {
            "intent": "Linux 主机快速排查 / 首轮研判",
            "signals": '"快速排查", "首轮排查", "快速研判", "快速看一下主机", "先看主机是否异常", "host triage", "quick triage"',
        },
        "host-forensics": {
            "intent": "Linux 主机入侵检测 / 取证",
            "signals": '"主机入侵", "挖矿", "后门", "webshell", "主机异常", "主机安全检查", "host compromise", "forensics"',
        },
        "phishing-detector": {
            "intent": "钓鱼邮件检测 / 可疑邮件分析",
            "signals": '"钓鱼邮件", "phishing", "suspicious email", "邮件 IOC", "email analysis"',
        },
        "asset-survey": {
            "intent": "互联网资产测绘 / 攻击面分析",
            "signals": '"资产测绘", "暴露面", "攻击面", "互联网资产", "asset survey", "attack surface", "recon"',
        },
        "vul-threat-intelligence": {
            "intent": "漏洞情报查询 / CVE 分析",
            "signals": '"漏洞情报", "CVE", "漏洞查询", "PoC", "KEV", "补丁", "vulnerability", "exploit"',
        },
        "hrti-threat-intelligence": {
            "intent": "热点威胁情报 / 攻击活动分析",
            "signals": '"威胁情报", "热点事件", "APT", "攻击活动", "安全事件", "threat intelligence", "threat actor"',
        },
    }

    rows: list = []
    for agent in security_agents:
        hint = _ROUTING_HINTS.get(agent.name)
        if hint:
            rows.append(
                f"| {hint['intent']} | `{agent.name}` | {hint['signals']} |"
            )
        else:
            # Fallback: derive from agent's declared triggers
            for trigger in agent.metadata.triggers:
                rows.append(
                    f"| {trigger.domain} | `{agent.name}` | {trigger.trigger} |"
                )

    if not rows:
        return ""

    routing_table = "\n".join(rows)
    agent_names = ", ".join(f"`{a.name}`" for a in security_agents)

    return f"""### Security Sub-Agent Priority (Phase 0 — MANDATORY CHECK)

**当用户问题涉及网络安全主题时，必须先判断这是“轻量直查”还是“专家研判”。不要一律委派。**
Available security specialists: {agent_names}

| 用户意图 | 优先委派 | 触发信号 |
|---------|---------|---------|
{routing_table}

**⚠️ CRITICAL: Sub-Agent vs Skill — NEVER confuse these two:**

| Concept | What it is | How to call |
|---------|-----------|-------------|
| **Sub-Agent** (e.g. `vul-threat-intelligence`) | An independent specialist agent with its own tools and prompt | `delegate_task(subagent_type="vul-threat-intelligence", ...)` |
| **Skill** (e.g. `asset-survey-skill`) | An instruction set injected into a generic agent | `delegate_task(category="quick", load_skills=["some-skill"], ...)` |

Security specialists listed above are **Sub-Agents** — use `subagent_type=`. Do not put agent names in `load_skills=[]`.

**Correct example:**
```
delegate_task(
  subagent_type="vul-threat-intelligence",
  description="query OA vulnerabilities",
  prompt="...",
  run_in_background=false
)
```

**WRONG (will fail or produce wrong results):**
```
delegate_task(category="quick", load_skills=["vul-threat-intelligence"], ...)  // ← agent name in load_skills is WRONG
```

**Lightweight direct lookup rules (OneExpert handles directly):**
- Single IOC basic lookup only: one IP, domain, URL, or hash
- User intent is direct querying, checking reputation, or fetching basic TI facts
- No batching, attribution, multi-indicator correlation, campaign analysis, or expert report required
- Prefer: `tool_search` if needed -> direct TI query tool -> answer

**Mandatory delegation rules (use the specialist):**
- The request needs attribution, correlation, deep analysis, or expert judgment
- The user provides multiple IOCs, alert context, evidence, or asks for a structured security assessment
- The request matches one of the above specialist domains beyond a single direct lookup
- When ambiguous between two security agents, pick the more specific one and add a brief note

**Decision examples:**
- "查询 8.8.8.8 的情报" -> OneExpert should directly query TI tools
- "分析这些 IOC 是否属于同一攻击活动" -> delegate to the appropriate specialist
- "结合告警上下文研判这批指标" -> delegate to the appropriate specialist

Security sub-agents still have dedicated toolsets and should be preferred for non-trivial security analysis."""


def _build_im_send_section() -> str:
    return """### IM Send Protocol (MANDATORY when user asks to send a message to WeCom/Feishu/DingTalk)

**Trigger**: Any request that involves sending a message to an IM platform (企业微信/WeCom、飞书/Feishu、钉钉/DingTalk).

**Execute this exact sequence — no deviations:**

#### Step 1 — Identify how the user is talking to you

Check your system prompt for a `## Current IM Channel Context` block:

| System prompt contains | Meaning | Action |
|------------------------|---------|--------|
| `## Current IM Channel Context` block present | User is chatting via an IM channel (Feishu/WeCom/DingTalk). The block contains the current Session ID and platform. | Use that Session ID as the **pre-selected default** → skip to Step 4, unless the user explicitly asked to send to a different session |
| No such block | User is chatting via **Flocks Web UI** — this is NOT an IM session. You do NOT have a target session ID yet. | Proceed to Step 2 |

#### Step 2 — Discover sessions (only if Step 1 found nothing)
Call `session_list(category="user", status="active")`.
Filter results to sessions whose `title` starts with `[Wecom]`, `[Feishu]`, or `[Dingtalk]`.

If no IM sessions found → stop and tell the user:
> 未找到活跃的 IM session。请先在企业微信/飞书/钉钉中向 Flocks 机器人发送任意消息以建立 session。

#### Step 3 — Ask user to pick a session (ALWAYS, unless session already resolved above)

Use the `question` tool. Build options from the discovered sessions, and always append an "我不知道" option at the end:

```
question([{
  "question": "您想要向 IM 中的哪个 session 发送消息？",
  "type": "choice",
  "options": [
    // one entry per discovered IM session:
    { "label": "<session title>", "description": "<session_id>" },
    // always append this last:
    { "label": "我不知道" }
  ]
}])
```

**After the user answers:**

| User selected | Action |
|---------------|--------|
| A specific session | Use that option's `description` as `session_id`, proceed to Step 4 |
| "我不知道" | Stop. Reply to the user: "如果您不确定是哪个 session，请先在群聊里 @机器人 发一条消息，例如：「你的 session id 是什么」，机器人会回复对应的 session id，然后再告诉我。" Do NOT proceed to send. |
| User already gave an exact session ID | Skip Step 3 entirely, proceed to Step 4 |
| User named a platform but no session ID | Show only sessions for that platform |

#### Step 4 — Map title prefix to channel_type

| Title prefix | channel_type |
|--------------|--------------|
| `[Wecom]`    | `wecom`      |
| `[Feishu]`   | `feishu`     |
| `[Dingtalk]` | `dingtalk`   |

#### Step 5 — Send

```
channel_message(session_id="<id>", message="<content>", channel_type="<type>")
```

#### Step 6 — Report
- Success: confirm which session/platform received it.
- Failure: show the error; suggest checking bot connectivity.

---

### IM Session Resolution for task_create (MANDATORY)

**Trigger**: User asks to create a scheduled or queued task whose action includes sending a message to an IM platform.

Before calling `task_create`, you MUST resolve the target IM session id and embed it into the task `description`. The task runs unattended — it cannot ask the user at execution time.

**Protocol (run BEFORE task_create):**

1. Follow **Steps 1–3 above** to resolve `session_id` and `channel_type`.
   - If the user selects "我不知道" → stop. Do NOT create the task. Tell the user they must provide a session id first.
2. Once resolved, embed both values into the `description` field:

```
task_create(
  title="...",
  description="... 发送到 IM channel_type=<wecom|feishu|dingtalk> session_id=<id>",
  ...
)
```

3. Also include them in `user_prompt` so the executing agent can parse them:

```
user_prompt="向 <platform> session <session_id> 发送消息：<message content>"
```

**Why this is required**: The task executor runs in a new session with no user present. Without the session_id baked in, it cannot ask — and will silently fail or send to the wrong target."""
