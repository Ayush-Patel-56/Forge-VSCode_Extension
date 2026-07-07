# backend/tests/test_mcp_bridge.py
"""
Proves the MCP tool-calling bridge end to end:

  A. Real client test -- spawns the actual filesystem MCP server (via
     MCPManager, same as test_mcp_manager.py), lists its tools, and calls
     one to write + read back a file on disk.
  B. Router loop test -- no network, no real MCP process. Stubs a fake
     OpenAI-style client and a fake tool executor to prove
     ModelRouter.stream()'s tool loop yields a progress chunk, invokes the
     executor with parsed arguments, and yields the model's final content
     once it stops calling tools.

Run with:  python backend/tests/test_mcp_bridge.py
"""
import asyncio
import json
import os
import sys
import tempfile
import shutil
from pathlib import Path
from types import SimpleNamespace

# Isolate this test from the user's real ~/.forge/forge.db BEFORE importing db:
# install/uninstall below would otherwise flip the user's is_installed flags.
os.environ['FORGE_DB_PATH'] = str(Path(tempfile.mkdtemp(prefix='forge-test-db-')) / 'forge.db')

# backend/ must be on sys.path so `from mcp.manager import MCPManager` /
# `from router.model_router import ModelRouter` resolve the same way they do
# inside the backend package itself. Do NOT import main.py.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# The router's tool-call progress chunks contain a non-ASCII glyph (⚙). Some
# Windows consoles use a cp1252 codepage that can't encode it -- make print()
# tolerant so a narrow console doesn't crash an otherwise-passing test.
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
except Exception:
    pass

from db import init_db  # noqa: E402
from mcp.manager import MCPManager  # noqa: E402
from router.model_router import ModelRouter  # noqa: E402


# ---------------------------------------------------------------------------
# Part A: real MCP client against a real spawned filesystem server.
# ---------------------------------------------------------------------------

async def run_real_client_test() -> bool:
    ok = True
    init_db()
    manager = MCPManager()
    workspace = Path(tempfile.mkdtemp(prefix="forge-mcp-bridge-test-"))

    try:
        result = await manager.install('filesystem', {'WORKSPACE_PATH': str(workspace)})
        if result.get('status') != 'ready':
            print(f"FAIL: install('filesystem', ...) expected status 'ready', got {result}")
            return False
        print("PASS: install('filesystem', ...) returned status 'ready'")

        tools = manager.get_all_tools()
        if not tools:
            print("FAIL: get_all_tools() returned an empty list after installing filesystem MCP")
            ok = False
        else:
            print(f"PASS: get_all_tools() returned {len(tools)} tool(s): {[t['name'] for t in tools]}")

        tool_names = {t['name'] for t in tools}
        has_read = 'read_file' in tool_names or 'read_text_file' in tool_names
        has_write = 'write_file' in tool_names
        if not has_read or not has_write:
            print(f"FAIL: expected filesystem tools to include a read tool and 'write_file', got {sorted(tool_names)}")
            ok = False
        else:
            print(f"PASS: filesystem tools include expected read/write tools: {sorted(tool_names)}")

        fs_entries = [t for t in tools if t['server'] == 'filesystem']
        if not fs_entries or 'input_schema' not in fs_entries[0] or 'description' not in fs_entries[0]:
            print(f"FAIL: expected tool entries shaped {{'server','name','description','input_schema'}}, got {fs_entries[:1]}")
            ok = False
        else:
            print("PASS: tool entries are shaped {'server','name','description','input_schema'}")

        # --- round-trip a real file through the bridge ---------------------
        target_path = workspace / 'bridge_test.txt'
        write_content = 'hello from the mcp tool-calling bridge\n'

        write_result = await manager.call_tool('filesystem', 'write_file', {
            'path': str(target_path),
            'content': write_content,
        })
        if write_result is None:
            print("FAIL: call_tool('filesystem', 'write_file', ...) returned None")
            ok = False
        else:
            print(f"PASS: call_tool('filesystem', 'write_file', ...) returned: {write_result}")

        if not target_path.exists():
            print(f"FAIL: expected {target_path} to exist on disk after write_file, it does not")
            ok = False
        else:
            on_disk = target_path.read_text()
            if on_disk != write_content:
                print(f"FAIL: on-disk content {on_disk!r} != written content {write_content!r}")
                ok = False
            else:
                print(f"PASS: {target_path} exists on disk with the expected content")

        read_tool = 'read_file' if 'read_file' in tool_names else 'read_text_file'
        read_result = await manager.call_tool('filesystem', read_tool, {'path': str(target_path)})
        read_text = read_result.get('text', '') if isinstance(read_result, dict) else str(read_result)
        if write_content.strip() not in read_text:
            print(f"FAIL: expected read-back content to contain {write_content.strip()!r}, got {read_text!r}")
            ok = False
        else:
            print(f"PASS: call_tool('filesystem', '{read_tool}', ...) round-tripped the written content")

        return ok
    finally:
        try:
            await manager.stop_all()
        except Exception:
            pass
        for proc in list(manager._processes.values()):
            try:
                if proc.poll() is None:
                    proc.kill()
            except Exception:
                pass
        shutil.rmtree(workspace, ignore_errors=True)


