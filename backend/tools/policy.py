# backend/tools/policy.py
"""Approval-policy classification for chat 'mode' (manual/auto/edit/plan).

requires_approval() decides, per (mode, tool_kind, tool_name/command), whether
a tool call must be gated behind an interactive approval_request event before
it runs. Read-only exploration should never block the user in auto/edit/plan
modes; anything that mutates the workspace or runs an arbitrary command still
gets gated unless it matches a conservative safe-command allowlist.

Modes:
  manual -> always gate everything (today's behavior, unchanged).
  auto   -> most permissive: read-only MCP tools, filesystem write tools
            (workspace file edits), and SAFE_COMMAND_RE terminal commands run
            without approval; only risky terminal commands are gated.
  edit   -> file edits run without approval (read-only + write MCP tools),
            but EVERY terminal command is gated -- "edit automatically"
            trusts edits, not the shell.
  plan   -> like auto for approval purposes, but main.py additionally filters
            the offered MCP tool set down to read-only tools and drops the
            terminal tool entirely, so risky tools are never reachable in the
            first place.
"""
import re

# Explicit read-only MCP tool names (bare tool name, i.e. without the
# 'server__' prefix) known across the MCP servers Forge ships/installs.
READ_ONLY_TOOL_PATTERNS: set[str] = {
    # filesystem server
    'read_file', 'read_text_file', 'read_multiple_files', 'read_media_file',
    'list_directory', 'list_directory_with_sizes', 'directory_tree',
    'search_files', 'get_file_info', 'list_allowed_directories',
    # memory server
    'read_graph', 'search_nodes', 'open_nodes',
    # git server (read-only subset)
    'git_status', 'git_log', 'git_diff', 'git_diff_staged', 'git_diff_unstaged', 'git_show',
}

# Filesystem write tools that 'edit' mode additionally trusts without approval.
WRITE_TOOL_PATTERNS: set[str] = {
    'write_file', 'edit_file', 'create_directory', 'move_file',
}

# Conservative allowlist of read-only terminal commands for 'auto'/'edit' modes.
SAFE_COMMAND_RE = re.compile(
    r'^(git (status|log|diff|show|branch)(\s|$)'
    r'|(ls|dir|pwd|whoami)\b'
    r'|node (-v|--version)$'
    r'|python (-V|--version)$'
    r'|npm (ls|list)\b)'
)


def _bare_tool_name(tool_name: str) -> str:
    """Strip a 'server__tool' prefix down to the bare tool name, if present."""
    return tool_name.partition('__')[2] or tool_name


def is_read_only_tool(tool_name: str) -> bool:
    bare = _bare_tool_name(tool_name)
    if bare in READ_ONLY_TOOL_PATTERNS:
        return True
    # Conservative fallback: unknown tools that look read-only by name.
    return bare.startswith(('read_', 'list_', 'search_', 'get_'))


def is_write_tool(tool_name: str) -> bool:
    return _bare_tool_name(tool_name) in WRITE_TOOL_PATTERNS


def is_safe_command(command: str) -> bool:
    return bool(SAFE_COMMAND_RE.match((command or '').strip()))


def requires_approval(mode: str | None, tool_kind: str, tool_name: str = '', command: str = '') -> bool:
    """tool_kind: 'terminal' or 'mcp'."""
    mode = mode or 'manual'

    if mode == 'manual':
        return True

    if tool_kind == 'terminal':
        if mode == 'edit':
            return True  # 'edit automatically' trusts file edits, not the shell
        return not is_safe_command(command)

    # tool_kind == 'mcp'
    if is_read_only_tool(tool_name):
        return False
    if mode in ('auto', 'edit') and is_write_tool(tool_name):
        return False
    return True


def filter_read_only_tools(openai_tools: list) -> list:
    """Restrict an OpenAI-format tool list to read-only MCP tools only, for
    plan mode. Expects each entry shaped {'type':'function','function':{'name':...}}."""
    out = []
    for t in openai_tools:
        name = (t.get('function') or {}).get('name', '')
        if is_read_only_tool(name):
            out.append(t)
    return out


PLAN_MODE_SYSTEM_MESSAGE = (
    'You are in PLAN MODE: explore the codebase using read-only tools, then '
    'present a clear step-by-step implementation plan. Do NOT modify anything '
    'or suggest running write commands yet.'
)
