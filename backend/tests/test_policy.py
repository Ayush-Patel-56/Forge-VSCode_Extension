# backend/tests/test_policy.py
"""
Proves backend/tools/policy.py's approval-gating matrix for chat 'mode'
(manual/auto/edit/plan):

  1. requires_approval() matrix -- manual gates everything; auto passes
     read-only MCP tools + safe terminal commands but gates writes/risky
     commands; edit additionally passes filesystem write tools; the
     conservative read_-prefixed fallback passes an unknown tool in auto.
  2. filter_read_only_tools() -- restricts an OpenAI-format tool list to
     read-only tools only (used to build the plan-mode tool set in main.py).

No network / no db / no main.py import -- policy.py has none of those
dependencies.

Run with:  python backend/tests/test_policy.py
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from tools.policy import (  # noqa: E402
    filter_read_only_tools, is_read_only_tool, is_safe_command, requires_approval,
)


def run_matrix_test() -> bool:
    ok = True

    def check(label, actual, expected):
        nonlocal ok
        if actual != expected:
            print(f"FAIL: {label} -> expected {expected!r}, got {actual!r}")
            ok = False
        else:
            print(f"PASS: {label} -> {actual!r}")

    # --- manual: gates everything, both tool kinds ------------------------
    check("manual gates mcp read_file",
          requires_approval('manual', 'mcp', tool_name='filesystem__read_file'), True)
    check("manual gates mcp write_file",
          requires_approval('manual', 'mcp', tool_name='filesystem__write_file'), True)
    check("manual gates terminal 'git status'",
          requires_approval('manual', 'terminal', command='git status'), True)

    # --- auto: read-only mcp + file writes + safe commands pass; risky
    # terminal commands gated ------------------------------------------------
    check("auto passes mcp read_file",
          requires_approval('auto', 'mcp', tool_name='filesystem__read_file'), False)
    check("auto passes terminal 'git status'",
          requires_approval('auto', 'terminal', command='git status'), False)
    check("auto passes mcp write_file (workspace edits are trusted)",
          requires_approval('auto', 'mcp', tool_name='filesystem__write_file'), False)
    check("auto passes mcp edit_file",
          requires_approval('auto', 'mcp', tool_name='filesystem__edit_file'), False)
    check("auto gates terminal 'git push'",
          requires_approval('auto', 'terminal', command='git push'), True)
    check("auto gates terminal 'rm -rf x'",
          requires_approval('auto', 'terminal', command='rm -rf x'), True)

    # --- edit: file edits pass; EVERY terminal command gated ---------------
    check("edit passes mcp write_file",
          requires_approval('edit', 'mcp', tool_name='filesystem__write_file'), False)
    check("edit passes mcp edit_file",
          requires_approval('edit', 'mcp', tool_name='filesystem__edit_file'), False)
    check("edit gates terminal 'git push'",
          requires_approval('edit', 'terminal', command='git push'), True)
    check("edit gates terminal 'git status' (edit trusts edits, not the shell)",
          requires_approval('edit', 'terminal', command='git status'), True)

    # --- conservative fallback: unknown read_-prefixed tool passes in auto
    check("auto passes unknown 'someserver__read_something'",
          requires_approval('auto', 'mcp', tool_name='someserver__read_something'), False)
    check("auto gates unknown 'someserver__do_something'",
          requires_approval('auto', 'mcp', tool_name='someserver__do_something'), True)

    # --- helper predicates directly ----------------------------------------
    check("is_read_only_tool('filesystem__list_directory')",
          is_read_only_tool('filesystem__list_directory'), True)
    check("is_safe_command('npm list')", is_safe_command('npm list'), True)
    check("is_safe_command('rm -rf /')", is_safe_command('rm -rf /'), False)

    return ok


def run_filter_read_only_tools_test() -> bool:
    ok = True
    tools = [
        {'type': 'function', 'function': {'name': 'filesystem__read_file'}},
        {'type': 'function', 'function': {'name': 'filesystem__write_file'}},
        {'type': 'function', 'function': {'name': 'filesystem__list_directory'}},
        {'type': 'function', 'function': {'name': 'terminal__run_command'}},
    ]
    filtered = filter_read_only_tools(tools)
    names = {t['function']['name'] for t in filtered}
    expected = {'filesystem__read_file', 'filesystem__list_directory'}
    if names != expected:
        print(f"FAIL: filter_read_only_tools() -> expected {expected!r}, got {names!r}")
        ok = False
    else:
        print(f"PASS: filter_read_only_tools() restricted to read-only tools: {names!r}")
    return ok


def main() -> int:
    ok_matrix = run_matrix_test()
    ok_filter = run_filter_read_only_tools_test()

    ok = ok_matrix and ok_filter
    if ok:
        print("PASS: all policy assertions succeeded")
        return 0
    print("FAIL: one or more policy assertions failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())
