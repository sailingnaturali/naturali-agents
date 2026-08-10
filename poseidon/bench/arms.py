"""poseidon.bench.arms — tool-delivery arms for the MCP-vs-CLI experiment.

The question: is MCP the right way to hand a boat's data to an agent, or is a
shell command (curl, or a purpose-built CLI) cheaper for the same answers?

Four arms, a clean 2x2 over *where the domain knowledge lives* and *how the
agent reaches it*:

                    | knowledge in code   | knowledge in the prompt
  ------------------|---------------------|------------------------
  MCP tool call     | mcp                 | —
  Bash              | cli                 | curl-warm
  Bash, no guidance | —                    curl-cold

  mcp        signalk-mcp's 7 shaped tools. Schemas cost tokens every turn;
             unit conversion and path knowledge are tested code.
  curl-cold  Bash + the server URL, nothing else. The agent must discover
             paths and convert SI itself. The naive setup.
  curl-warm  Bash + a path cheatsheet and a units warning in the system
             prompt. The knowledge moved from code into the prompt — where it
             is also billed every turn, which is half the point of measuring.
  cli        Bash + the `sk` command (signalk-mcp's same tools.py). Knowledge
             stays in tested code, but costs nothing until called.

All four share ONE neutral persona prompt and run flat — no subagents, no
crew_system_prompt(). That is deliberate: the production prompt names MCP
tools and would bias the Bash arms, and delegation spawns a whole extra
context whose tokens would swamp the signal being measured. These numbers are
"the tool surface, isolated", not "Poseidon as shipped".
"""
from __future__ import annotations

import os

from claude_agent_sdk import ClaudeAgentOptions

from poseidon import config
from poseidon.profiles import load_mcp_servers

def signalk_url() -> str:
    """Resolved at build time, not import time — __main__ loads ~/.poseidon/.env
    after this module is imported, so a module-level constant would miss it and
    the arms would quietly query a different host than production does.
    """
    return os.environ.get("SIGNALK_URL", "http://naturalaspi:3000")


# Identical across arms so the only variable is how data is reached.
PERSONA = """You are the ship's systems assistant aboard a sailing vessel.

Answer the crew's question in one or two sentences of natural spoken English.
Always give units in full — knots, metres, percent, volts, amps — never raw
symbols or abbreviations.

Use your tools to read live vessel data. Never guess or estimate a reading; if
you cannot get it, say so plainly."""

_CURL_COLD = """
The vessel's SignalK server is at {url}. It speaks the SignalK REST
API and reads are anonymous. Use the Bash tool with curl to query it."""

# The same knowledge signalk-mcp encodes in tools.py, moved into the prompt.
_CURL_WARM = """
The vessel's SignalK server is at {url}. It speaks the SignalK REST
API and reads are anonymous. Use the Bash tool with curl to query it.

Read a single path with:
  curl -s {url}/signalk/v1/api/vessels/self/<path/with/slashes>

Do NOT fetch the whole vessels/self tree — it is over 16 KB. Go straight to
the path you need. The paths that matter:

  environment.depth.belowKeel / .belowTransducer / .belowSurface
  environment.wind.speedTrue / .speedApparent / .directionTrue / .angleApparent
  environment.tide.heightNow / .state / .heightHigh / .heightLow
  electrical.batteries.house.capacity.stateOfCharge / .voltage / .current
  tanks.freshWater.0.currentLevel / tanks.blackWater.0.currentLevel
  navigation.position / .speedOverGround / .headingTrue / .state
  propulsion.port.runTime / propulsion.starboard.runTime
  notifications   (subtree: active alarms, each leaf has state/message)

SignalK is strictly SI. You MUST convert before answering:
  speed m/s -> knots (x1.94384)   angles radians -> degrees (x57.2958)
  ratios 0-1 -> percent (x100)    temperature kelvin -> celsius (-273.15)
  depth and height are already metres; runTime is seconds."""

_CLI = """
The vessel's data is available through the `sk` command. Run it with the Bash
tool. It prints JSON with values already converted to human units.

  sk depth                    depth below keel, transducer and surface
  sk battery [bank]           state of charge, voltage, current
  sk alarms                   active notifications, worst first
  sk time                     vessel local time
  sk route                    active route
  sk paths [prefix]           list available data paths
  sk read <path>              any SignalK path's current value

Run `sk --help` if you need the exact usage."""


def _options(prompt_extra: str, tools: list[str], mcp_servers: dict) -> ClaudeAgentOptions:
    url = signalk_url()
    env = {"SIGNALK_URL": url}   # inherited by spawned MCP servers and by `sk`
    if config.BASE_URL:
        env["ANTHROPIC_BASE_URL"] = config.BASE_URL
    return ClaudeAgentOptions(
        system_prompt=PERSONA + prompt_extra.format(url=url),
        model=config.MODEL,
        env=env,
        mcp_servers=mcp_servers,
        strict_mcp_config=True,
        allowed_tools=tools,
        tools=tools,
        setting_sources=[],                    # no CLAUDE.md, no user settings
        permission_mode="bypassPermissions",
        include_partial_messages=False,
        max_turns=20,
    )


def _signalk_server() -> dict:
    """Just the signalk MCP server — the other 10 are not under test."""
    return {"signalk": load_mcp_servers()["signalk"]}


ARMS = {
    "mcp":       lambda: _options("", ["mcp__signalk"], _signalk_server()),
    "curl-cold": lambda: _options(_CURL_COLD, ["Bash"], {}),
    "curl-warm": lambda: _options(_CURL_WARM, ["Bash"], {}),
    "cli":       lambda: _options(_CLI, ["Bash"], {}),
}


def build_options(arm: str) -> ClaudeAgentOptions:
    if arm not in ARMS:
        raise ValueError(f"unknown arm {arm!r}; choose from {sorted(ARMS)}")
    return ARMS[arm]()
