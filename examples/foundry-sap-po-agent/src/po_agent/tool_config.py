"""Builds and checks the Foundry MCP tool definition for the SAP purchase order tools.

Rules (Microsoft Learn, "Connect to Model Context Protocol servers" in Foundry Agent Service):
- allowed_tools omitted or [] exposes every tool of the server, so it must list the tools explicitly.
- require_approval defaults to "always"; only read-only tools may skip approval: {"never": [...]}.
- credentials live in a Foundry project connection (project_connection_id), never in code.
"""
import re

TOOL_NAME = re.compile(r"^[a-z][a-z0-9_]{2,63}$")


class ToolConfigError(ValueError):
    """The MCP tool definition breaks one of the safety rules."""


def build_mcp_tool_kwargs(settings):
    """Keyword arguments for azure.ai.projects.models.MCPTool from config/settings.json."""
    mcp = settings["mcp"]
    kwargs = {
        "server_label": mcp["serverLabel"],
        "server_url": mcp["serverUrl"],
        "allowed_tools": list(mcp["tools"]),
        "require_approval": approval_setting(mcp["tools"], mcp.get("readOnlyTools", [])),
        "project_connection_id": settings["foundry"]["mcpConnectionName"],
    }
    check_mcp_tool_kwargs(kwargs, mcp.get("readOnlyTools", []))
    return kwargs


def approval_setting(tools, read_only_tools):
    """Only read-only tools skip approval; everything else keeps the default ("always")."""
    skip = [t for t in tools if t in set(read_only_tools)]
    if not skip:
        return "always"
    return {"never": skip}


def check_mcp_tool_kwargs(kwargs, read_only_tools):
    """Raise ToolConfigError if the definition is unsafe; return the list of problems otherwise empty."""
    problems = []
    tools = kwargs.get("allowed_tools")
    if not tools:
        problems.append("allowed_tools must list the tools explicitly (empty or missing allows all tools)")
    else:
        for name in tools:
            if not TOOL_NAME.match(name):
                problems.append(f"tool name {name!r} is not lower_snake_case")
        if len(set(tools)) != len(tools):
            problems.append("allowed_tools has duplicates")
    approval = kwargs.get("require_approval", "always")
    if approval == "never":
        problems.append('require_approval "never" skips approval for every tool, including future write tools')
    elif isinstance(approval, dict):
        if set(approval) - {"never", "always"}:
            problems.append(f"unknown require_approval keys: {sorted(set(approval) - {'never', 'always'})}")
        for name in approval.get("never", []):
            if name not in set(read_only_tools):
                problems.append(f"tool {name!r} skips approval but isn't declared read-only")
            if tools and name not in tools:
                problems.append(f"tool {name!r} skips approval but isn't in allowed_tools")
    elif approval != "always":
        problems.append(f"unexpected require_approval value {approval!r}")
    if not str(kwargs.get("server_url", "")).startswith("https://"):
        problems.append("server_url must be https")
    if not kwargs.get("project_connection_id"):
        problems.append("project_connection_id is required (credentials stay in the Foundry connection)")
    if problems:
        raise ToolConfigError("; ".join(problems))
    return []


def should_approve(tool_name, arguments, allowed_tools, read_only_tools, ask):
    """Decide an mcp_approval_request: deny unknown tools, ask the human for anything else.

    Read-only tools normally never reach this point (they skip approval); if one does, the human still decides.
    """
    if tool_name not in set(allowed_tools):
        return False
    return bool(ask(tool_name, arguments))