# ---------------------------------------------------------------------------
# Part B: router tool loop, fully stubbed -- no network, no real process.
# ---------------------------------------------------------------------------

def _make_tool_call(call_id: str, name: str, arguments_json: str) -> SimpleNamespace:
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=arguments_json))


def _make_response(content, tool_calls=None, usage=None) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=tool_calls))],
        usage=usage,
    )


async def run_router_loop_test() -> bool:
    ok = True
    router = ModelRouter()
    router._log_usage = lambda *args, **kwargs: None  # type: ignore[method-assign]

    fake_tool = {
        'type': 'function',
        'function': {
            'name': 'fakeserver__faketool',
            'description': 'a fake tool for testing',
            'parameters': {'type': 'object', 'properties': {'x': {'type': 'number'}}},
        },
    }

    executor_calls: list[tuple[str, dict]] = []

    async def fake_executor(raw_name: str, arguments: dict):
        executor_calls.append((raw_name, arguments))
        return {'text': 'tool result text'}

    def fake_tools_provider():
        return [fake_tool], fake_executor

    call_count = {'n': 0}

    async def fake_create(**kwargs):
        call_count['n'] += 1
        if call_count['n'] == 1:
            if 'tools' not in kwargs or not kwargs['tools']:
                raise AssertionError('expected tools to be passed on the first tool-loop call')
            tool_call = _make_tool_call('call_1', 'fakeserver__faketool', json.dumps({'x': 1}))
            return _make_response(None, tool_calls=[tool_call])
        return _make_response('final answer from the model', tool_calls=None)

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
    router._get_client = lambda provider: fake_client  # type: ignore[method-assign]

    events = []
    async for raw in router.stream(
        messages=[{'role': 'user', 'content': 'please use the fake tool'}],
        model_id=None,
        context_chunks=[],
        tools_provider=fake_tools_provider,
    ):
        events.append(json.loads(raw))

    # The plain-text "⚙ calling ..." progress chunk was replaced by a typed
    # tool_call event (see model_router.py's typed SSE event protocol).
    collected = [e['content'] for e in events if 'content' in e]

    tool_call_events = [e for e in events if e.get('event') == 'tool_call' and e.get('name') == 'fakeserver.faketool']
    if not tool_call_events:
        print(f"FAIL: expected a tool_call event for 'fakeserver.faketool', got {events!r}")
        ok = False
    else:
        print(f"PASS: router yielded a typed tool_call event: {tool_call_events[0]!r}")

    final_chunks = [c for c in collected if c == 'final answer from the model']
    if not final_chunks:
        print(f"FAIL: expected a final chunk == 'final answer from the model', got {collected!r}")
        ok = False
    else:
        print("PASS: router yielded the model's final content chunk after the tool call")

    if executor_calls != [('fakeserver__faketool', {'x': 1})]:
        print(f"FAIL: expected executor to be called with [('fakeserver__faketool', {{'x': 1}})], got {executor_calls!r}")
        ok = False
    else:
        print(f"PASS: tool executor received the parsed arguments: {executor_calls!r}")

    if call_count['n'] != 2:
        print(f"FAIL: expected exactly 2 create() calls (tool_calls, then final), got {call_count['n']}")
        ok = False
    else:
        print("PASS: exactly 2 create() calls happened (tool-calls round, then final round)")

    return ok


def main() -> int:
    ok_a = asyncio.run(run_real_client_test())
    ok_b = asyncio.run(run_router_loop_test())

    ok = ok_a and ok_b
    if ok:
        print("PASS: all MCP tool-calling bridge assertions succeeded")
        return 0
    print("FAIL: one or more MCP tool-calling bridge assertions failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())
