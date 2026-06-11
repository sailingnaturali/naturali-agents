"""poseidon/profiles.py — agent profiles: tool subsets + SDK options factory.

Lanes x profiles (spec §2.5): Navigator roots the crew channel; Engineer and
Logbook are SDK subagents carrying their own tool subsets; the alarm lane
builds its own minimal options in alarms.py. MCP server commands live in
mcp_servers.json (machine-generated from the hermes config — see the plan,
Task 5 Step 5); only stdio servers, no secrets in the file.

SDK notes (verified against claude-agent-sdk 0.2.97 / CLI 2.1.173):
  - ClaudeAgentOptions.mcp_servers accepts a dict; passing a Path requires a
    {"mcpServers": ...} wrapper that our flat JSON does not have, so we call
    load_mcp_servers() and pass the dict directly (SDK wraps dicts correctly).
  - AgentDefinition.tools restricts tool availability for each subagent.
  - setting_sources=[] suppresses loading Claude Code settings/CLAUDE.md.
  - strict_mcp_config=True prevents the CLI from also loading the user/project
    MCP configs into the daemon session.
  - The delegation tool is named "Agent" in this SDK version (confirmed via
    poseidon/interim.py _TOPICS key which already uses "Agent").
"""
from __future__ import annotations

import json
from pathlib import Path

from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions

from poseidon import config, prompts

# "mcp__<server>" entries match every tool that server exposes.
NAVIGATOR_TOOLS = [
    "mcp__signalk", "mcp__weather", "mcp__currents", "mcp__pilotbook",
    "mcp__colregs", "mcp__outstations",
    "Agent",  # delegation to Engineer/Logbook subagents
]
ENGINEER_TOOLS = ["mcp__vessel-knowledge", "mcp__signalk"]
LOGBOOK_TOOLS = ["mcp__logbook", "mcp__signalk"]

_MCP_SERVERS_JSON = Path(__file__).with_name("mcp_servers.json")


def load_mcp_servers(path: Path | None = None) -> dict:
    path = path or _MCP_SERVERS_JSON
    return json.loads(path.read_text(encoding="utf-8"))


def crew_options() -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        system_prompt=prompts.crew_system_prompt(),
        model=config.MODEL,
        mcp_servers=load_mcp_servers(),
        strict_mcp_config=True,
        allowed_tools=NAVIGATOR_TOOLS + ENGINEER_TOOLS + LOGBOOK_TOOLS,
        tools=NAVIGATOR_TOOLS,
        # tools= only filters built-ins; MCP scoping needs disallowed_tools.
        # Engineer/Logbook subagents re-allow these via AgentDefinition.tools.
        # If live verification shows delegation losing access, drop this line
        # (documented fallback: soft scoping, full schemas in main context).
        disallowed_tools=["mcp__vessel-knowledge", "mcp__logbook"],
        agents={
            "engineer": AgentDefinition(
                description=("Vessel systems, equipment knowledge, alarm "
                             "triage. Delegate battery/electrical/tank/"
                             "equipment questions here."),
                prompt=prompts.engineer_prompt(),
                tools=ENGINEER_TOOLS,
            ),
            "logbook": AgentDefinition(
                description=("Ship's log: record moments, recall past "
                             "entries. Delegate log questions here."),
                prompt=prompts.LOGBOOK_PROMPT,
                tools=LOGBOOK_TOOLS,
            ),
        },
        setting_sources=[],          # never load Claude Code settings/CLAUDE.md
        permission_mode="bypassPermissions",  # headless daemon, curated tools
        include_partial_messages=False,       # block-level events suffice
        max_turns=20,
    )
