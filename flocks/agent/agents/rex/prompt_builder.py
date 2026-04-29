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


def _load_rex_runtime_prompt(relative_name: str, **variables: str) -> str:
    from flocks.session.prompt import load_prompt_fragment

    return load_prompt_fragment(f"rex/{relative_name}", **variables)

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
    )

    key_triggers = build_key_triggers_section(available_agents, available_skills)
    security_priority = ""
    im_send_section = ""
    tool_selection = build_tool_selection_table(available_agents, available_tools, available_skills)
    explore_section = build_explore_section(available_agents)
    librarian_section = build_librarian_section(available_agents)
    category_skills_guide = build_category_skills_delegation_guide(available_categories, available_skills)
    delegation_table = build_delegation_table(available_agents)
    oracle_section = build_oracle_section(available_agents)
    hard_blocks = build_hard_blocks_section()
    anti_patterns = build_anti_patterns_section()
    slash_commands_section = ""
    task_management_section = _task_management_section(use_task_system)
    workflows_section = ""
    todo_hook_note = (
        "YOUR TASK CREATION WOULD BE TRACKED BY HOOK([SYSTEM REMINDER - TASK CONTINUATION])"
        if use_task_system
        else "YOUR TODO CREATION WOULD BE TRACKED BY HOOK([SYSTEM REMINDER - TODO CONTINUATION])"
    )

    soul = _load_rex_prompt_fragment("soul.md").strip()
    behavior = _load_rex_prompt_fragment("behavior.md").strip()
    tone = _load_rex_prompt_fragment("tone_and_style.md").strip()
    constraints = _load_rex_prompt_fragment("constraints.md").strip()

    template = _load_rex_runtime_prompt(
        "base.md",
        soul=soul,
        behavior=behavior,
        tone=tone,
        constraints=constraints,
    )

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

        return _load_rex_runtime_prompt("slash_commands.md", rows=rows)
    except Exception:
        return ""


def _task_management_section(use_task_system: bool) -> str:
    if use_task_system:
        return _load_rex_runtime_prompt("task_management_task.md")

    return _load_rex_runtime_prompt("task_management_todo.md")


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

    return _load_rex_runtime_prompt(
        "security_priority.md",
        agent_names=agent_names,
        routing_table=routing_table,
    )


def _build_im_send_section() -> str:
    return _load_rex_runtime_prompt("im_send.md")
